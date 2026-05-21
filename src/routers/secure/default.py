import platform
import psutil
import threading
import time
from datetime import datetime
from typing import Annotated, Any, Literal

import requests
from fastapi import APIRouter, HTTPException, Query
from fastapi.concurrency import run_in_threadpool
from kink import di
from kink.errors.service_error import ServiceError
from loguru import logger
from pydantic import BaseModel, Field, HttpUrl
from sqlalchemy import Date, cast, func, select
from sqlalchemy.orm import noload

from program.apis import TraktAPI
from program.db import db_functions
from program.db.db import db_session
from program.media.media_entry import MediaEntry
from program.media.item import Episode, MediaItem, Movie, Season, Show
from program.media.state import States
from program.program import Program
from program.services.rate_limit import RateLimitService, get_rate_limit_service
from program.settings import settings_manager
from program.utils import format_api_datetime, generate_api_key

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

    service: Literal["realdebrid", "alldebrid", "debridlink", "torbox"]
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


USER_INFO_CACHE_TTL_SECONDS = 60.0
SCRAPED_COUNT_CACHE_TTL_SECONDS = 30.0

_user_info_cache_lock = threading.Lock()
_user_info_cache: tuple[float, DownloaderUserInfoResponse] | None = None

_scraped_count_cache_lock = threading.Lock()
_scraped_count_cache: tuple[float, int] | None = None


class DownloaderServiceStatus(BaseModel):
    key: str
    available: bool
    cooldown_until: str | None = None


class LimiterSnapshotResponse(BaseModel):
    key: str
    label: str
    owner: str
    tokens: float
    capacity: float
    rate_per_second: float
    utilization_pct: float
    next_token_in_seconds: float
    priority: str
    warn_at_pct: float
    breaker_state: str
    breaker_failures: int
    breaker_recovery_in_seconds: float


class RateLimitsResponse(BaseModel):
    limiters: list[LimiterSnapshotResponse]
    by_owner: dict[str, list[str]]


class DownloaderQueueStats(BaseModel):
    scraped_queued: int
    scraped_ready: int = 0
    deferred: int
    total_queued: int = 0
    downloader_emitted: int = Field(
        default=0,
        description="Queued items emitted by Downloader (re-queue); same as queue_by_source.Downloader",
    )
    queue_by_source: dict[str, int] = Field(
        default_factory=dict,
        description="Deduped downloader-relevant queue counts by emitted_by source",
    )
    next_ready_at: str | None = None
    next_ready_in_seconds: float | None = Field(
        default=None,
        description="Seconds until the soonest deferred item becomes due (server clock)",
    )
    queue_truncated: bool = False
    scraped_in_library: int = Field(
        default=0,
        description="Library items (all types) currently in the Scraped state",
    )


class InFlightItemResponse(BaseModel):
    id: int
    title: str
    type: str
    parent_title: str | None = None
    season_number: int | None = None
    episode_number: int | None = None
    state: str | None = None
    activity: str | None = Field(
        default=None,
        description="Live downloader step while this job is in flight",
    )


class QueuedItemResponse(InFlightItemResponse):
    run_at: str
    queued_at: str
    scraped_at: str | None = None
    deferred: bool
    wait_seconds: float
    emitted_by: str


class LastDownloaderJobResponse(BaseModel):
    item: InFlightItemResponse | None = None
    completed_at: str | None = None
    outcome: Literal["success", "deferred", "failed", "skipped"] | None = None
    detail: str | None = None
    service: str | None = None


# Status endpoint only needs titles/metadata — avoid selectin-loading streams/subtitles.
_MEDIA_ITEM_STATUS_LOAD_OPTIONS = (
    noload(MediaItem.streams),
    noload(MediaItem.blacklisted_streams),
    noload(MediaItem.filesystem_entries),
    noload(MediaItem.subtitles),
)


