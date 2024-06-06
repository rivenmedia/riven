from datetime import datetime
from typing import Any, Dict

import pydantic
from fastapi import APIRouter, Request
from program.indexers.trakt import get_imdbid_from_tmdb
from utils.logger import logger

from .models.overseerr import OverseerrWebhook

router = APIRouter(
    responses={404: {"description": "Not found"}},
)


@router.post("/overseerr")
async def overseerr_webhook(request: Request) -> Dict[str, Any]:
    """Webhook for Overseerr"""
    response = await request.json()
    logger.debug(f"Received request for: {response.get('subject', 'Unknown')}")

    try:
        req = OverseerrWebhook.model_validate(response)
    except pydantic.ValidationError:
        return {"success": False, "message": "Invalid request"}

    imdb_id = req.media.imdbId
    if not imdb_id:
        imdb_id = get_imdbid_from_tmdb(req.media.tmdbId)
        if not imdb_id:
            logger.error(f"Failed to get imdb_id from TMDB: {req.media.tmdbId}")
            return {"success": False, "message": "Failed to get imdb_id from TMDB", "title": req.subject}

    item = {"imdb_id": imdb_id, "requested_by": "overseerr", "requested_at": datetime.now()}
    request.app.program.add_to_queue(item)
    return {"success": True}
