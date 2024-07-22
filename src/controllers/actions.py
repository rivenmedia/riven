from typing import Any, Dict, Optional

import pydantic
from fastapi import APIRouter, Request
from program.content.overseerr import Overseerr
from program.indexers.trakt import TraktIndexer, get_imdbid_from_tmdb
from program.media.item import MediaItem, Show
from requests import RequestException
from utils.logger import logger

from .models.overseerr import OverseerrWebhook

router = APIRouter(
    prefix="/actions",
    responses={404: {"description": "Not found"}},
)


@router.post("/request/{imdb_id}")
async def request(request: Request, imdb_id: str) -> Dict[str, Any]:
    try:
        new_item = MediaItem({"imdb_id": imdb_id, "requested_by": "manually"})
        request.app.program.add_to_queue(new_item)
    except Exception as e:
        logger.error(f"Failed to create item from imdb_id: {imdb_id}")
        return {"success": False, "message": "Failed to create item from imdb_id"}

    return {"success": True, "message": f"Added {imdb_id} to queue"}