def _item_display_rows(
    item_ids: list[int],
) -> dict[int, tuple[InFlightItemResponse, datetime | None]]:
    """Build display rows for item IDs; returns (response, scraped_at) per id."""

    if not item_ids:
        return {}

    unique_ids = list(dict.fromkeys(item_ids))

    with db_session() as session:
        items = list(
            session.scalars(
                select(MediaItem)
                .where(MediaItem.id.in_(unique_ids))
                .options(*_MEDIA_ITEM_STATUS_LOAD_OPTIONS)
            ).all()
        )
        parent_ids: set[int] = set()
        for item in items:
            pid = getattr(item, "parent_id", None)
            if pid:
                parent_ids.add(int(pid))

        parents: dict[int, MediaItem] = {}
        if parent_ids:
            for parent in session.scalars(
                select(MediaItem)
                .where(MediaItem.id.in_(parent_ids))
                .options(*_MEDIA_ITEM_STATUS_LOAD_OPTIONS)
            ):
                parents[parent.id] = parent

            grandparent_ids = {
                int(getattr(parent, "parent_id"))
                for parent in parents.values()
                if getattr(parent, "parent_id", None)
            } - set(parents.keys())
            if grandparent_ids:
                for grandparent in session.scalars(
                    select(MediaItem)
                    .where(MediaItem.id.in_(grandparent_ids))
                    .options(*_MEDIA_ITEM_STATUS_LOAD_OPTIONS)
                ):
                    parents[grandparent.id] = grandparent

        by_id = {item.id: item for item in items}
        rows: dict[int, tuple[InFlightItemResponse, datetime | None]] = {}

        for item_id in unique_ids:
            item = by_id.get(item_id)
            if not item:
                rows[item_id] = (
                    InFlightItemResponse(
                        id=item_id,
                        title=f"Item {item_id}",
                        type="unknown",
                    ),
                    None,
                )
                continue

            parent_title: str | None = None
            season_number: int | None = None
            episode_number: int | None = None

            if item.type == "season":
                show = parents.get(int(getattr(item, "parent_id", 0) or 0))
                parent_title = show.title if show else None
                season_number = getattr(item, "number", None)
            elif item.type == "episode":
                season = parents.get(int(getattr(item, "parent_id", 0) or 0))
                season_number = getattr(season, "number", None) if season else None
                show = (
                    parents.get(int(getattr(season, "parent_id", 0) or 0))
                    if season
                    else None
                )
                parent_title = show.title if show else None
                episode_number = getattr(item, "number", None)

            rows[item_id] = (
                InFlightItemResponse(
                    id=item.id,
                    title=item.title or f"Item {item.id}",
                    type=item.type,
                    parent_title=parent_title,
                    season_number=season_number,
                    episode_number=episode_number,
                    state=item.last_state.name if item.last_state else None,
                ),
                item.scraped_at,
            )

        return rows


def _in_flight_items(
    item_ids: list[int],
    display: dict[int, tuple[InFlightItemResponse, datetime | None]] | None = None,
    activities: dict[int, str] | None = None,
) -> list[InFlightItemResponse]:
    rows = display if display is not None else _item_display_rows(item_ids)
    result: list[InFlightItemResponse] = []
    for item_id in item_ids:
        if item_id not in rows:
            continue
        row = rows[item_id][0]
        activity = (activities or {}).get(item_id)
        if activity:
            row = row.model_copy(update={"activity": activity})
        result.append(row)
    return result


