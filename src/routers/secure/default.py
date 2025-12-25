import platform
import psutil
from typing import Annotated, Any, Literal

import requests
from fastapi import APIRouter, HTTPException, Query
from kink import di
from kink.errors.service_error import ServiceError
from loguru import logger
from pydantic import BaseModel, Field, HttpUrl
from sqlalchemy import Date, cast, func, select

from program.apis import TraktAPI
from program.db import db_functions
from program.db.db import db_session
from program.media.item import Episode, MediaItem, Movie, Season, Show
from program.media.state import States
from program.program import Program
from program.settings import settings_manager
from program.utils import generate_api_key

from ..models.shared import MessageResponse

router = APIRouter(
    responses={404: {"description": "Not found"}},
)


def get_size(size_bytes: float, suffix: str = "B") -> str | None:
    factor = 1024
    for unit in ["", "K", "M", "G", "T", "P"]:
        if size_bytes < factor:
            return f"{size_bytes:.2f}{unit}{suffix}"
        size_bytes /= factor


@router.get("/health", operation_id="health")
async def health() -> MessageResponse:
    return MessageResponse(message=str(di[Program].initialized))


class DownloaderUserInfo(BaseModel):
    """Normalized downloader user information response"""

    service: Literal["realdebrid", "alldebrid", "debridlink"]
    username: str | None = None
    email: str | None = None
    user_id: int | str
    premium_status: Literal["free", "premium"]
    premium_expires_at: str | None = None
    premium_days_left: int | None = None
    points: int | None = None
    total_downloaded_bytes: int | None = None
    cooldown_until: str | None = None


class DownloaderUserInfoResponse(BaseModel):
    """Response containing user info for all initialized downloader services"""

    services: list[DownloaderUserInfo]


