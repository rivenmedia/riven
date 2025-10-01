from typing import Literal, Optional

import requests
from fastapi import APIRouter, HTTPException, Request
from kink import di
from loguru import logger
from pydantic import BaseModel, Field, HttpUrl
from sqlalchemy import func, select

from program.apis import TraktAPI
from program.db import db_functions
from program.db.db import db
from program.media.item import Episode, MediaItem, Movie, Season, Show
from program.media.state import States
from program.services.downloaders import Downloader
from program.settings.manager import settings_manager
from program.utils import generate_api_key
from program.services.filesystem.filesystem_service import FilesystemService

from ..models.shared import MessageResponse

router = APIRouter(
    responses={404: {"description": "Not found"}},
)


@router.get("/health", operation_id="health")
async def health(request: Request) -> MessageResponse:
    return {
        "message": str(request.app.program.initialized),
    }


class DownloaderUserInfo(BaseModel):
    """Normalized downloader user information response"""
    service: Literal["realdebrid", "torbox", "alldebrid"]
    username: Optional[str] = None
    email: Optional[str] = None
    user_id: int | str
    premium_status: Literal["free", "premium"]
    premium_expires_at: Optional[str] = None
    premium_days_left: Optional[int] = None
    points: Optional[int] = None
    total_downloaded_bytes: Optional[int] = None
    cooldown_until: Optional[str] = None


class DownloaderUserInfoResponse(BaseModel):
    """Response containing user info for all initialized downloader services"""
    services: list[DownloaderUserInfo]


@router.get("/downloader_user_info", operation_id="download_user_info")
async def download_user_info(request: Request) -> DownloaderUserInfoResponse:
    """
    Get normalized user information from all initialized downloader services.

    Returns user info including premium status, expiration, and service-specific details
    for all active downloader services (Real-Debrid, TorBox, AllDebrid, etc.)
    """
    try:
        # Get the downloader service from the program
        downloader: Downloader = request.app.program.services.get(Downloader)

        if not downloader or not downloader.initialized:
            raise HTTPException(status_code=503, detail="No downloader service is initialized")

        # Get user info from all initialized services
        services_info = []

        for service in downloader.initialized_services:
            try:
                user_info = service.get_user_info()

                if user_info:
                    # Convert datetime objects to ISO strings for JSON serialization
                    services_info.append(DownloaderUserInfo(
                        service=user_info.service,
                        username=user_info.username,
                        email=user_info.email,
                        user_id=user_info.user_id,
                        premium_status=user_info.premium_status,
                        premium_expires_at=user_info.premium_expires_at.isoformat() if user_info.premium_expires_at else None,
                        premium_days_left=user_info.premium_days_left,
                        points=user_info.points,
                        total_downloaded_bytes=user_info.total_downloaded_bytes,
                        cooldown_until=user_info.cooldown_until.isoformat() if user_info.cooldown_until else None,
                    ))
                else:
                    logger.warning(f"Failed to get user info from {service.key}")
            except Exception as e:
                logger.error(f"Error getting user info from {service.key}: {e}")
                # Continue to next service instead of failing completely
                continue

        if not services_info:
            raise HTTPException(status_code=500, detail="Failed to retrieve user information from any downloader service")

        return DownloaderUserInfoResponse(services=services_info)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting downloader user info: {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

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
    incomplete_retries: dict[int, int] = Field(
        description="Media item log string: number of retries"
    )
    states: dict[States, int]


@router.get("/stats", operation_id="stats")
async def get_stats(_: Request) -> StatsResponse:
    payload = {}
    with db.Session() as session:
        # Ensure the connection is open for the entire duration of the session
        with session.connection().execution_options(stream_results=True) as conn:
            movies_symlinks = conn.execute(select(func.count(Movie.id)).where(Movie.filesystem_entry_id.isnot(None))).scalar_one()
            episodes_symlinks = conn.execute(select(func.count(Episode.id)).where(Episode.filesystem_entry_id.isnot(None))).scalar_one()
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
    events: dict[str, list[int]]

@router.get("/events", operation_id="events")
async def get_events(
    request: Request,
) -> EventResponse:
    events = request.app.program.em.get_event_updates()
    return EventResponse(events=events)

class MountResponse(BaseModel):
    files: dict[str, str]

@router.get("/mount", operation_id="mount")
async def get_mount_files() -> MountResponse:
    """Get all files in the Riven VFS mount."""
    import os

    mount_dir = str(settings_manager.settings.filesystem.mount_path)
    file_map = {}

    def scan_dir(path):
        with os.scandir(path) as entries:
            for entry in entries:
                if entry.is_file():
                    file_map[entry.name] = entry.path
                elif entry.is_dir():
                    scan_dir(entry.path)

    scan_dir(mount_dir)  # dict of `filename: filepath``
    return MountResponse(files=file_map)


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
            data=log_contents.encode("utf-8"),
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

class VFSStatsResponse(BaseModel):
    stats: dict[str, dict] = Field(description="VFS statistics")

@router.get(
    "/vfs_stats",
    summary="Get VFS Statistics",
    description="Get statistics about the VFS",
    operation_id="get_vfs_stats",
)
async def get_vfs_stats(request: Request) -> VFSStatsResponse:
    return VFSStatsResponse(stats=request.app.program.services[FilesystemService].riven_vfs._opener_stats)