def _queued_items(
    event_rows: list[dict[str, Any]],
    display: dict[int, tuple[InFlightItemResponse, datetime | None]] | None = None,
) -> list[QueuedItemResponse]:
    if not event_rows:
        return []

    now = datetime.now()
    item_ids = [int(r["item_id"]) for r in event_rows]
    display_rows = display if display is not None else _item_display_rows(item_ids)
    result: list[QueuedItemResponse] = []

    for raw in event_rows:
        item_id = int(raw["item_id"])
        run_at: datetime = raw["run_at"]
        queued_at: datetime = raw["queued_at"]
        deferred: bool = bool(raw["deferred"])

        display_row, scraped_at = display_rows.get(
            item_id,
            (
                InFlightItemResponse(
                    id=item_id,
                    title=f"Item {item_id}",
                    type="unknown",
                ),
                None,
            ),
        )

        if deferred:
            wait_seconds = max(0.0, (run_at - now).total_seconds())
        else:
            anchor = queued_at
            if scraped_at and scraped_at > anchor:
                anchor = scraped_at
            wait_seconds = max(0.0, (now - anchor).total_seconds())

        result.append(
            QueuedItemResponse(
                **display_row.model_dump(),
                run_at=format_api_datetime(run_at),
                queued_at=format_api_datetime(queued_at),
                scraped_at=format_api_datetime(scraped_at),
                deferred=deferred,
                wait_seconds=wait_seconds,
                emitted_by=str(raw["emitted_by"]),
            )
        )

    return result


# Keep payloads bounded when the event manager tracks many concurrent downloader jobs.
DOWNLOADER_IN_FLIGHT_LIMIT = 50


class DownloaderStatusResponse(BaseModel):
    paused: bool
    pause_until: str | None = None
    min_job_interval_seconds: float
    queue: DownloaderQueueStats
    services: list[DownloaderServiceStatus]
    in_flight_total: int = 0
    in_flight_items: list[InFlightItemResponse]
    queued_items: list[QueuedItemResponse]
    recent_jobs: list[LastDownloaderJobResponse] = []


def _recent_jobs_response(
    raw_jobs: list[dict[str, Any]],
    display: dict[int, tuple[InFlightItemResponse, datetime | None]] | None = None,
) -> list[LastDownloaderJobResponse]:
    if not raw_jobs:
        return []

    result: list[LastDownloaderJobResponse] = []
    for raw in raw_jobs:
        item_id = raw.get("item_id")
        item: InFlightItemResponse | None = None
        if item_id is not None:
            item_id_int = int(item_id)
            rows = display if display is not None else _item_display_rows([item_id_int])
            item = rows.get(item_id_int, (None, None))[0]

        result.append(
            LastDownloaderJobResponse(
                item=item,
                completed_at=raw.get("completed_at"),
                outcome=raw.get("outcome"),
                detail=raw.get("detail"),
                service=raw.get("service"),
            )
        )

    return result


def _fetch_download_user_info() -> DownloaderUserInfoResponse:
    """
    Fetch normalized user information from all initialized downloader services.

    Returns user info including premium status, expiration, and service-specific details
    for all active downloader services (Real-Debrid, Debrid-Link, AllDebrid, etc.)
    """
    try:
        # Get the downloader service from the program
        services = di[Program].services

        if services is None:
            raise HTTPException(
                status_code=503,
                detail="Program services are not ready yet; try again in a few seconds.",
            )

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
        logger.exception("Error getting downloader user info")
        raise HTTPException(status_code=500, detail=f"Internal server error: {e!r}") from e


def _download_user_info_sync(*, refresh: bool = False) -> DownloaderUserInfoResponse:
    global _user_info_cache

    if not refresh:
        with _user_info_cache_lock:
            if _user_info_cache is not None:
                cached_at, cached = _user_info_cache
                if time.monotonic() - cached_at < USER_INFO_CACHE_TTL_SECONDS:
                    return cached

    result = _fetch_download_user_info()

    with _user_info_cache_lock:
        _user_info_cache = (time.monotonic(), result)

    return result


@router.get(
    "/downloader_user_info",
    operation_id="download_user_info",
    response_model=DownloaderUserInfoResponse,
)
async def download_user_info(
    refresh: Annotated[
        bool,
        Query(
            description="Bypass the in-memory cache and fetch fresh data from debrid APIs",
        ),
    ] = False,
) -> DownloaderUserInfoResponse:
    return await run_in_threadpool(_download_user_info_sync, refresh=refresh)


