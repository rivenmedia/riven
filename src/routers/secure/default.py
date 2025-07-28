from typing import Literal, Optional
import threading
import time

import requests
from fastapi import APIRouter, HTTPException, Request
from kink import di
from loguru import logger
from pydantic import BaseModel, Field, HttpUrl
from sqlalchemy import func, select

from program.apis import TraktAPI
from program.db.db import db
from program.media.item import Episode, MediaItem, Movie, Season, Show
from program.media.state import States
from program.settings.manager import settings_manager
from program.utils import generate_api_key
from program.db import db_functions

from ..models.shared import MessageResponse

router = APIRouter(
    responses={404: {"description": "Not found"}},
)

# Simple cache for mount scanning
_mount_scan_cache = {}
_cache_lock = threading.Lock()

def _get_cached_mount_scan(cache_key: str) -> Optional[dict]:
    """Get cached mount scan result if still valid."""
    with _cache_lock:
        if cache_key in _mount_scan_cache:
            result, expiry = _mount_scan_cache[cache_key]
            if time.time() < expiry:
                return result
            else:
                del _mount_scan_cache[cache_key]
    return None

def _cache_mount_scan(cache_key: str, result: dict, ttl: int = 300):
    """Cache mount scan result with TTL."""
    with _cache_lock:
        _mount_scan_cache[cache_key] = (result, time.time() + ttl)

        # Limit cache size to prevent memory issues
        if len(_mount_scan_cache) > 10:
            # Remove oldest entries
            oldest_key = min(_mount_scan_cache.keys(),
                           key=lambda k: _mount_scan_cache[k][1])
            del _mount_scan_cache[oldest_key]


@router.get("/health", operation_id="health")
async def health(request: Request) -> MessageResponse:
    return {
        "message": str(request.app.program.initialized),
    }


class RDUser(BaseModel):
    id: int
    username: str
    email: str
    points: int = Field(description="User's RD points")
    locale: str
    avatar: str = Field(description="URL to the user's avatar")
    type: Literal["free", "premium"]
    premium: int = Field(description="Premium subscription left in seconds")


@router.get("/rd", operation_id="rd")
async def get_rd_user() -> RDUser:
    api_key = settings_manager.settings.downloaders.real_debrid.api_key
    headers = {"Authorization": f"Bearer {api_key}"}

    proxy = (
        settings_manager.settings.downloaders.proxy_url
        if settings_manager.settings.downloaders.proxy_url
        else None
    )

    response = requests.get(
        "https://api.real-debrid.com/rest/1.0/user",
        headers=headers,
        proxies=proxy if proxy else None,
        timeout=10,
    )

    if response.status_code != 200:
        return {"success": False, "message": response.json()}

    return response.json()

@router.post("/generateapikey", operation_id="generateapikey")
async def generate_apikey() -> MessageResponse:
    new_key = generate_api_key()
    settings_manager.settings.api_key = new_key
    settings_manager.save()
    return { "message": new_key}


@router.get("/services", operation_id="services")
async def get_services(request: Request) -> dict[str, bool]:
    data = {}
    if hasattr(request.app.program, "services"):
        for service in request.app.program.all_services.values():
            data[service.key] = service.initialized
            if not hasattr(service, "services"):
                continue
            for sub_service in service.services.values():
                data[sub_service.key] = sub_service.initialized
    return data


class TraktOAuthInitiateResponse(BaseModel):
    auth_url: str


@router.get("/trakt/oauth/initiate", operation_id="trakt_oauth_initiate")
async def initiate_trakt_oauth(request: Request) -> TraktOAuthInitiateResponse:
    trakt_api = di[TraktAPI]
    if trakt_api is None:
        raise HTTPException(status_code=404, detail="Trakt service not found")
    auth_url = trakt_api.perform_oauth_flow()
    return {"auth_url": auth_url}


