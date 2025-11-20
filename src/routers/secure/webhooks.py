from typing import Any, Dict

import pydantic
from fastapi import APIRouter, Request
from loguru import logger

from program.media.item import MediaItem
from program.services.content.overseerr import Overseerr

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
            logger.log(
                "API", "Received test notification, Overseerr configured properly"
            )
            return {"success": True}
        req = OverseerrWebhook.model_validate(response)
    except (Exception, pydantic.ValidationError) as e:
        logger.error(f"Failed to process request: {e}")
        return {"success": False, "message": str(e)}

    if (
        hasattr(request.app.program, "all_services")
        and Overseerr in request.app.program.all_services
    ):
        overseerr: Overseerr = request.app.program.all_services[Overseerr]
    else:
        logger.error("Overseerr not initialized yet")
        return {"success": False, "message": "Overseerr not initialized"}

    if not overseerr.initialized:
        logger.error("Overseerr not initialized")
        return {"success": False, "message": "Overseerr not initialized"}

    item_type = req.media.media_type
    if item_type == "tv":
        item_type = "show"

    new_item = None
    if item_type == "movie":
        new_item = MediaItem(
            {
                "tmdb_id": req.media.tmdbId,
                "requested_by": "overseerr",
                "overseerr_id": req.request.request_id,
            }
        )
    elif item_type == "show":
        new_item = MediaItem(
            {
                "tvdb_id": req.media.tvdbId,
                "requested_by": "overseerr",
                "overseerr_id": req.request.request_id,
            }
        )

    if not new_item:
        logger.error(
            f"Failed to create new item: TMDB ID {req.media.tmdbId}, TVDB ID {req.media.tvdbId}"
        )
        return {"success": False, "message": "Failed to create new item"}

    request.app.program.em.add_item(new_item, service="Overseerr")
    return {"success": True}