def _scraped_library_count() -> int:
    global _scraped_count_cache

    now = time.monotonic()
    with _scraped_count_cache_lock:
        if _scraped_count_cache is not None:
            cached_at, cached_count = _scraped_count_cache
            if now - cached_at < SCRAPED_COUNT_CACHE_TTL_SECONDS:
                return cached_count

    with db_session() as session:
        count = session.execute(
            select(func.count(MediaItem.id)).where(
                MediaItem.last_state == States.Scraped
            )
        ).scalar_one()

    with _scraped_count_cache_lock:
        _scraped_count_cache = (now, int(count))

    return int(count)


def _build_downloader_status() -> DownloaderStatusResponse:
    """Operational downloader status: cooldowns, circuit breakers, and queue depth."""

    try:
        program = di[Program]
        services = program.services

        if services is None:
            raise HTTPException(
                status_code=503,
                detail="Program services are not ready yet; try again in a few seconds.",
            )

        downloader = services.downloader

        if not downloader or not downloader.initialized:
            raise HTTPException(
                status_code=503, detail="No downloader service is initialized"
            )

        operational = downloader.get_operational_status()
        queue_raw, queue_event_rows = program.em.get_downloader_queue_snapshot()
        in_flight_ids = [int(i) for i in program.em.get_event_updates().get("Downloader", [])]
        in_flight_total = len(in_flight_ids)
        in_flight_sample = in_flight_ids[:DOWNLOADER_IN_FLIGHT_LIMIT]
        recent_jobs_raw = downloader.get_recent_jobs()
        active_activities = downloader.get_active_job_activities()

        display_ids: list[int] = list(in_flight_sample)
        display_ids.extend(int(r["item_id"]) for r in queue_event_rows)
        display_ids.extend(
            int(job["item_id"])
            for job in recent_jobs_raw
            if job.get("item_id") is not None
        )
        item_display = (
            _item_display_rows(list(dict.fromkeys(display_ids)))
            if display_ids
            else {}
        )

        service_rows = [
            DownloaderServiceStatus(
                key=str(row["key"]),
                available=bool(row["available"]),
                cooldown_until=row.get("cooldown_until"),
            )
            for row in operational["services"]
        ]

        return DownloaderStatusResponse(
            paused=bool(operational["paused"]),
            pause_until=operational.get("pause_until"),
            min_job_interval_seconds=float(operational["min_job_interval_seconds"]),
            queue=DownloaderQueueStats(
                scraped_queued=int(queue_raw["scraped_queued"]),
                scraped_ready=int(queue_raw.get("scraped_ready", 0)),
                deferred=int(queue_raw["deferred"]),
                total_queued=int(queue_raw.get("total_queued", 0)),
                downloader_emitted=int(queue_raw.get("downloader_emitted", 0)),
                queue_by_source=dict(queue_raw.get("queue_by_source") or {}),
                next_ready_at=queue_raw.get("next_ready_at"),
                next_ready_in_seconds=queue_raw.get("next_ready_in_seconds"),
                queue_truncated=bool(queue_raw.get("queue_truncated", False)),
                scraped_in_library=_scraped_library_count(),
            ),
            services=service_rows,
            in_flight_total=in_flight_total,
            in_flight_items=_in_flight_items(
                in_flight_sample, item_display, active_activities
            ),
            queued_items=_queued_items(queue_event_rows, item_display),
            recent_jobs=_recent_jobs_response(recent_jobs_raw, item_display),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error getting downloader status")
        raise HTTPException(status_code=500, detail=f"Internal server error: {e!r}") from e


@router.get(
    "/downloader_status",
    operation_id="downloader_status",
    response_model=DownloaderStatusResponse,
)
async def downloader_status() -> DownloaderStatusResponse:
    return await run_in_threadpool(_build_downloader_status)


class DownloaderQueueReorderRequest(BaseModel):
    item_id: int = Field(description="Media item id to reorder in the downloader queue")


def _downloader_queue_reorder_sync(item_id: int, *, prioritize: bool) -> MessageResponse:
    try:
        program = di[Program]
        services = program.services

        if services is None:
            raise HTTPException(
                status_code=503,
                detail="Program services are not ready yet; try again in a few seconds.",
            )

        downloader = services.downloader
        if not downloader or not downloader.initialized:
            raise HTTPException(
                status_code=503, detail="No downloader service is initialized"
            )

        if prioritize:
            ok = program.em.prioritize_downloader_queue_item(item_id)
            action = "prioritize"
        else:
            ok = program.em.deprioritize_downloader_queue_item(item_id)
            action = "deprioritize"

        if not ok:
            raise HTTPException(
                status_code=404,
                detail=f"Item {item_id} is not in the downloader queue or is already downloading",
            )

        return MessageResponse(message=f"Downloader queue {action} applied for item {item_id}")
    except HTTPException:
        raise
    except ServiceError:
        raise HTTPException(
            status_code=503,
            detail="Program services are not ready yet; try again in a few seconds.",
        )
    except Exception as e:
        logger.exception("Error reordering downloader queue item %s", item_id)
        raise HTTPException(status_code=500, detail=f"Internal server error: {e!r}") from e


@router.post(
    "/downloader_queue/prioritize",
    operation_id="downloader_queue_prioritize",
    response_model=MessageResponse,
)
async def downloader_queue_prioritize(
    body: DownloaderQueueReorderRequest,
) -> MessageResponse:
    return await run_in_threadpool(
        _downloader_queue_reorder_sync, body.item_id, prioritize=True
    )


@router.post(
    "/downloader_queue/deprioritize",
    operation_id="downloader_queue_deprioritize",
    response_model=MessageResponse,
)
async def downloader_queue_deprioritize(
    body: DownloaderQueueReorderRequest,
) -> MessageResponse:
    return await run_in_threadpool(
        _downloader_queue_reorder_sync, body.item_id, prioritize=False
    )


@router.get(
    "/rate_limits",
    operation_id="rate_limits",
    response_model=RateLimitsResponse,
)
async def rate_limits(
    owner: str | None = None,
    active_within_minutes: Annotated[
        int,
        Query(
            ge=1,
            le=24 * 60,
            description="Only return limiters used within this many minutes",
        ),
    ] = 30,
    include_inactive: Annotated[
        bool,
        Query(description="Include registered limiters with no recent activity"),
    ] = False,
) -> RateLimitsResponse:
    """Snapshot of rate limiters and circuit breakers with recent activity."""

    try:
        rl = get_rate_limit_service()
        active_within_seconds = (
            None if include_inactive else float(active_within_minutes * 60)
        )
        snapshots = rl.snapshot_all(
            owner=owner,
            active_within_seconds=active_within_seconds,
        )
        limiters = [
            LimiterSnapshotResponse(
                key=s.key,
                label=s.label,
                owner=s.owner,
                tokens=s.tokens,
                capacity=s.capacity,
                rate_per_second=s.rate_per_second,
                utilization_pct=s.utilization_pct,
                next_token_in_seconds=s.next_token_in_seconds,
                priority=s.priority,
                warn_at_pct=s.warn_at_pct,
                breaker_state=s.breaker_state,
                breaker_failures=s.breaker_failures,
                breaker_recovery_in_seconds=s.breaker_recovery_in_seconds,
            )
            for s in snapshots
        ]
        by_owner: dict[str, list[str]] = {}
        for lim in limiters:
            by_owner.setdefault(lim.owner, []).append(lim.key)
        return RateLimitsResponse(limiters=limiters, by_owner=by_owner)
    except Exception as e:
        logger.exception("Error getting rate limits")
        raise HTTPException(status_code=500, detail=f"Internal server error: {e!r}") from e


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


class ServicesStatusResponse(BaseModel):
    """Per-runner/sub-service initialization flags plus runtime fallback indicators."""

    services: dict[str, bool] = Field(
        default_factory=dict,
        description="Service key → whether that integration initialized successfully",
    )
    mock_vfs: bool = Field(
        default=False,
        description="True when FUSE is unavailable and the in-memory VFS inventory is used",
    )
    console_updater: bool = Field(
        default=False,
        description="True when only the console (no-op) library updater is active",
    )


@router.get("/services", operation_id="services", response_model=ServicesStatusResponse)
async def get_services() -> ServicesStatusResponse:
    data = dict[str, bool]()
    mock_vfs = False
    console_updater = False

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

        mock_vfs = services.filesystem.uses_mock_vfs
        console_updater = services.updater.uses_console_updater

    return ServicesStatusResponse(
        services=data,
        mock_vfs=mock_vfs,
        console_updater=console_updater,
    )


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
    states_movies: dict[States, int]
    states_episodes: dict[States, int]
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


def _counts_by_state(
    conn,
    model: type[MediaItem] | type[Movie] | type[Episode],
) -> dict[States, int]:
    counts: dict[States, int] = {state: 0 for state in States}
    rows = conn.execute(
        select(model.last_state, func.count(model.id)).group_by(model.last_state)
    )
    for state_val, count in rows:
        if state_val is not None:
            counts[state_val] = int(count)
    return counts


def _compute_stats() -> StatsResponse:
    """
    Produce aggregated statistics for the media library and its items.

    Runs synchronously; call via run_in_threadpool from the HTTP handler so large
    libraries do not block the API event loop.
    """

    with db_session() as session:
        with session.connection() as conn:
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

            incomplete_items = conn.execute(
                select(func.count(MediaItem.id)).where(
                    MediaItem.last_state != States.Completed
                )
            ).scalar_one()

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

            states = _counts_by_state(conn, MediaItem)
            states_movies = _counts_by_state(conn, Movie)
            states_episodes = _counts_by_state(conn, Episode)

    return StatsResponse(
        total_items=total_items,
        total_movies=total_movies,
        total_shows=total_shows,
        total_seasons=total_seasons,
        total_episodes=total_episodes,
        total_symlinks=total_symlinks,
        incomplete_items=incomplete_items,
        states=states,
        states_movies=states_movies,
        states_episodes=states_episodes,
        activity=activity,
        media_year_releases=media_year_releases,
    )


@router.get(
    "/stats",
    operation_id="stats",
    response_model=StatsResponse,
)
async def get_stats() -> StatsResponse:
    return await run_in_threadpool(_compute_stats)


class LogsResponse(BaseModel):
    logs: list[str]


@router.get(
    "/logs",
    operation_id="logs",
    response_model=LogsResponse,
)
async def get_logs() -> LogsResponse:
    MAX_LOG_LINES = 1000

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

        if len(log_contents) > MAX_LOG_LINES:
            # Keep only the last MAX_LOG_LINES entries while preserving
            # chronological order (oldest -> newest)
            log_contents = log_contents[-MAX_LOG_LINES:]

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
    services = di[Program].services
    assert services

    vfs = services.filesystem.riven_vfs
    if not vfs:
        raise HTTPException(status_code=503, detail="VFS not initialized")

    # Inventory build can be O(N) on first call; keep it off the event loop.
    file_map = await run_in_threadpool(vfs.get_mount_files_inventory)
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

    for (
        handler
    ) in (  # pyright: ignore[reportUnknownVariableType]
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


class VFSLibraryStats(BaseModel):
    """Sizes of video media entries currently marked available in the VFS."""

    total_bytes: Annotated[
        int,
        Field(description="Sum of file_size for all media entries in VFS (non-directory)"),
    ]
    movies_bytes: Annotated[
        int,
        Field(description="Portion of total_bytes linked to movie MediaItems"),
    ]
    tv_bytes: Annotated[
        int,
        Field(description="Portion of total_bytes linked to episode MediaItems"),
    ]


class VfsThroughputStats(BaseModel):
    """Cumulative VFS I/O accounting: network ingress vs client reads (warm cache_hit vs cold paths)."""

    network_bytes_ingested: Annotated[
        int,
        Field(description="Total HTTP response body bytes ingested (streaming + discrete range reads)"),
    ]
    client_bytes_served_warm: Annotated[
        int,
        Field(
            description="Bytes returned to FUSE where the read was satisfied as cache_hit (already on disk)"
        ),
    ]
    client_bytes_served_cold: Annotated[
        int,
        Field(description="Bytes returned via body pipeline, header/footer scans, or other non-cache_hit paths"),
    ]
    client_warm_byte_ratio: Annotated[
        float | None,
        Field(
            description="client_bytes_served_warm / (warm+cold) when volume > 0; else null",
        ),
    ]


class VFSStatsResponse(BaseModel):
    streams: Annotated[
        dict[str, dict[str, Any]],
        Field(description="Active media stream statistics keyed by stream path:fh"),
    ]
    cache: Annotated[
        dict[str, Any],
        Field(description="Aggregate chunk-cache metrics"),
    ]
    library: Annotated[
        VFSLibraryStats,
        Field(description="Library file sizes for content exposed through the VFS"),
    ]
    throughput: Annotated[
        VfsThroughputStats,
        Field(description="VFS-wide origin / usefulness counters since mount"),
    ]


@router.get(
    "/vfs_stats",
    summary="Get VFS Statistics",
    description="Get statistics about the VFS including active streams and cache metrics",
    operation_id="get_vfs_stats",
    response_model=VFSStatsResponse,
)
async def get_vfs_stats() -> VFSStatsResponse:
    """Get statistics about the VFS"""

    from program.services.streaming import Cache

    services = di[Program].services

    if services is None:
        raise HTTPException(
            status_code=503,
            detail="Program services are not ready yet; try again in a few seconds.",
        )

    vfs = services.filesystem.riven_vfs

    if vfs is None:
        raise HTTPException(
            status_code=503,
            detail="VFS is not available yet; filesystem service may still be starting.",
        )

    try:
        cache_snapshot: dict[str, Any] = di[Cache].snapshot_for_http()
    except Exception:
        cache_snapshot = {}

    base_media = (
        MediaEntry.available_in_vfs.is_(True),
        MediaEntry.is_directory.is_(False),
    )
    with db_session() as session:
        total_bytes = int(
            session.execute(
                select(func.coalesce(func.sum(MediaEntry.file_size), 0)).where(*base_media)
            ).scalar_one()
        )
        movies_bytes = int(
            session.execute(
                select(func.coalesce(func.sum(MediaEntry.file_size), 0))
                .join(MediaItem, MediaItem.id == MediaEntry.media_item_id)
                .where(*base_media, MediaItem.type == "movie")
            ).scalar_one()
        )
        tv_bytes = int(
            session.execute(
                select(func.coalesce(func.sum(MediaEntry.file_size), 0))
                .join(MediaItem, MediaItem.id == MediaEntry.media_item_id)
                .where(*base_media, MediaItem.type == "episode")
            ).scalar_one()
        )

    library = VFSLibraryStats(
        total_bytes=total_bytes,
        movies_bytes=movies_bytes,
        tv_bytes=tv_bytes,
    )

    throughput_raw = vfs.io_metrics_snapshot
    throughput = VfsThroughputStats(
        network_bytes_ingested=int(throughput_raw.get("network_bytes_ingested", 0)),
        client_bytes_served_warm=int(throughput_raw.get("client_bytes_served_warm", 0)),
        client_bytes_served_cold=int(throughput_raw.get("client_bytes_served_cold", 0)),
        client_warm_byte_ratio=throughput_raw.get("client_warm_byte_ratio"),
    )

    return VFSStatsResponse(
        streams=vfs.opener_stats,
        cache=cache_snapshot,
        library=library,
        throughput=throughput,
    )


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