@router.get("/trakt/oauth/callback", operation_id="trakt_oauth_callback")
async def trakt_oauth_callback(code: str, request: Request) -> MessageResponse:
    trakt_api = di[TraktAPI]
    trakt_api_key = settings_manager.settings.content.trakt.api_key
    if trakt_api is None:
        raise HTTPException(status_code=404, detail="Trakt Api not found")
    if trakt_api_key is None:
        raise HTTPException(status_code=404, detail="Trakt Api key not found in settings")
    success = trakt_api.handle_oauth_callback(trakt_api_key, code)
    if success:
        return {"message": "OAuth token obtained successfully"}
    else:
        raise HTTPException(status_code=400, detail="Failed to obtain OAuth token")


class StatsResponse(BaseModel):
    total_items: int
    total_movies: int
    total_shows: int
    total_seasons: int
    total_episodes: int
    total_symlinks: int
    incomplete_items: int
    incomplete_retries: dict[str, int] = Field(
        description="Media item log string: number of retries"
    )
    states: dict[States, int]


@router.get("/stats", operation_id="stats")
async def get_stats(_: Request) -> StatsResponse:
    payload = {}
    with db.Session() as session:
        # Ensure the connection is open for the entire duration of the session
        with session.connection().execution_options(stream_results=True) as conn:
            movies_symlinks = conn.execute(select(func.count(Movie.id)).where(Movie.symlinked == True)).scalar_one()
            episodes_symlinks = conn.execute(select(func.count(Episode.id)).where(Episode.symlinked == True)).scalar_one()
            total_symlinks = movies_symlinks + episodes_symlinks

            total_movies = conn.execute(select(func.count(Movie.id))).scalar_one()
            total_shows = conn.execute(select(func.count(Show.id))).scalar_one()
            total_seasons = conn.execute(select(func.count(Season.id))).scalar_one()
            total_episodes = conn.execute(select(func.count(Episode.id))).scalar_one()
            total_items = conn.execute(select(func.count(MediaItem.id))).scalar_one()

            # Use a server-side cursor for batch processing
            incomplete_retries = {}
            batch_size = 1000

            result = conn.execute(
                select(MediaItem.id, MediaItem.scraped_times)
                .where(MediaItem.last_state != States.Completed)
            )

            while True:
                batch = result.fetchmany(batch_size)
                if not batch:
                    break

                for media_item_id, scraped_times in batch:
                    incomplete_retries[media_item_id] = scraped_times

            states = {}
            for state in States:
                states[state] = conn.execute(select(func.count(MediaItem.id)).where(MediaItem.last_state == state)).scalar_one()

            payload["total_items"] = total_items
            payload["total_movies"] = total_movies
            payload["total_shows"] = total_shows
            payload["total_seasons"] = total_seasons
            payload["total_episodes"] = total_episodes
            payload["total_symlinks"] = total_symlinks
            payload["incomplete_items"] = len(incomplete_retries)
            payload["incomplete_retries"] = incomplete_retries
            payload["states"] = states

    return StatsResponse(**payload)

class LogsResponse(BaseModel):
    logs: list[str]

@router.get("/logs", operation_id="logs")
async def get_logs() -> LogsResponse:
    log_file_path = None
    for handler in logger._core.handlers.values():
        if ".log" in handler._name:
            log_file_path = handler._sink._path
            break

    if not log_file_path:
        raise HTTPException(status_code=404, detail="Log file handler not found")

    try:
        with open(log_file_path, "r") as log_file:
            log_contents = log_file.read().splitlines()  # Read the file and split into lines without newline characters
        return LogsResponse(logs=log_contents)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read log file: {e}")


class EventResponse(BaseModel):
    events: dict[str, list[str]]

@router.get("/events", operation_id="events")
async def get_events(
    request: Request,
) -> EventResponse:
    events = request.app.program.em.get_event_updates()
    return EventResponse(events=events)

class MountResponse(BaseModel):
    files: dict[str, str]

