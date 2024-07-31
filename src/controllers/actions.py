from typing import Any, Dict

from fastapi import APIRouter, Request
from program.media.item import MediaItem
from program.symlink import Symlinker
from utils.logger import logger

router = APIRouter(
    prefix="/actions",
    responses={404: {"description": "Not found"}},
)


@router.post("/request/{imdb_id}")
async def request(request: Request, imdb_id: str) -> Dict[str, Any]:
    try:
        new_item = MediaItem({"imdb_id": imdb_id, "requested_by": "manually"})
        request.app.program.add_to_queue(new_item)
    except Exception:
        logger.error(f"Failed to create item from imdb_id: {imdb_id}")
        return {"success": False, "message": "Failed to create item from imdb_id"}

    return {"success": True, "message": f"Added {imdb_id} to queue"}

@router.delete("/symlink/{_id}")
async def remove_symlink(request: Request, _id: int) -> Dict[str, Any]:
    try:
        symlinker: Symlinker = request.app.program.services[Symlinker]
        if symlinker.delete_item_symlinks(_id):
            logger.log("API", f"Removed symlink(s) for item with id: {_id}")
            return {"success": True, "message": f"Removed symlink(s) for item with id: {_id}"}
        else:
            logger.error(f"Failed to remove symlink for item with id: {_id}")
            return {"success": False, "message": "Failed to remove symlink"}
    except Exception as e:
        logger.error(f"Failed to remove symlink for item with id: {_id}, error: {e}")
        return {"success": False, "message": "Failed to remove symlink", "error": str(e)}
