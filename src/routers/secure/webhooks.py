from typing import Any, Dict, Optional

import pydantic
from fastapi import APIRouter, Request, HTTPException
from kink import di
from loguru import logger
from pydantic import BaseModel
from requests import RequestException

from program.apis.trakt_api import TraktAPI
from program.media.item import MediaItem
from program.services.content.overseerr import Overseerr
from program.services.indexers.trakt import TraktIndexer
from program.managers.event_manager import Event

from ..models.overseerr import OverseerrWebhook

router = APIRouter(
    prefix="/webhook",
    responses={404: {"description": "Not found"}},
)


class ShowUpdateTrigger(BaseModel):
    """Model for external show update triggers."""
    imdb_id: Optional[str] = None
    trakt_id: Optional[int] = None
    tvdb_id: Optional[int] = None
    tmdb_id: Optional[int] = None
    title: Optional[str] = None
    year: Optional[int] = None
    reason: Optional[str] = "external_trigger"  # Reason for the update
    priority: Optional[str] = "high"  # Priority level: low, medium, high


class BatchShowUpdateTrigger(BaseModel):
    """Model for batch show update triggers."""
    shows: list[ShowUpdateTrigger]
    reason: Optional[str] = "batch_external_trigger"


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

    new_item = MediaItem({"imdb_id": imdb_id, "requested_by": "overseerr", "overseerr_id": req.request.request_id})
    request.app.program.em.add_item(new_item, service="Overseerr")
    return {"success": True}


def get_imdbid_from_overseerr(req: OverseerrWebhook) -> str:
    """Get the imdb_id from the Overseerr webhook"""
    imdb_id = req.media.imdbId
    trakt_api = di[TraktAPI]
    if not imdb_id:
        try:
            _type = req.media.media_type
            if _type == "tv":
                _type = "show"
            imdb_id = trakt_api.get_imdbid_from_tmdb(str(req.media.tmdbId), type=_type)
            if not imdb_id or not imdb_id.startswith("tt"):
                imdb_id = trakt_api.get_imdbid_from_tvdb(str(req.media.tvdbId), type=_type)
        except RequestException:
            pass
    return imdb_id


@router.post("/show-update")
async def trigger_show_update(trigger: ShowUpdateTrigger) -> Dict[str, Any]:
    """
    External webhook to trigger immediate show re-indexing.
    Useful for integrations with external services that detect new seasons/episodes.
    """
    try:
        from program import Program
        program = di[Program]

        if not program or not program.initialized:
            raise HTTPException(status_code=503, detail="Program not initialized")

        # Find the show in the database
        show = _find_show_by_identifiers(trigger)

        if not show:
            logger.warning(f"Show not found for external trigger: {trigger.model_dump()}")
            return {
                "success": False,
                "message": "Show not found in database",
                "trigger": trigger.model_dump()
            }

        # Create high-priority event for immediate processing
        event = Event(
            emitted_by="ExternalTrigger",
            item_id=show.id,
            run_at=0  # Immediate execution
        )

        # Add to event queue with high priority
        program.em.add_event(event)

        logger.info(f"External trigger: queued immediate update for {show.log_string} (reason: {trigger.reason})")

        return {
            "success": True,
            "message": f"Show update queued for immediate processing",
            "show": {
                "id": show.id,
                "title": show.title,
                "imdb_id": show.imdb_id
            },
            "trigger": trigger.model_dump()
        }

    except Exception as e:
        logger.error(f"Error processing external show update trigger: {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.post("/show-update/batch")
async def trigger_batch_show_update(batch_trigger: BatchShowUpdateTrigger) -> Dict[str, Any]:
    """
    External webhook to trigger batch show re-indexing.
    Useful for bulk updates from external services.
    """
    try:
        from program import Program
        program = di[Program]

        if not program or not program.initialized:
            raise HTTPException(status_code=503, detail="Program not initialized")

        results = []
        events_created = 0

        for trigger in batch_trigger.shows:
            try:
                show = _find_show_by_identifiers(trigger)

                if show:
                    event = Event(
                        emitted_by="ExternalBatchTrigger",
                        item_id=show.id,
                        run_at=0  # Immediate execution
                    )

                    program.em.add_event(event)
                    events_created += 1

                    results.append({
                        "success": True,
                        "show": {
                            "id": show.id,
                            "title": show.title,
                            "imdb_id": show.imdb_id
                        },
                        "trigger": trigger.model_dump()
                    })
                else:
                    results.append({
                        "success": False,
                        "message": "Show not found",
                        "trigger": trigger.model_dump()
                    })

            except Exception as e:
                logger.error(f"Error processing show in batch trigger: {e}")
                results.append({
                    "success": False,
                    "message": f"Error: {str(e)}",
                    "trigger": trigger.model_dump()
                })

        logger.info(f"External batch trigger: queued {events_created} show updates (reason: {batch_trigger.reason})")

        return {
            "success": True,
            "message": f"Batch processing completed: {events_created} shows queued",
            "total_shows": len(batch_trigger.shows),
            "successful_triggers": events_created,
            "results": results
        }

    except Exception as e:
        logger.error(f"Error processing external batch show update trigger: {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


def _find_show_by_identifiers(trigger: ShowUpdateTrigger) -> Optional[MediaItem]:
    """
    Find a show in the database using the provided identifiers.

    Args:
        trigger: ShowUpdateTrigger with identifiers

    Returns:
        MediaItem if found, None otherwise
    """
    from program.db.db_functions import get_item_by_external_id

    # Try different identifiers in order of preference
    identifiers = [
        ("imdb_id", trigger.imdb_id),
        ("trakt_id", trigger.trakt_id),
        ("tvdb_id", trigger.tvdb_id),
        ("tmdb_id", trigger.tmdb_id)
    ]

    for id_type, id_value in identifiers:
        if id_value:
            try:
                show = get_item_by_external_id(id_value, id_type)
                if show and show.type == "show":
                    return show
            except Exception as e:
                logger.debug(f"Error searching by {id_type}={id_value}: {e}")
                continue

    # Fallback: search by title and year if provided
    if trigger.title:
        try:
            from program.db.db import db
            from sqlalchemy import and_

            with db.Session() as session:
                query = session.query(MediaItem).filter(
                    and_(
                        MediaItem.type == "show",
                        MediaItem.title.ilike(f"%{trigger.title}%")
                    )
                )

                if trigger.year:
                    # Extract year from aired_at if available
                    query = query.filter(
                        MediaItem.year == trigger.year
                    )

                show = query.first()
                if show:
                    return show

        except Exception as e:
            logger.debug(f"Error searching by title/year: {e}")

    return None