@router.get("/mount", operation_id="mount")
async def get_rclone_files() -> MountResponse:
    """Get all files in the rclone mount with optimized scanning and caching."""
    import os
    import time
    from pathlib import Path

    rclone_dir = settings_manager.settings.symlink.rclone_path

    # Use cached result if available and recent (5 minutes)
    cache_key = f"mount_scan_{rclone_dir}"
    cached_result = _get_cached_mount_scan(cache_key)
    if cached_result:
        return MountResponse(files=cached_result)

    file_map = {}

    def scan_dir_optimized(path):
        """Optimized directory scanning using os.scandir with better error handling."""
        try:
            with os.scandir(path) as entries:
                # Process entries in batches to reduce memory usage
                batch = []
                for entry in entries:
                    batch.append(entry)

                    # Process batch when it reaches 100 entries
                    if len(batch) >= 100:
                        _process_entry_batch(batch, file_map)
                        batch = []

                # Process remaining entries
                if batch:
                    _process_entry_batch(batch, file_map)

        except (OSError, PermissionError) as e:
            logger.warning(f"Error scanning directory {path}: {e}")

    def _process_entry_batch(entries, file_map):
        """Process a batch of directory entries efficiently."""
        for entry in entries:
            try:
                if entry.is_file(follow_symlinks=False):
                    file_map[entry.name] = entry.path
                elif entry.is_dir(follow_symlinks=False):
                    scan_dir_optimized(entry.path)
            except (OSError, PermissionError):
                # Skip entries that can't be accessed
                continue

    # Perform the scan
    scan_dir_optimized(rclone_dir)

    # Cache the result for 5 minutes
    _cache_mount_scan(cache_key, file_map, ttl=300)

    return MountResponse(files=file_map)


@router.get("/performance", operation_id="performance")
async def get_performance_metrics():
    """Get system performance metrics and statistics."""
    try:
        # Import here to avoid circular imports
        from main import performance_monitor

        stats = performance_monitor.get_stats()

        # Add system-level metrics
        import psutil
        import os

        # Get current process info
        process = psutil.Process(os.getpid())

        system_stats = {
            'memory_usage_mb': process.memory_info().rss / 1024 / 1024,
            'cpu_percent': process.cpu_percent(),
            'open_files': len(process.open_files()),
            'threads': process.num_threads(),
            'uptime_seconds': time.time() - process.create_time()
        }

        # Add database connection pool stats if available
        try:
            from program.db.db import db
            pool_stats = {
                'pool_size': db.engine.pool.size(),
                'checked_in': db.engine.pool.checkedin(),
                'checked_out': db.engine.pool.checkedout(),
                'overflow': db.engine.pool.overflow(),
                'invalid': db.engine.pool.invalid()
            }
            system_stats['database_pool'] = pool_stats
        except Exception:
            pass

        return {
            'performance': stats,
            'system': system_stats,
            'timestamp': time.time()
        }

    except Exception as e:
        logger.error(f"Error getting performance metrics: {e}")
        return {"error": "Failed to retrieve performance metrics"}


class UploadLogsResponse(BaseModel):
    success: bool
    url: HttpUrl = Field(description="URL to the uploaded log file. 50M Filesize limit. 180 day retention.")

@router.post("/upload_logs", operation_id="upload_logs")
async def upload_logs() -> UploadLogsResponse:
    """Upload the latest log file to paste.c-net.org"""

    log_file_path = None
    for handler in logger._core.handlers.values():
        if ".log" in handler._name:
            log_file_path = handler._sink._path
            break

    if not log_file_path:
        raise HTTPException(status_code=500, detail="Log file handler not found")

    try:
        with open(log_file_path, "r") as log_file:
            log_contents = log_file.read()

        response = requests.post(
            "https://paste.c-net.org/",
            data=log_contents.encode('utf-8'),
            headers={"Content-Type": "text/plain"}
        )

        if response.status_code == 200:
            logger.info(f"Uploaded log file to {response.text.strip()}")
            return UploadLogsResponse(success=True, url=response.text.strip())
        else:
            logger.error(f"Failed to upload log file: {response.status_code}")
            raise HTTPException(status_code=500, detail="Failed to upload log file")

    except Exception as e:
        logger.error(f"Failed to read or upload log file: {e}")
        raise HTTPException(status_code=500, detail="Failed to read or upload log file")

class CalendarResponse(BaseModel):
    data: dict

@router.get(
    "/calendar",
    summary="Fetch Calendar",
    description="Fetch the calendar of all the items in the library",
    operation_id="fetch_calendar",
)
async def fetch_calendar(_: Request) -> CalendarResponse:
    """Fetch the calendar of all the items in the library"""
    with db.Session() as session:
        return CalendarResponse(
            data=db_functions.create_calendar(session)
        )
