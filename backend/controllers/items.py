from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from program.media.item import MediaItem
from program.content.overseerr import Overseerr
from program.media.state import States
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
async def get_items(request: Request):
    return {
        "success": True,
        "items": [item.to_dict() for item in request.app.program.media_items],
    }


@router.get("/extended/{item_id}")
async def get_extended_item_info(request: Request, item_id: str):
    item = request.app.program.media_items.get_item(item_id)
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
    item = request.app.program.media_items.get_item(item_id)
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
    item = request.app.program.media_items.get_item(imdb_id)
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
async def get_imdb_info(request: Request, imdb_id: str):
    item = request.app.program.media_items.get_item(imdb_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Item not found")
    return {"success": True, "item": item.to_extended_dict()}
