from datetime import datetime

import pydantic
import requests
from fastapi import APIRouter, Request
from program.indexers.trakt import get_imdbid_from_tmdb
from program.settings.manager import settings_manager
from utils.logger import logger

from .overseerr_models import OverseerrWebhook

router = APIRouter(
    responses={404: {"description": "Not found"}},
)


@router.get("/")
async def root():
    return {
        "success": True,
        "message": "Iceburg is running!",
        "version": settings_manager.settings.version,
    }


@router.get("/health")
async def health(request: Request):
    return {
        "success": True,
        "message": request.app.program.initialized,
    }


@router.get("/user")
async def get_rd_user():
    api_key = settings_manager.settings.real_debrid.api_key
    headers = {"Authorization": f"Bearer {api_key}"}
    response = requests.get(
        "https://api.real-debrid.com/rest/1.0/user", headers=headers, timeout=10
    )
    return response.json()


@router.get("/services")
async def get_services(request: Request):
    data = {}
    if hasattr(request.app.program, "services"):
        for service in request.app.program.services.values():
            data[service.key] = service.initialized
            if not hasattr(service, "services"):
                continue
            for sub_service in service.services.values():
                data[sub_service.key] = sub_service.initialized
    return {"success": True, "data": data}

@router.post("/overseerr")
async def overseerr_webhook(request: Request):
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
