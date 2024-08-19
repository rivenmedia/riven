from datetime import datetime
from typing import Optional

import Levenshtein
from fastapi import APIRouter, HTTPException, Request
from program.db.db import db
from program.db.db_functions import get_media_items_by_ids, delete_media_item
from program.media.item import MediaItem
from program.media.state import States
from sqlalchemy import func, select
from utils.logger import logger
from sqlalchemy.orm import joinedload

router = APIRouter(
    prefix="/items",
    tags=["items"],
    responses={404: {"description": "Not found"}},
)

def handle_ids(ids: str) -> list[int]:
    ids = [int(id) for id in ids.split(",")] if "," in ids else [int(ids)]
    if not ids:
        raise HTTPException(status_code=400, detail="No item ID provided")
    return ids

@router.get("/states")
async def get_states():
    return {
        "success": True,
        "states": [state for state in States],
    }

@router.get(
    "",
    summary="Retrieve Media Items",
    description="Fetch media items with optional filters and pagination",
)
async def get_items(
    _: Request,
    limit: Optional[int] = 50,
    page: Optional[int] = 1,
    type: Optional[str] = None,
    state: Optional[str] = None,
    sort: Optional[str] = "desc",
    search: Optional[str] = None,
    extended: Optional[bool] = False,
):
    if page < 1:
        raise HTTPException(status_code=400, detail="Page number must be 1 or greater.")

    if limit < 1:
        raise HTTPException(status_code=400, detail="Limit must be 1 or greater.")

    query = select(MediaItem)

    if search:
        search_lower = search.lower()
        if search_lower.startswith("tt"):
            query = query.where(MediaItem.imdb_id == search_lower)
        else:
            query = query.where(
                (func.lower(MediaItem.title).like(f"%{search_lower}%")) |
                (func.lower(MediaItem.imdb_id).like(f"%{search_lower}%"))
            )

    if state:
        filter_lower = state.lower()
        filter_state = None
        for state_enum in States:
            if Levenshtein.distance(filter_lower, state_enum.name.lower()) <= 0.82:
                filter_state = state_enum
                break
        if filter_state:
            query = query.where(MediaItem.state == filter_state)
        else:
            valid_states = [state_enum.name for state_enum in States]
            raise HTTPException(
                status_code=400,
                detail=f"Invalid filter state: {state}. Valid states are: {valid_states}",
            )

    if type:
        if "," in type:
            types = type.split(",")
            for type in types:
                if type not in ["movie", "show", "season", "episode"]:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Invalid type: {type}. Valid types are: ['movie', 'show', 'season', 'episode']")
        else:
            types=[type]
        query = query.where(MediaItem.type.in_(types))

    if sort and not search:
        if sort.lower() == "asc":
            query = query.order_by(MediaItem.requested_at.asc())
        elif sort.lower() == "desc":
            query = query.order_by(MediaItem.requested_at.desc())
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid sort: {sort}. Valid sorts are: ['asc', 'desc']",
            )

    with db.Session() as session:
        total_items = session.execute(select(func.count()).select_from(query.subquery())).scalar_one()
        items = session.execute(query.offset((page - 1) * limit).limit(limit)).unique().scalars().all()

        total_pages = (total_items + limit - 1) // limit

        return {
            "success": True,
            "items": [item.to_extended_dict() if extended else item.to_dict() for item in items],
            "page": page,
            "limit": limit,
            "total_items": total_items,
            "total_pages": total_pages,
        }


@router.post(
        "/add",
        summary="Add Media Items",
        description="Add media items with bases on imdb IDs",
)
async def add_items(
    request: Request, imdb_ids: str = None
):

    if not imdb_ids:
        raise HTTPException(status_code=400, detail="No IMDb ID(s) provided")

    ids = imdb_ids.split(",")

    valid_ids = []
    for id in ids:
        if not id.startswith("tt"):
            logger.warning(f"Invalid IMDb ID {id}, skipping")
        else:
            valid_ids.append(id)

    if not valid_ids:
        raise HTTPException(status_code=400, detail="No valid IMDb ID(s) provided")

    with db.Session() as _:
        for id in valid_ids:
            item = MediaItem({"imdb_id": id, "requested_by": "riven", "requested_at": datetime.now()})
            request.app.program.em.add_item(item)

    return {"success": True, "message": f"Added {len(valid_ids)} item(s) to the queue"}

