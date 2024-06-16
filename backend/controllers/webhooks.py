from datetime import datetime
from typing import Any, Dict

import pydantic
from fastapi import APIRouter, Request
from program.content.overseerr import Overseerr
from program.indexers.trakt import (
    TraktIndexer,
    create_item_from_imdb_id,
    get_imdbid_from_tmdb,
)
from program.media.item import MediaItem, Show
from requests import RequestException
from utils.logger import logger
from utils.request import get

from .models.overseerr import OverseerrWebhook

router = APIRouter(
    prefix="/webhook",
    responses={404: {"description": "Not found"}},
)


@router.post("/overseerr")
async def overseerr(request: Request) -> Dict[str, Any]:
    """Webhook for Overseerr"""
    response = await request.json()

    if response.get("subject") == "Test Notification":
        logger.log("API", "Received test notification, Overseerr configured properly")
        return {"success": True}

    try:
        req = OverseerrWebhook.model_validate(response)
    except pydantic.ValidationError:
        return {"success": False, "message": "Invalid request"}
    except Exception as e:
        logger.error(f"Failed to process request: {e}")
        return {"success": False, "message": "Failed to process request"}


    imdb_id = req.media.imdbId
    if not imdb_id:
        try:
            imdb_id = get_imdbid_from_tmdb(req.media.tmdbId)
        except RequestException as e:
            logger.error(f"Failed to get imdb_id from TMDB: {req.media.tmdbId}")
            return {"success": False, "message": "Failed to get imdb_id from TMDB", "title": req.subject}
        if not imdb_id:
            logger.error(f"Failed to get imdb_id from TMDB: {req.media.tmdbId}")
            return {"success": False, "message": "Failed to get imdb_id from TMDB", "title": req.subject}

    overseerr: Overseerr = request.app.program.services[Overseerr]
    if not overseerr.initialized:
        logger.error("Overseerr not initialized")
        return {"success": False, "message": "Overseerr not initialized", "title": req.subject}

    trakt: TraktIndexer = request.app.program.services[TraktIndexer]

    if imdb_id in overseerr.recurring_items:
        logger.log("API", "Request already in queue", {"imdb_id": imdb_id})
        return {"success": False, "message": "Request already in queue", "title": req.subject}
    else:
        overseerr.recurring_items.add(imdb_id)

    try:
        new_item = MediaItem({"imdb_id": imdb_id, "requested_by": "overseerr"})
        item = create_item_from_imdb_id(new_item.imdb_id)
        if isinstance(item, Show):
            trakt._add_seasons_to_show(item, imdb_id)
        request.app.program.add_to_queue(item)
    except Exception as e:
        logger.error(f"Failed to create item from imdb_id: {imdb_id}")
        return {"success": False, "message": "Failed to create item from imdb_id", "title": req.subject}

    return {"success": True}
