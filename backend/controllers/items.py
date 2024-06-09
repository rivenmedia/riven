from datetime import datetime
from typing import List, Optional

import Levenshtein
from fastapi import APIRouter, HTTPException, Request
from program.content.overseerr import Overseerr
from program.media.container import MediaItemContainer
from program.media.item import ItemId, MediaItem
from program.media.state import States
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


@router.get("/")
async def get_items(
    request: Request,
    limit: Optional[int] = 20,
    page: Optional[int] = 1,
    search: Optional[str] = None,
    filter: Optional[str] = None,
    fetch_all: Optional[bool] = False,
    max_distance: Optional[float] = 0.90
):
    mic: MediaItemContainer = request.app.program.media_items
    items = list(mic._items.values())
    total_count = len(items)

    if search:
        search_lower = search.lower()
        items = [
            item for item in items
            if (item.title and Levenshtein.distance(search_lower, item.title.lower()) <= max_distance) or
               (item.imdb_id and Levenshtein.distance(search_lower, item.imdb_id.lower()) <= 1)
        ]
    if filter:
        filter_lower = filter.lower()
        filter_state = None
        for state in States:
            if Levenshtein.distance(filter_lower, state.name.lower()) <= 0.8:
                filter_state = state
                break
        if filter_state:
            items = [item for item in items if item.state == filter_state]
        else:
            valid_states = [state.name for state in States]
            raise HTTPException(status_code=400, detail=f"Invalid filter state: {filter}. Valid states are: {valid_states}")
    if fetch_all:
        paginated_items = items
    else:
        start = (page - 1) * limit
        end = start + limit
        paginated_items = items[start:end]

    return {
        "success": True,
        "items": [item.to_dict() for item in paginated_items],
        "page": page,
        "limit": limit,
        "total": total_count
    }

@router.get("/extended/{item_id}")
async def get_extended_item_info(request: Request, item_id: str):
    item = request.app.program.media_items.get(item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Item not found")
    return {
        "success": True,
        "item": item.to_extended_dict(),
    }


@router.post("/add/imdb/{imdb_id}")
@router.post("/add/imdb/")
async def add_items(request: Request, imdb_id: Optional[str] = None, imdb_ids: Optional[IMDbIDs] = None):
    if imdb_id:
        imdb_ids = IMDbIDs(imdb_ids=[imdb_id])
    elif not imdb_ids or not imdb_ids.imdb_ids or any(not id for id in imdb_ids.imdb_ids):
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
        item = MediaItem({"imdb_id": id, "requested_by": "iceberg", "requested_at": datetime.now()})
        request.app.program.add_to_queue(item)
    
    return {"success": True, "message": f"Added {len(valid_ids)} item(s) to the queue"}


@router.delete("/remove/id/{item_id}")
async def remove_item(request: Request, item_id: str):
    item = request.app.program.media_items.get(item_id)
    if not item:
        logger.error(f"Item with ID {item_id} not found")
        raise HTTPException(status_code=404, detail="Item not found")

    request.app.program.media_items.remove(item)
    if item.symlinked:
        request.app.program.media_items.remove_symlink(item)
        logger.log("API", f"Removed symlink for item with ID {item_id}")

    overseerr_service = request.app.program.services.get(Overseerr)
    if overseerr_service and overseerr_service.initialized:
        try:
            overseerr_result = overseerr_service.delete_request(item_id)
            if overseerr_result:
                logger.log("API", f"Deleted Overseerr request for item with ID {item_id}")
            else:
                logger.log("API", f"Failed to delete Overseerr request for item with ID {item_id}")
        except Exception as e:
            logger.error(f"Exception occurred while deleting Overseerr request for item with ID {item_id}: {e}")

    return {
        "success": True,
        "message": f"Removed {item_id}",
    }


@router.delete("/remove/imdb/{imdb_id}")
async def remove_item_by_imdb(request: Request, imdb_id: str):
    item = request.app.program.media_items.get(imdb_id)
    if not item:
        logger.error(f"Item with IMDb ID {imdb_id} not found")
        raise HTTPException(status_code=404, detail="Item not found")

    request.app.program.media_items.remove(item)
    if item.symlinked or (item.file and item.folder):  # TODO: this needs to be checked later..
        request.app.program.media_items.remove_symlink(item)
        logger.log("API", f"Removed symlink for item with IMDb ID {imdb_id}")

    overseerr_service = request.app.program.services.get(Overseerr)
    if overseerr_service and overseerr_service.initialized:
        try:
            overseerr_result = overseerr_service.delete_request(item.overseerr_id)
            if overseerr_result:
                logger.log("API", f"Deleted Overseerr request for item with IMDb ID {imdb_id}")
            else:
                logger.error(f"Failed to delete Overseerr request for item with IMDb ID {imdb_id}")
        except Exception as e:
            logger.error(f"Exception occurred while deleting Overseerr request for item with IMDb ID {imdb_id}: {e}")
    else:
        logger.error("Overseerr service not found in program services")

    return {
        "success": True,
        "message": f"Removed item with IMDb ID {imdb_id}",
    }


@router.get("/imdb/{imdb_id}")
async def get_imdb_info(request: Request, imdb_id: str, season: Optional[int] = None, episode: Optional[int] = None):
    """
    Get the item with the given IMDb ID.
    If the season and episode are provided, get the item with the given season and episode.
    """
    item_id = ItemId(imdb_id)
    if season is not None:
        item_id = ItemId(str(season), parent_id=item_id)
    if episode is not None:
        item_id = ItemId(str(episode), parent_id=item_id)
    
    item = request.app.program.media_items.get(item_id)
    if item is None:
        logger.error(f"Item with ID {item_id} not found in container")
        raise HTTPException(status_code=404, detail="Item not found")
    
    return {"success": True, "item": item.to_extended_dict()}


@router.get("/incomplete")
async def get_incomplete_items(request: Request):
    if not hasattr(request.app, 'program') or not hasattr(request.app.program, 'media_items'):
        logger.error("Program or media_items not found in the request app")
        raise HTTPException(status_code=500, detail="Internal server error")

    incomplete_items = request.app.program.media_items.incomplete_episodes
    if not incomplete_items:
        logger.info("No incomplete items found")
        return {
            "success": True,
            "incomplete_items": []
        }

    return {
        "success": True,
        "incomplete_items": [item.to_dict() for item in incomplete_items.values()]
    }
