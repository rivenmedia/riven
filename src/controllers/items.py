from typing import List, Optional

import Levenshtein
import program.db.db_functions as DB
from fastapi import APIRouter, HTTPException, Request
from program.db.db import db
from program.media.item import Episode, MediaItem, Season
from program.media.state import States
from program.symlink import Symlinker
from pydantic import BaseModel
from sqlalchemy import func, select
from utils.logger import logger

router = APIRouter(
    prefix="/items",
    tags=["items"],
    responses={404: {"description": "Not found"}},
)


class IMDbIDs(BaseModel):
    imdb_ids: Optional[List[str]] = None


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
                        detail=f"Invalid type: {type}. Valid types are: ['movie', 'show', 'season', 'episode']",
                    )
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
            "items": [item.to_dict() for item in items],
            "page": page,
            "limit": limit,
            "total_items": total_items,
            "total_pages": total_pages,
        }


@router.get("/extended/{item_id}")
async def get_extended_item_info(_: Request, item_id: str):
    with db.Session() as session:
        item = session.execute(select(MediaItem).where(MediaItem.imdb_id == item_id)).unique().scalar_one_or_none()
        if item is None:
            raise HTTPException(status_code=404, detail="Item not found")
        return {"success": True, "item": item.to_extended_dict()}


@router.post("/add")
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

    for id in valid_ids:
        item = MediaItem({"imdb_id": id, "requested_by": "riven"})
        request.app.program.add_to_queue(item)

    return {"success": True, "message": f"Added {len(valid_ids)} item(s) to the queue"}


@router.delete("/remove")
async def remove_item(
    _: Request, imdb_id: str
):
    if not imdb_id:
        raise HTTPException(status_code=400, detail="No IMDb ID provided")
    if DB._remove_item_from_db(imdb_id):
        return {"success": True, "message": f"Removed item with imdb_id {imdb_id}"}
    return {"success": False, "message": f"No item with imdb_id ({imdb_id}) found"}


@router.get("/imdb/{imdb_id}")
async def get_imdb_info(
    _: Request,
    imdb_id: str,
    season: Optional[int] = None,
    episode: Optional[int] = None,
):
    """
    Get the item with the given IMDb ID.
    If the season and episode are provided, get the item with the given season and episode.
    """
    with db.Session() as session:
        if season is not None and episode is not None:
            item = session.execute(
                select(Episode).where(
                    (Episode.imdb_id == imdb_id) &
                    (Episode.season_number == season) &
                    (Episode.episode_number == episode)
                )
            ).scalar_one_or_none()
        elif season is not None:
            item = session.execute(
                select(Season).where(
                    (Season.imdb_id == imdb_id) &
                    (Season.season_number == season)
                )
            ).scalar_one_or_none()
        else:
            item = session.execute(
                select(MediaItem).where(MediaItem.imdb_id == imdb_id)
            ).scalar_one_or_none()

        if item is None:
            raise HTTPException(status_code=404, detail="Item not found")

        return {"success": True, "item": item.to_extended_dict()}
