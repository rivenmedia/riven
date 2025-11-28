from kink import di
from pydantic import BaseModel
from fastapi import APIRouter, Request
from loguru import logger

from program.media.item import MediaItem
from program.services.content.overseerr import Overseerr
from program.program import Program

from ..models.overseerr import OverseerrWebhook

router = APIRouter(
    prefix="/webhook",
    responses={404: {"description": "Not found"}},
)


class OverseerrWebhookResponse(BaseModel):
    success: bool
    message: str | None = None


@router.post("/overseerr", response_model=OverseerrWebhookResponse)
async def overseerr(request: Request) -> OverseerrWebhookResponse:
    """Webhook for Overseerr"""

    try:
        response = await request.json()

        if response.get("subject") == "Test Notification":
            logger.log(
                "API", "Received test notification, Overseerr configured properly"
            )

            return OverseerrWebhookResponse(
                success=True,
            )

        req = OverseerrWebhook.model_validate(response)

        if services := di[Program].services:
            overseerr = services.overseerr
        else:
            logger.error("Overseerr not initialized yet")
            return OverseerrWebhookResponse(
                success=False,
                message="Overseerr not initialized",
            )

        if not overseerr.initialized:
            logger.error("Overseerr not initialized")

            return OverseerrWebhookResponse(
                success=False,
                message="Overseerr not initialized",
            )

        item_type = req.media.media_type

        new_item = None

        if item_type == "movie":
            new_item = MediaItem(
                {
                    "tmdb_id": req.media.tmdbId,
                    "requested_by": "overseerr",
                    "overseerr_id": req.request.request_id if req.request else None,
                }
            )
        elif item_type == "tv":
            new_item = MediaItem(
                {
                    "tvdb_id": req.media.tvdbId,
                    "requested_by": "overseerr",
                    "overseerr_id": req.request.request_id if req.request else None,
                }
            )

        if not new_item:
            logger.error(
                f"Failed to create new item: TMDB ID {req.media.tmdbId}, TVDB ID {req.media.tvdbId}"
            )

            return OverseerrWebhookResponse(
                success=False,
                message="Failed to create new item",
            )

        di[Program].em.add_item(
            new_item,
            service=Overseerr.__class__.__name__,
        )

        return OverseerrWebhookResponse(success=True)
    except Exception as e:
        logger.error(f"Failed to process request: {e}")

        return OverseerrWebhookResponse(success=False)
