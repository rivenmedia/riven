from typing import Any, Dict

import pydantic
from fastapi import APIRouter, Request
from requests.exceptions import ConnectionError, RequestException, RetryError

from program.content.overseerr import Overseerr
from program.indexers.trakt import get_imdbid_from_tmdb, get_imdbid_from_tvdb
from program.media.item import MediaItem
from program.media.state import OverseerrStatus
from program.settings.manager import settings_manager
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
            _type = req.media.media_type
            if _type == "tv":
                _type = "show"
            imdb_id = get_imdbid_from_tmdb(req.media.tmdbId, type=_type)
            if not imdb_id or not imdb_id.startswith("tt"):
                imdb_id = get_imdbid_from_tvdb(req.media.tvdbId, type=_type)
            if not imdb_id or not imdb_id.startswith("tt"):
                logger.error(f"Failed to get imdb_id from Overseerr: {req.media.tmdbId}")
                return {"success": False, "message": "Failed to get imdb_id from Overseerr", "title": req.subject}
        except RequestException:
            logger.error(f"Failed to get imdb_id from Overseerr: {req.media.tmdbId}")
            return {"success": False, "message": "Failed to get imdb_id from Overseerr", "title": req.subject}

    overseerr: Overseerr = request.app.program.all_services[Overseerr]
    if not overseerr.initialized:
        logger.error("Overseerr not initialized")
        return {"success": False, "message": "Overseerr not initialized", "title": req.subject}

    if imdb_id in overseerr.recurring_items:
        logger.log("API", "Request already in queue", {"imdb_id": imdb_id})
        return {"success": True, "message": "Request already in queue", "title": req.subject}
    else:
        overseerr.recurring_items.add(imdb_id)

    req_id = req.request.request_id
    overseerr_config = settings_manager.settings.content.overseerr
    header = {"X-Api-Key": overseerr_config.api_key}

    try:
        resp = get(
            overseerr_config.url + f"/api/v1/request/{req_id}",
            additional_headers=header,
        )
    except (ConnectionError, RetryError) as e:
        logger.error(
            f"Failed to fetch requests from overseerr to get mediaId: {str(e)}"
        )
    except Exception as e:
        logger.error(
            f"Unexpected error during fetching requests to get mediaId: {str(e)}"
        )

    media_id = resp.data.media.id

    try:
        new_item = MediaItem(
            {
                "imdb_id": imdb_id,
                "requested_by": "overseerr",
                "last_overseerr_status": OverseerrStatus.Requested.name,
            }
        )
        if media_id:
            new_item.set("overseerr_id", media_id)
        request.app.program.em.add_item(new_item)
    except Exception:
        logger.error(f"Failed to create item from imdb_id: {imdb_id}")
        return {"success": False, "message": "Failed to create item from imdb_id", "title": req.subject}

    return {"success": True, "message": f"Added {imdb_id} to queue"}
