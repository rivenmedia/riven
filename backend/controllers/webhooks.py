import json
from datetime import datetime

import pydantic
from fastapi import APIRouter, HTTPException, Request
from program.indexers.trakt import get_imdbid_from_tmdb
from program.settings.manager import settings_manager
from utils.logger import logger

from .models.overseerr import OverseerrWebhook

router = APIRouter(
    responses={404: {"description": "Not found"}},
)


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


@router.post("/plex")
async def plex_webhook(request: Request):
    form = await request.form()
    payload = form.get("payload")
    if not payload:
        logger.error("Missing payload in form data")
        raise HTTPException(status_code=400, detail="Missing payload in form data")
    
    try:
        payload_dict = json.loads(payload)
        plex_payload = PlexPayload(**payload_dict)
    except json.JSONDecodeError:
        logger.error("Invalid JSON payload")
        raise HTTPException(status_code=400, detail="Invalid JSON payload")
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

    if plex_payload.event == "media.play":
        logger.log("PLEX", f"Event: {plex_payload.event}")
        logger.log("PLEX", f"User: {plex_payload.Account.title} (ID: {plex_payload.Account.id})")
        logger.log("PLEX", f"Media Title: {plex_payload.Metadata.title}")
        logger.log("PLEX", f"Media Type: {plex_payload.Metadata.type}")
        logger.log("PLEX", f"Year: {plex_payload.Metadata.year}")

    logger.log("EVENT", f"Event: {plex_payload.event}")
    # Assuming you have a function to log the payload
    # log_plex_payload(plex_payload)
    
    return {"status": "received"}



### Plex Models

from pydantic import BaseModel


class Account(BaseModel):
    id: int
    thumb: str
    title: str

class Server(BaseModel):
    title: str
    uuid: str

class Player(BaseModel):
    local: bool
    publicAddress: str
    title: str
    uuid: str

class Metadata(BaseModel):
    librarySectionType: str
    ratingKey: str
    key: str
    guid: str
    type: str
    title: str
    librarySectionTitle: str
    librarySectionID: int
    librarySectionKey: str
    contentRating: str
    summary: str
    rating: float
    audienceRating: float
    year: int
    tagline: str
    thumb: str

class PlexPayload(BaseModel):
    event: str
    user: bool
    owner: bool
    Account: Account
    Server: Server
    Player: Player
    Metadata: Metadata

class TraktSettings(BaseModel):
    trakt_id: str
    trakt_secret: str

    class Config:
        env_file = ".env"

settings = TraktSettings()
