from typing import Any, Dict

import pydantic
from fastapi import APIRouter, Request
from program.services.content.overseerr import Overseerr
from program.services.indexers.trakt import get_imdbid_from_tmdb, get_imdbid_from_tvdb
from program.media.item import MediaItem
from requests import RequestException
from loguru import logger

from ..models.overseerr import OverseerrWebhook

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
            return {"success": True}
        req = OverseerrWebhook.model_validate(response)
    except (Exception, pydantic.ValidationError) as e:
        logger.error(f"Failed to process request: {e}")
        return {"success": False, "message": str(e)}

    imdb_id = get_imdbid_from_overseerr(req)
    if not imdb_id:
        logger.error(f"Failed to get imdb_id from Overseerr: {req.media.tmdbId}")
        return {"success": False, "message": "Failed to get imdb_id from Overseerr"}

    overseerr: Overseerr = request.app.program.all_services[Overseerr]
    if not overseerr.initialized:
        logger.error("Overseerr not initialized")
        return {"success": False, "message": "Overseerr not initialized"}

    new_item = MediaItem({"imdb_id": imdb_id, "requested_by": "overseerr", "requested_id": req.request.request_id})

    request.app.program.em.add_item(new_item, service="Overseerr")

    return {"success": True}


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