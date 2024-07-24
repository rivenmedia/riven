from typing import Any, Dict

from fastapi import APIRouter, Request
from program.media.item import MediaItem
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
