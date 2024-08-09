import time

import program.db.db_functions as DB
import requests
from fastapi import APIRouter, HTTPException, Request
from program.content.trakt import TraktContent
from program.db.db import db
from program.media.item import Episode, MediaItem, Movie, Season, Show
from program.media.state import States
from program.scrapers import Scraping
from program.settings.manager import settings_manager
from sqlalchemy import func, select

router = APIRouter(
    responses={404: {"description": "Not found"}},
)


@router.get("/")
async def root():
    return {
        "success": True,
        "message": "Riven is running!",
        "version": settings_manager.settings.version,
    }


@router.get("/health")
async def health(request: Request):
    return {
        "success": True,
        "message": request.app.program.initialized,
    }


@router.get("/rd")
async def get_rd_user():
    api_key = settings_manager.settings.downloaders.real_debrid.api_key
    headers = {"Authorization": f"Bearer {api_key}"}

    proxy = settings_manager.settings.downloaders.real_debrid.proxy_url if settings_manager.settings.downloaders.real_debrid.proxy_enabled else None

    response = requests.get(
        "https://api.real-debrid.com/rest/1.0/user",
        headers=headers,
        proxies=proxy if proxy else None,
        timeout=10
    )

    if response.status_code != 200:
        return {"success": False, "message": response.json()}

    return {
        "success": True,
        "data": response.json(),
    }


@router.get("/torbox")
async def get_torbox_user():
    api_key = settings_manager.settings.downloaders.torbox.api_key
    headers = {"Authorization": f"Bearer {api_key}"}
    response = requests.get(
        "https://api.torbox.app/v1/api/user/me", headers=headers, timeout=10
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


@router.get("/trakt/oauth/initiate")
async def initiate_trakt_oauth(request: Request):
    trakt = request.app.program.services.get(TraktContent)
    if trakt is None:
        raise HTTPException(status_code=404, detail="Trakt service not found")
    auth_url = trakt.perform_oauth_flow()
    return {"auth_url": auth_url}


@router.get("/trakt/oauth/callback")
async def trakt_oauth_callback(code: str, request: Request):
    trakt = request.app.program.services.get(TraktContent)
    if trakt is None:
        raise HTTPException(status_code=404, detail="Trakt service not found")
    success = trakt.handle_oauth_callback(code)
    if success:
        return {"success": True, "message": "OAuth token obtained successfully"}
    else:
        raise HTTPException(status_code=400, detail="Failed to obtain OAuth token")


@router.get("/stats")
async def get_stats(_: Request):
    payload = {}
    with db.Session() as session:

        movies_symlinks = session.execute(select(func.count(Movie._id)).where(Movie.symlinked == True)).scalar_one()
        episodes_symlinks = session.execute(select(func.count(Episode._id)).where(Episode.symlinked == True)).scalar_one()
        total_symlinks = movies_symlinks + episodes_symlinks

        total_movies = session.execute(select(func.count(Movie._id))).scalar_one()
        total_shows = session.execute(select(func.count(Show._id))).scalar_one()
        total_seasons = session.execute(select(func.count(Season._id))).scalar_one()
        total_episodes = session.execute(select(func.count(Episode._id))).scalar_one()
        total_items = session.execute(select(func.count(MediaItem._id))).scalar_one()
        _incomplete_items = session.execute(select(MediaItem).where(MediaItem.last_state != "Completed")).unique().scalars().all()

        incomplete_retries = {}
        for item in _incomplete_items:
            incomplete_retries[item.log_string] = item.scraped_times

        states = {}
        for state in States:
            states[state] = session.execute(select(func.count(MediaItem._id)).where(MediaItem.last_state == state.value)).scalar_one()

        payload["total_items"] = total_items
        payload["total_movies"] = total_movies
        payload["total_shows"] = total_shows
        payload["total_seasons"] = total_seasons
        payload["total_episodes"] = total_episodes
        payload["total_symlinks"] = total_symlinks
        payload["incomplete_items"] = len(_incomplete_items)
        payload["incomplete_retries"] = incomplete_retries
        payload["states"] = states

        return {"success": True, "data": payload}