@router.post(
        "/reset",
        summary="Reset Media Items",
        description="Reset media items with bases on item IDs",
)
async def reset_items(
    request: Request, ids: str
):
    ids = handle_ids(ids)
    with db.Session() as session:
        items = []
        for id in ids:
            item = session.execute(select(MediaItem).where(MediaItem._id == id).options(joinedload("*"))).unique().scalar_one()
            items.append(item)
        for item in items:
            request.app.program.em.cancel_job(item)
            item.reset()

        session.commit()
    return {"success": True, "message": f"Reset items with id {ids}"}

@router.post(
        "/retry",
        summary="Retry Media Items",
        description="Retry media items with bases on item IDs",
)
async def retry_items(
    request: Request, ids: str
):
    ids = handle_ids(ids)
    with db.Session() as session:
        items = []
        for id in ids:
            items.append(session.execute(select(MediaItem).where(MediaItem._id == id)).unique().scalar_one())
        for item in items:
            request.app.program.em.cancel_job(item)
            request.app.program.em.add_item(item)

    return {"success": True, "message": f"Retried items with id {ids}"}

@router.delete(
    "/remove",
    summary="Remove Media Items",
    description="Remove media items based on item IDs",
)
async def remove_item(request: Request, ids: str):
    ids = handle_ids(ids)
    try:
        media_items = get_media_items_by_ids(ids)
        if not media_items or len(media_items) != len(ids):
            raise ValueError("Invalid item ID(s) provided. Some items may not exist.")
        for media_item in media_items:
            request.app.program.em.cancel_job(media_item)
            delete_media_item(media_item)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {"success": True, "message": f"Removed items with ids {ids}"}

# These require downloaders to be refactored

# @router.get("/cached")
# async def manual_scrape(request: Request, ids: str):
#     scraper = request.app.program.services.get(Scraping)
#     downloader = request.app.program.services.get(Downloader).service
#     if downloader.__class__.__name__ not in ["RealDebridDownloader", "TorBoxDownloader"]:
#         raise HTTPException(status_code=400, detail="Only Real-Debrid is supported for manual scraping currently")
#     ids = [int(id) for id in ids.split(",")] if "," in ids else [int(ids)]
#     if not ids:
#         raise HTTPException(status_code=400, detail="No item ID provided")
#     with db.Session() as session:
#         items = []
#         return_dict = {}
#         for id in ids:
#             items.append(session.execute(select(MediaItem).where(MediaItem._id == id)).unique().scalar_one())
#     if any(item for item in items if item.type in ["Season", "Episode"]):
#         raise HTTPException(status_code=400, detail="Only shows and movies can be manually scraped currently")
#     for item in items:
#         new_item = item.__class__({})
#         # new_item.parent = item.parent
#         new_item.copy(item)
#         new_item.copy_other_media_attr(item)
#         scraped_results = scraper.scrape(new_item, log=False)
#         cached_hashes = downloader.get_cached_hashes(new_item, scraped_results)
#         for hash, stream in scraped_results.items():
#             return_dict[hash] = {"cached": hash in cached_hashes, "name": stream.raw_title}
#         return {"success": True, "data": return_dict}

# @router.post("/download")
# async def download(request: Request, id: str, hash: str):
#     downloader = request.app.program.services.get(Downloader).service
#     with db.Session() as session:
#         item = session.execute(select(MediaItem).where(MediaItem._id == id)).unique().scalar_one()
#         item.reset(True)
#         downloader.download_cached(item, hash)
#         request.app.program.add_to_queue(item)
#         return {"success": True, "message": f"Downloading {item.title} with hash {hash}"}