from datetime import datetime
from enum import Enum
from typing import List, Optional

import Levenshtein
from fastapi import APIRouter, HTTPException, Request
from program.db.db import db
from sqlalchemy import select, func
import program.db.db_functions as DB
from program.content.overseerr import Overseerr
from program.media.item import Episode, MediaItem, Movie, Season, Show
from program.media.state import States
from program.symlink import Symlinker
from pydantic import BaseModel
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
    request: Request,
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
        type_lower = type.lower()
        if type_lower not in ["movie", "show", "season", "episode"]:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid type: {type}. Valid types are: ['movie', 'show', 'season', 'episode']",
            )
        query = query.where(MediaItem.type == type_lower)

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
async def get_extended_item_info(request: Request, item_id: str):
    with db.Session() as session:
        item = DB._get_item_from_db(session, MediaItem({"imdb_id":str(item_id)}))
        if item is None:
            raise HTTPException(status_code=404, detail="Item not found")
        return {"success": True, "item": item.to_extended_dict()}


@router.post("/add/imdb/{imdb_id}")
@router.post("/add/imdb/")
async def add_items(
    request: Request, imdb_id: Optional[str] = None, imdb_ids: Optional[IMDbIDs] = None
):
    if imdb_id:
        imdb_ids = IMDbIDs(imdb_ids=[imdb_id])
    elif (
        not imdb_ids or not imdb_ids.imdb_ids or any(not id for id in imdb_ids.imdb_ids)
    ):
        raise HTTPException(status_code=400, detail="No IMDb ID(s) provided")

    valid_ids = []
    for id in imdb_ids.imdb_ids:
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


@router.delete("/remove/")
async def remove_item(
    request: Request, item_id: Optional[str] = None, imdb_id: Optional[str] = None
):
    if item_id:
        item = request.app.program.media_items.get(item_id)
        id_type = "ID"
    elif imdb_id:
        item = next(
            (i for i in request.app.program.media_items if i.imdb_id == imdb_id), None
        )
        id_type = "IMDb ID"
    else:
        raise HTTPException(status_code=400, detail="No item ID or IMDb ID provided")

    if not item:
        logger.error(f"Item with {id_type} {item_id or imdb_id} not found")
        return {
            "success": False,
            "message": f"Item with {id_type} {item_id or imdb_id} not found. No action taken.",
        }

    try:
        # Remove the item from the media items container
        request.app.program.media_items.remove([item])
        logger.log("API", f"Removed item with {id_type} {item_id or imdb_id}")

        # Remove the symlinks associated with the item
        symlinker = request.app.program.service[Symlinker]
        symlinker.delete_item_symlinks(item)
        logger.log(
            "API", f"Removed symlink for item with {id_type} {item_id or imdb_id}"
        )

        # Save and reload the media items to ensure consistency
        symlinker.save_and_reload_media_items(request.app.program.media_items)
        logger.log(
            "API",
            f"Saved and reloaded media items after removing item with {id_type} {item_id or imdb_id}",
        )

        return {
            "success": True,
            "message": f"Successfully removed item with {id_type} {item_id or imdb_id}.",
        }
    except Exception as e:
        logger.error(f"Failed to remove item with {id_type} {item_id or imdb_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/imdb/{imdb_id}")
async def get_imdb_info(
    request: Request,
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


@router.get("/incomplete")
async def get_incomplete_items(request: Request):
    if not hasattr(request.app, "program"):
        logger.error("Program not found in the request app")
        raise HTTPException(status_code=500, detail="Internal server error")

    with db.Session() as session:
        incomplete_items = session.execute(
            select(MediaItem).where(MediaItem.last_state != "Completed")
        ).unique().scalars().all()

        if not incomplete_items:
            return {"success": True, "incomplete_items": []}

        return {
            "success": True,
            "incomplete_items": [item.to_dict() for item in incomplete_items],
        }
