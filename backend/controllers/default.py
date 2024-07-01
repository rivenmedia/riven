import time

import requests
from fastapi import APIRouter, HTTPException, Request
from program.content.trakt import TraktContent
from program.media.state import States
from program.scrapers import Scraping
from program.settings.manager import settings_manager

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
async def get_stats(request: Request):
    payload = {}

    total_items = len(request.app.program.media_items._items)
    total_movies = len(request.app.program.media_items._movies)
    total_shows = len(request.app.program.media_items._shows)
    total_seasons = len(request.app.program.media_items._seasons)
    total_episodes = len(request.app.program.media_items._episodes)

    _incomplete_items = request.app.program.media_items.get_incomplete_items()

    incomplete_retries = {}
    for _, item in _incomplete_items.items():
        incomplete_retries[item.log_string] = item.scraped_times

    states = {}
    for state in States:
        states[state] = request.app.program.media_items.count(state)

    payload["total_items"] = total_items
    payload["total_movies"] = total_movies
    payload["total_shows"] = total_shows
    payload["total_seasons"] = total_seasons
    payload["total_episodes"] = total_episodes
    payload["incomplete_items"] = len(_incomplete_items)
    payload["incomplete_retries"] = incomplete_retries
    payload["states"] = states

    return {"success": True, "data": payload}

@router.get("/scrape/{item_id:path}")
async def scrape_item(item_id: str, request: Request):
    item = request.app.program.media_items.get_item(item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Item not found")
    
    scraper = request.app.program.services.get(Scraping)
    if scraper is None:
        raise HTTPException(status_code=404, detail="Scraping service not found")

    time_now = time.time()
    scraped_results = scraper.scrape(item, log=False)
    time_end = time.time()
    duration = time_end - time_now

    results = {}
    for hash, torrent in scraped_results.items():
        results[hash] = {
            "title": torrent.data.parsed_title,
            "raw_title": torrent.raw_title,
            "rank": torrent.rank,
        }

    return {"success": True, "total": len(results), "duration": round(duration, 3), "results": results}