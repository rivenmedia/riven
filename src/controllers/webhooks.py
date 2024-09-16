from typing import Any, Dict

import pydantic
from fastapi import APIRouter, Request
from program.content.overseerr import Overseerr
from program.indexers.trakt import get_imdbid_from_tmdb, get_imdbid_from_tvdb
from program.media.item import MediaItem
from requests import RequestException
from utils.logger import logger
from program.db.db_functions import _ensure_item_exists_in_db

from .models.overseerr import OverseerrWebhook

router = APIRouter(
    prefix="/webhook",
    responses={404: {"description": "Not found"}},
)


@router.post("/overseerr")
async def overseerr(request: Request) -> Dict[str, Any]:
    """Webhook for Overseerr"""
    try:
        response = await request.json()
        if response.get("subject") == "Test Notification":
            logger.log("API", "Received test notification, Overseerr configured properly")
            return {"status": "success"}
        req = OverseerrWebhook.model_validate(response)
    except (Exception, pydantic.ValidationError) as e:
        logger.error(f"Failed to process request: {e}")
        return {"status": "error", "message": str(e)}

    imdb_id = get_imdbid_from_overseerr(req)
    if not imdb_id:
        logger.error(f"Failed to get imdb_id from Overseerr: {req.media.tmdbId}")
        return {"status": "error", "message": "Failed to get imdb_id from Overseerr"}

    overseerr: Overseerr = request.app.program.all_services[Overseerr]
    if not overseerr.initialized:
        logger.error("Overseerr not initialized")
        return {"status": "error", "message": "Overseerr not initialized"}

    try:
        new_item = MediaItem({"imdb_id": imdb_id, "requested_by": "overseerr", "requested_id": req.request.request_id})
    except Exception as e:
        logger.error(f"Failed to create item for {imdb_id}: {e}")
        return {"status": "error", "message": str(e)}

    if _ensure_item_exists_in_db(new_item) or imdb_id in overseerr.recurring_items:
        logger.log("API", "Request already in queue or already exists in the database")
        return {"status": "success"}
    else:
        overseerr.recurring_items.add(imdb_id)

    try:
        request.app.program.em.add_item(new_item)
    except Exception as e:
        logger.error(f"Failed to add item for {imdb_id}: {e}")

    return {"status": "success"}


def get_imdbid_from_overseerr(req: OverseerrWebhook) -> str:
    """Get the imdb_id from the Overseerr webhook"""
    imdb_id = req.media.imdbId
    if not imdb_id:
        try:
            _type = req.media.media_type
            if _type == "tv":
                _type = "show"
            imdb_id = get_imdbid_from_tmdb(req.media.tmdbId, type=_type)
            if not imdb_id or not imdb_id.startswith("tt"):
                imdb_id = get_imdbid_from_tvdb(req.media.tvdbId, type=_type)
        except RequestException:
            pass
    return imdb_id