@router.get(
    "/downloader_user_info",
    operation_id="download_user_info",
    response_model=DownloaderUserInfoResponse,
)
async def download_user_info() -> DownloaderUserInfoResponse:
    """
    Get normalized user information from all initialized downloader services.

    Returns user info including premium status, expiration, and service-specific details
    for all active downloader services (Real-Debrid, Debrid-Link, AllDebrid, etc.)
    """
    try:
        # Get the downloader service from the program
        services = di[Program].services

        assert services

        downloader = services.downloader

        if not downloader or not downloader.initialized:
            raise HTTPException(
                status_code=503, detail="No downloader service is initialized"
            )

        # Get user info from all initialized services
        services_info = list[DownloaderUserInfo]()

        for service in downloader.initialized_services:
            try:
                user_info = service.get_user_info()

                if user_info:
                    # Convert datetime objects to ISO strings for JSON serialization
                    services_info.append(
                        DownloaderUserInfo(
                            service=user_info.service,
                            username=user_info.username,
                            email=user_info.email,
                            user_id=user_info.user_id,
                            premium_status=user_info.premium_status,
                            premium_expires_at=(
                                user_info.premium_expires_at.isoformat()
                                if user_info.premium_expires_at
                                else None
                            ),
                            premium_days_left=user_info.premium_days_left,
                            points=user_info.points,
                            total_downloaded_bytes=user_info.total_downloaded_bytes,
                            cooldown_until=(
                                user_info.cooldown_until.isoformat()
                                if user_info.cooldown_until
                                else None
                            ),
                        )
                    )
                else:
                    logger.warning(f"Failed to get user info from {service.key}")
            except Exception as e:
                logger.error(f"Error getting user info from {service.key}: {e}")
                # Continue to next service instead of failing completely
                continue

        if not services_info:
            raise HTTPException(
                status_code=500,
                detail="Failed to retrieve user information from any downloader service",
            )

        return DownloaderUserInfoResponse(services=services_info)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting downloader user info: {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.post(
    "/generateapikey",
    operation_id="generate_apikey",
    response_model=MessageResponse,
)
async def generate_apikey() -> MessageResponse:
    new_key = generate_api_key()
    settings_manager.settings.api_key = new_key
    settings_manager.save()

    return MessageResponse(message=new_key)


@router.get("/services", operation_id="services")
async def get_services() -> dict[str, bool]:
    data = dict[str, bool]()

    services = di[Program].services

    if services:
        for service in services.to_dict().values():
            if service.services:
                data.update(
                    {
                        sub_service.key: sub_service.initialized
                        for sub_service in service.services.values()
                    }
                )
            else:
                data[service.key] = service.initialized

    return data


class TraktOAuthInitiateResponse(BaseModel):
    auth_url: str


@router.get(
    "/trakt/oauth/initiate",
    operation_id="trakt_oauth_initiate",
    response_model=TraktOAuthInitiateResponse,
)
async def initiate_trakt_oauth() -> TraktOAuthInitiateResponse:
    try:
        trakt_api = di[TraktAPI]
    except ServiceError:
        raise HTTPException(status_code=404, detail="Trakt service not found")

    auth_url = trakt_api.build_oauth_url()

    return TraktOAuthInitiateResponse(auth_url=auth_url)


@router.get(
    "/trakt/oauth/callback",
    operation_id="trakt_oauth_callback",
    response_model=MessageResponse,
)
async def trakt_oauth_callback(
    code: Annotated[
        str,
        Query(description="The OAuth code returned by Trakt"),
    ],
) -> MessageResponse:
    try:
        trakt_api = di[TraktAPI]
    except ServiceError:
        raise HTTPException(status_code=404, detail="Trakt Api not found")

    trakt_api_key = settings_manager.settings.content.trakt.api_key

    if not trakt_api_key:
        raise HTTPException(
            status_code=404, detail="Trakt Api key not found in settings"
        )

    success = trakt_api.handle_oauth_callback(trakt_api_key, code)

    if success:
        return MessageResponse(message="OAuth token obtained successfully")
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
    states: dict[States, int]
    activity: Annotated[
        dict[str, int],
        Field(
            description="Dictionary mapping date strings to count of items requested on that day"
        ),
    ]
    media_year_releases: Annotated[
        list[dict[str, int | None]],
        Field(
            description="List of dictionaries with 'year' and 'count' keys representing media item releases per year"
        ),
    ]


@router.get(
    "/stats",
    operation_id="stats",
    response_model=StatsResponse,
)
async def get_stats() -> StatsResponse:
    """
    Produce aggregated statistics for the media library and its items.

    The response includes total counts for media items, movies, shows, seasons, and episodes; the total number of filesystem symlinks (determined by existence of FilesystemEntry records linked to movie or episode items); a mapping of each state to its item count; the number of incomplete items; and a mapping of incomplete item IDs to their scraped attempt counts.

    Returns:
        StatsResponse: Aggregated statistics with keys `total_items`, `total_movies`, `total_shows`, `total_seasons`, `total_episodes`, `total_symlinks`, `incomplete_items`, `incomplete_retries`, and `states`.
    """

    with db_session() as session:
        # Ensure the connection is open for the entire duration of the session
        with session.connection().execution_options(stream_results=True) as conn:
            from sqlalchemy import exists

            from program.media.filesystem_entry import FilesystemEntry

            movies_symlinks = conn.execute(
                select(func.count(Movie.id)).where(
                    exists().where(FilesystemEntry.media_item_id == Movie.id)
                )
            ).scalar_one()

            episodes_symlinks = conn.execute(
                select(func.count(Episode.id)).where(
                    exists().where(FilesystemEntry.media_item_id == Episode.id)
                )
            ).scalar_one()

            total_symlinks = movies_symlinks + episodes_symlinks

            total_movies = conn.execute(select(func.count(Movie.id))).scalar_one()
            total_shows = conn.execute(select(func.count(Show.id))).scalar_one()
            total_seasons = conn.execute(select(func.count(Season.id))).scalar_one()
            total_episodes = conn.execute(select(func.count(Episode.id))).scalar_one()
            total_items = conn.execute(select(func.count(MediaItem.id))).scalar_one()

            activity = dict[str, int]()

            activity_result = conn.execute(
                select(
                    cast(MediaItem.requested_at, Date).label("date"),
                    func.count(MediaItem.id).label("count"),
                )
                .where(MediaItem.requested_at.isnot(None))
                .group_by(cast(MediaItem.requested_at, Date))
                .order_by(cast(MediaItem.requested_at, Date))
            )

            for date, count in activity_result:
                activity[date.isoformat()] = count

            media_year_releases = list[dict[str, int | None]]()

            media_year_result = conn.execute(
                select(MediaItem.year, func.count(MediaItem.id)).group_by(
                    MediaItem.year
                )
            )

            for year, count in media_year_result:
                media_year_releases.append({"year": year, "count": count})

            # Use a server-side cursor for batch processing
            batch_size = 1000
            incomplete_retries = dict[int, int]()

            result = conn.execute(
                select(MediaItem.id, MediaItem.scraped_times).where(
                    MediaItem.last_state != States.Completed
                )
            )

            while True:
                batch = result.fetchmany(batch_size)

                if not batch:
                    break

                for media_item_id, scraped_times in batch:
                    incomplete_retries[media_item_id] = scraped_times

            states = dict[States, int]()

            for state in States:
                states[state] = conn.execute(
                    select(func.count(MediaItem.id)).where(
                        MediaItem.last_state == state
                    )
                ).scalar_one()

    return StatsResponse(
        total_items=total_items,
        total_movies=total_movies,
        total_shows=total_shows,
        total_seasons=total_seasons,
        total_episodes=total_episodes,
        total_symlinks=total_symlinks,
        incomplete_items=len(incomplete_retries),
        states=states,
        activity=activity,
        media_year_releases=media_year_releases,
    )


class LogsResponse(BaseModel):
    logs: list[str]


@router.get(
    "/logs",
    operation_id="logs",
    response_model=LogsResponse,
)
async def get_logs() -> LogsResponse:
    log_file_path: str | None = None

    for (
        handler  # pyright: ignore[reportUnknownVariableType]
    ) in (
        logger._core.handlers.values()  # pyright: ignore[reportAttributeAccessIssue, reportUnknownVariableType]
    ):
        if ".log" in handler._name:
            log_file_path = (  # pyright: ignore[reportUnknownVariableType]
                handler._sink._path
            )
            break

    if not log_file_path:
        raise HTTPException(status_code=404, detail="Log file handler not found")

    try:
        with open(
            log_file_path,  # pyright: ignore[reportUnknownArgumentType]
            "r",
        ) as log_file:
            # Read the file and split into lines without newline characters
            log_contents = log_file.read().splitlines()

        return LogsResponse(logs=log_contents)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read log file: {e}")


class EventResponse(BaseModel):
    events: dict[str, list[int]]


@router.get(
    "/events",
    operation_id="events",
    response_model=EventResponse,
)
async def get_events() -> EventResponse:
    events = di[Program].em.get_event_updates()

    return EventResponse(events=events)


class MountResponse(BaseModel):
    files: dict[str, str]


@router.get(
    "/mount",
    operation_id="mount",
    response_model=MountResponse,
)
async def get_mount_files() -> MountResponse:
    """Get all files in the Riven VFS mount."""

    import os

    mount_dir = str(settings_manager.settings.filesystem.mount_path)

    # `filename: filepath`
    file_map = dict[str, str]()

    def scan_dir(path: str):
        with os.scandir(path) as entries:
            for entry in entries:
                if entry.is_file():
                    file_map[entry.name] = entry.path
                elif entry.is_dir():
                    scan_dir(entry.path)

    scan_dir(mount_dir)

    return MountResponse(files=file_map)


class UploadLogsResponse(BaseModel):
    success: bool
    url: Annotated[
        HttpUrl,
        Field(
            description="URL to the uploaded log file. 50M Filesize limit. 180 day retention."
        ),
    ]


def _upload_logs_to_paste() -> HttpUrl:
    """
    Upload the current log file to paste.c-net.org.

    Returns:
        HttpUrl: The URL of the uploaded log file.

    Raises:
        HTTPException: If log file not found or upload fails.
    """
    log_file_path: str | None = None

    for handler in (  # pyright: ignore[reportUnknownVariableType]
        logger._core.handlers.values()  # pyright: ignore[reportAttributeAccessIssue, reportUnknownVariableType]
    ):
        if ".log" in handler._name:
            log_file_path = (  # pyright: ignore[reportUnknownVariableType]
                handler._sink._path
            )
            break

    if not log_file_path:
        raise HTTPException(status_code=500, detail="Log file handler not found")

    with open(
        log_file_path,  # pyright: ignore[reportUnknownArgumentType]
        "r",
    ) as log_file:
        log_contents = log_file.read()

    response = requests.post(
        "https://paste.c-net.org/",
        data=log_contents.encode("utf-8"),
        headers={"Content-Type": "text/plain", "x-uuid": ""},
        timeout=30,
    )

    if response.status_code == 200:
        url = HttpUrl(url=response.text.strip())
        logger.info(f"Uploaded log file to {url}")
        return url
    else:
        logger.error(f"Failed to upload log file: {response.status_code}")
        raise HTTPException(status_code=500, detail="Failed to upload log file")


@router.post(
    "/upload_logs",
    operation_id="upload_logs",
    response_model=UploadLogsResponse,
)
async def upload_logs() -> UploadLogsResponse:
    """Upload the latest log file to paste.c-net.org"""
    try:
        url = _upload_logs_to_paste()
        return UploadLogsResponse(success=True, url=url)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to read or upload log file: {e}")
        raise HTTPException(status_code=500, detail="Failed to read or upload log file")


class CalendarResponse(BaseModel):
    data: Annotated[
        dict[int, dict[str, Any]],
        Field(
            description="Dictionary with dates as keys and lists of media items as values"
        ),
    ]


@router.get(
    "/calendar",
    summary="Fetch Calendar",
    description="Fetch the calendar of all the items in the library",
    operation_id="fetch_calendar",
    response_model=CalendarResponse,
)
async def fetch_calendar() -> CalendarResponse:
    """Fetch the calendar of all the items in the library"""

    with db_session() as session:
        return CalendarResponse(data=db_functions.create_calendar(session))


class VFSStatsResponse(BaseModel):
    stats: Annotated[
        dict[str, dict[str, Any]],
        Field(description="VFS statistics"),
    ]


@router.get(
    "/vfs_stats",
    summary="Get VFS Statistics",
    description="Get statistics about the VFS",
    operation_id="get_vfs_stats",
    response_model=VFSStatsResponse,
)
async def get_vfs_stats() -> VFSStatsResponse:
    """Get statistics about the VFS"""

    services = di[Program].services

    assert services

    vfs = services.filesystem.riven_vfs

    assert vfs

    return VFSStatsResponse(stats=vfs.opener_stats)


class DebugResponse(BaseModel):
    success: bool
    log_url: Annotated[
        HttpUrl | None,
        Field(description="URL to the uploaded log file"),
    ]
    db_backup_filename: Annotated[
        str | None,
        Field(description="Filename of the database backup"),
    ]
    system_info: Annotated[
        dict[str, Any],
        Field(description="System information"),
    ]
    errors: Annotated[
        list[str],
        Field(description="List of any errors that occurred"),
    ] = []


@router.post(
    "/debug",
    summary="Generate Debug Bundle",
    description="Upload logs and create database backup for debugging purposes",
    operation_id="generate_debug_bundle",
    response_model=DebugResponse,
)
async def generate_debug_bundle() -> DebugResponse:
    """
    Generate a debug bundle containing uploaded logs and database backup.

    This endpoint:
    1. Uploads the current log file to paste.c-net.org
    2. Creates a database backup snapshot
    3. Returns system information

    Returns the log URL and backup filename.
    """
    from program.utils.cli import snapshot_database

    errors = list[str]()
    log_url: HttpUrl | None = None
    db_backup_filename: str | None = None

    try:
        log_url = _upload_logs_to_paste()
    except HTTPException as e:
        errors.append(e.detail)
    except Exception as e:
        logger.error(f"Debug: Failed to upload logs: {e}")
        errors.append(f"Failed to upload logs: {str(e)}")

    try:
        db_backup_filename = snapshot_database()
        if db_backup_filename:
            logger.info(f"Debug: Created database backup: {db_backup_filename}")
        else:
            errors.append("Failed to create database backup")
    except Exception as e:
        logger.error(f"Debug: Failed to create database backup: {e}")
        errors.append(f"Failed to create database backup: {str(e)}")

    success = log_url is not None and db_backup_filename is not None

    system_info = {
        "platform": platform.platform(),
        "python_version": platform.python_version(),
        "cpu_count": psutil.cpu_count(),
        "load_avg": psutil.getloadavg(),
        "memory": get_size(psutil.virtual_memory().total),
        "swap": get_size(psutil.swap_memory().total),
        "disk": get_size(psutil.disk_usage("/").total),
    }

    return DebugResponse(
        success=success,
        log_url=log_url,
        db_backup_filename=db_backup_filename,
        system_info=system_info,
        errors=errors,
    )
