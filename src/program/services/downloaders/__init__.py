from collections import deque
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
import threading
import time
from typing import Any, Literal
from loguru import logger
from RTN import ParsedData

from program.media.item import (
    Episode,
    MediaItem,
    Movie,
    ProcessedItemType,
    Season,
    Show,
)
from program.media.state import States
from program.media.stream import Stream
from program.media.media_entry import MediaEntry
from program.media.models import ActiveStream, MediaMetadata
from program.services.downloaders.models import (
    DebridFile,
    DownloadedTorrent,
    InfringingTorrentException,
    NoMatchingFilesException,
    NotCachedException,
    TorrentContainer,
    TorrentInfo,
    UserInfo,
)
from program.services.downloaders.shared import (
    DownloaderBase,
    sort_streams_by_quality,
    parse_filename,
)
from program.settings import settings_manager
from program.utils import format_api_datetime
from program.services.rate_limit import CircuitBreakerOpen, get_rate_limit_service
from program.core.runner import MediaItemGenerator, Runner, RunnerResult

from .realdebrid import RealDebridDownloader
from .debridlink import DebridLinkDownloader
from .alldebrid import AllDebridDownloader
from .torbox import TorBoxDownloader


_RECENT_JOBS_MAX = 5
_RECENT_JOBS_MAX_AGE = timedelta(minutes=2)


@dataclass
class _JobCompletion:
    outcome: Literal["success", "deferred", "failed", "skipped"]
    detail: str | None = None
    service: str | None = None


@dataclass
class _LastJob:
    item_id: int
    completed_at: datetime
    outcome: Literal["success", "deferred", "failed", "skipped"]
    detail: str | None = None
    service: str | None = None


_DETAIL_MAX_LEN = 480
_ACTIVITY_MAX_LEN = 200


@dataclass
class _ActiveJobActivity:
    detail: str


@dataclass
class _DownloadRunDiagnostics:
    streams_total: int = 0
    streams_tried: int = 0
    not_cached: int = 0
    no_matching_files: int = 0
    api_errors: int = 0
    circuit_breaker: int = 0
    last_error: str | None = None
    services_tried: set[str] = field(default_factory=set)

    def note_not_cached(self, service: str, infohash: str) -> None:
        self.not_cached += 1
        self.services_tried.add(service)

    def note_no_matching_files(self, service: str, infohash: str) -> None:
        self.no_matching_files += 1
        self.services_tried.add(service)

    def note_api_error(self, service: str, infohash: str, exc: BaseException) -> None:
        self.api_errors += 1
        self.services_tried.add(service)
        self.last_error = f"{type(exc).__name__}: {exc}"[:120]

    def note_circuit_breaker(self, service: str) -> None:
        self.circuit_breaker += 1
        self.services_tried.add(service)

    def note_stream_tried(self) -> None:
        self.streams_tried += 1

    def _reason_summary(self) -> str:
        parts: list[str] = []
        if self.not_cached:
            parts.append("not cached on debrid")
        if self.no_matching_files:
            parts.append("no matching files in torrent")
        if self.api_errors:
            if self.last_error:
                parts.append(f"API error ({self.last_error})")
            else:
                parts.append("API error")
        if self.circuit_breaker:
            parts.append("circuit breaker open")
        if not parts:
            return "No stream could be downloaded"
        summary = "; ".join(parts)
        return summary[0].upper() + summary[1:]

    def build_detail(self) -> str:
        if self.streams_total == 0:
            return "0 streams on item"

        tried = self.streams_tried or self.streams_total
        remaining = max(0, self.streams_total - tried)

        header = (
            "Tried 1 stream" if tried == 1 else f"Tried {tried} streams"
        )
        if remaining:
            more = "1 more on item" if remaining == 1 else f"{remaining} more on item"
            header += f" ({more})"

        detail = f"{header}. {self._reason_summary()}"

        if len(detail) > _DETAIL_MAX_LEN:
            detail = detail[: _DETAIL_MAX_LEN - 3] + "..."

        return detail


class _ThrottledLog:
    """Emit at most one WARNING per key per interval; fold duplicates into a suffix."""

    def __init__(self, interval_seconds: float = 60.0) -> None:
        self._interval = interval_seconds
        self._last_key: str | None = None
        self._last_at: datetime | None = None
        self._suppressed = 0

    def warning(self, key: str, message: str) -> None:
        now = datetime.now()
        if (
            self._last_key == key
            and self._last_at
            and (now - self._last_at).total_seconds() < self._interval
        ):
            self._suppressed += 1
            return

        if self._suppressed:
            message = f"{message} ({self._suppressed} similar events suppressed)"
            self._suppressed = 0

        logger.warning(message)
        self._last_key = key
        self._last_at = now

    def reset(self) -> None:
        self._last_key = None
        self._last_at = None
        self._suppressed = 0


class Downloader(Runner[None, DownloaderBase]):
    def __init__(self):
        super().__init__()

        self.initialized = False
        self.services = {
            RealDebridDownloader: RealDebridDownloader(),
            DebridLinkDownloader: DebridLinkDownloader(),
            AllDebridDownloader: AllDebridDownloader(),
            TorBoxDownloader: TorBoxDownloader(),
        }

        # Get all initialized services instead of just the first one
        self.initialized_services = [
            service for service in self.services.values() if service.initialized
        ]

        # Keep backward compatibility - primary service is the first initialized one
        self.service = (
            self.initialized_services[0] if self.initialized_services else None
        )

        self.initialized = self.validate()

        # Track per-service cooldowns when circuit breaker is open
        self._service_cooldowns = dict[str, datetime]()
        self._throttled_logs = _ThrottledLog(interval_seconds=60.0)
        self._job_slot_lock = threading.Lock()
        self._next_job_slot_at = 0.0
        self.min_job_interval_seconds = self._compute_min_job_interval()
        self.max_streams_per_job = (
            settings_manager.settings.downloaders.max_streams_per_job
        )
        self.subtitles_enabled = (
            settings_manager.settings.post_processing.subtitle.enabled
        )
        self._recent_jobs: deque[_LastJob] = deque(maxlen=_RECENT_JOBS_MAX)
        self._active_jobs: dict[int, _ActiveJobActivity] = {}
        self._active_jobs_lock = threading.Lock()

    def _set_active_job_activity(self, item_id: int, detail: str) -> None:
        trimmed = detail.strip()
        if not trimmed:
            return
        if len(trimmed) > _ACTIVITY_MAX_LEN:
            trimmed = trimmed[: _ACTIVITY_MAX_LEN - 3] + "..."
        with self._active_jobs_lock:
            self._active_jobs[item_id] = _ActiveJobActivity(detail=trimmed)

        try:
            from kink import di

            from program.program import Program

            di[Program].em.set_pipeline_activity(item_id, trimmed)
        except Exception:
            pass

    def _clear_active_job_activity(self, item_id: int) -> None:
        with self._active_jobs_lock:
            self._active_jobs.pop(item_id, None)
        try:
            from kink import di

            from program.program import Program

            di[Program].em.clear_pipeline_activity(item_id)
        except Exception:
            pass

    def get_active_job_activities(self) -> dict[int, str]:
        with self._active_jobs_lock:
            return {item_id: row.detail for item_id, row in self._active_jobs.items()}

    def _log_job_completion(
        self,
        item: MediaItem,
        outcome: Literal["success", "deferred", "failed", "skipped"],
        detail: str | None,
        service: str | None,
    ) -> None:
        msg = f"Downloader {outcome} for {item.log_string} ({item.id})"
        if detail:
            msg += f": {detail}"
        if service:
            msg += f" [{service}]"

        if outcome == "success":
            logger.info(msg)
        elif outcome == "failed":
            logger.warning(msg)
        elif outcome == "deferred":
            logger.warning(msg)
        else:
            logger.info(msg)

    def _download_retry_run_at(self) -> datetime:
        """Next wall-clock slot for a follow-up download job."""

        try:
            from kink import di

            from program.program import Program

            program = di[Program]
            return program.em._reserve_downloader_dispatch_time(program)
        except Exception:
            return datetime.now()

    def _fail_download(self, item: MediaItem, completion: _JobCompletion) -> None:
        """Mark the item failed and surface it on the Activity board."""

        item.store_state(States.Failed)
        try:
            from kink import di

            from program.program import Program

            di[Program].em.record_recently_finished(
                int(item.id),
                outcome="failed",
                service_name="Downloader",
                failure_service="Downloader",
                completion_detail=completion.detail,
            )
        except Exception:
            pass

    def _append_completed_job(
        self,
        item: MediaItem,
        completion: _JobCompletion,
    ) -> None:
        self._recent_jobs.appendleft(
            _LastJob(
                item_id=int(item.id),
                completed_at=datetime.now(UTC),
                outcome=completion.outcome,
                detail=completion.detail,
                service=completion.service,
            )
        )
        self._log_job_completion(
            item,
            completion.outcome,
            completion.detail,
            completion.service,
        )
        try:
            from kink import di

            from program.program import Program

            em = di[Program].em
            item_id = int(item.id)
            if completion.outcome == "deferred" and completion.detail:
                em.set_pipeline_activity(item_id, completion.detail)
        except Exception:
            pass

    def _prune_stale_recent_jobs(self) -> None:
        cutoff = datetime.now(UTC) - _RECENT_JOBS_MAX_AGE
        while self._recent_jobs and self._recent_jobs[-1].completed_at < cutoff:
            self._recent_jobs.pop()

    def get_recent_jobs(self) -> list[dict[str, Any]]:
        self._prune_stale_recent_jobs()
        return [
            {
                "item_id": job.item_id,
                "completed_at": format_api_datetime(job.completed_at),
                "outcome": job.outcome,
                "detail": job.detail,
                "service": job.service,
            }
            for job in self._recent_jobs
        ]

    def _compute_min_job_interval(self) -> float:
        override = settings_manager.settings.downloaders.min_job_interval_seconds
        if override is not None:
            return float(override)

        rates = [
            float(service.API_RATE_PER_SECOND)
            for service in self.initialized_services
            if service.API_RATE_PER_SECOND > 0
        ]
        if not rates:
            return 0.2

        return 1.0 / min(rates)

    def _available_services(self, now: datetime | None = None) -> list[DownloaderBase]:
        if now is None:
            now = datetime.now()

        return [
            service
            for service in self.initialized_services
            if service.key not in self._service_cooldowns
            or self._service_cooldowns[service.key] <= now
        ]

    def pause_until(self) -> datetime | None:
        """When all initialized services are in cooldown, return the earliest retry time."""

        if self._available_services():
            return None

        if not self._service_cooldowns:
            return None

        return min(self._service_cooldowns.values())

    _MIN_SERVICE_COOLDOWN_SECONDS = 5.0
    _MAX_SERVICE_COOLDOWN_SECONDS = 600.0

    def _on_circuit_breaker_open(
        self,
        service: DownloaderBase,
        exc: CircuitBreakerOpen,
        *,
        context: str = "",
    ) -> datetime:
        """Apply per-service cooldown and emit a throttled warning."""

        rl = get_rate_limit_service()
        wait_sec = max(
            exc.retry_after or 0.0,
            rl.seconds_until_ready(service.primary_limit_key()),
            self._MIN_SERVICE_COOLDOWN_SECONDS,
        )
        wait_sec = min(wait_sec, self._MAX_SERVICE_COOLDOWN_SECONDS)
        cooldown_until = datetime.now() + timedelta(seconds=wait_sec)
        self._service_cooldowns[service.key] = cooldown_until
        message = f"Circuit breaker OPEN for {service.key} ({exc.name})"
        if context:
            message = f"{message}; {context}"
        self._throttled_logs.warning(f"cb:{service.key}:{exc.name}", message)
        return cooldown_until

    def _acquire_job_slot(self) -> None:
        """Space downloader jobs apart to stay within debrid API rate limits."""

        interval = self.min_job_interval_seconds
        if interval <= 0:
            return

        with self._job_slot_lock:
            now = time.monotonic()
            wait = self._next_job_slot_at - now
            if wait > 0:
                time.sleep(wait)
                now = time.monotonic()

            self._next_job_slot_at = now + interval

    def _space_after_stream_attempt(self) -> None:
        """Light spacing between stream attempts within a single job."""

        interval = self.min_job_interval_seconds
        if interval > 0:
            time.sleep(interval)

    def get_operational_status(self) -> dict[str, Any]:
        """Operational snapshot for API/dashboard (not account/premium info)."""

        now = datetime.now()
        pause = self.pause_until()
        available = self._available_services(now)

        services: list[dict[str, Any]] = []
        for service in self.initialized_services:
            cooldown = self._service_cooldowns.get(service.key)
            services.append(
                {
                    "key": service.key,
                    "available": service in available,
                    "cooldown_until": (
                        format_api_datetime(cooldown)
                        if cooldown and cooldown > now
                        else None
                    ),
                }
            )

        return {
            "paused": pause is not None and pause > now,
            "pause_until": (
                format_api_datetime(pause) if pause and pause > now else None
            ),
            "min_job_interval_seconds": self.min_job_interval_seconds,
            "max_streams_per_job": self.max_streams_per_job,
            "services": services,
        }

    def validate(self):
        if not self.initialized_services:
            logger.error(
                "No downloader service is initialized. Please initialize a downloader service."
            )
            return False

        logger.info(
            f"Initialized {len(self.initialized_services)} downloader service(s): {', '.join(s.key for s in self.initialized_services)}"
        )

        return True

    def run(
        self,
        item: MediaItem,
    ) -> MediaItemGenerator:
        logger.debug(f"Starting download process for {item.log_string} ({item.id})")

        item_id = int(item.id)
        self._set_active_job_activity(item_id, "Starting download")

        self.max_streams_per_job = (
            settings_manager.settings.downloaders.max_streams_per_job
        )
        self._acquire_job_slot()

        completion: _JobCompletion | None = None
        try:
            # Check if all services are in cooldown due to circuit breaker
            now = datetime.now()

            self._set_active_job_activity(item_id, "Checking services")
            available_services = self._available_services(now)

            if not available_services:
                self._set_active_job_activity(
                    item_id, "Waiting — all services in cooldown"
                )
                # All services are in cooldown, reschedule for the earliest available time
                next_attempt = min(self._service_cooldowns.values())

                self._throttled_logs.warning(
                    f"all_cooldown:{next_attempt.isoformat(timespec='minutes')}",
                    "All downloader services in cooldown, deferring downloads "
                    f"until {next_attempt.strftime('%m/%d/%y %H:%M:%S')}",
                )

                completion = _JobCompletion(
                    "deferred",
                    detail=f"All services in cooldown until {next_attempt.isoformat()}",
                )
                yield RunnerResult(media_items=[item], run_at=next_attempt)
                return

            # Check subscription status once before attempting any stream checks.
            # If no service has an active premium subscription (e.g. debrid expired),
            # bail out early without blacklisting any streams so they remain available
            # for when the subscription is renewed.
            if not self._any_service_subscription_active(available_services):
                self._set_active_job_activity(
                    item_id, "Skipped — no active debrid subscription"
                )
                completion = _JobCompletion(
                    "skipped",
                    detail="No active debrid subscription",
                )
                yield RunnerResult(media_items=[item])
                return

            download_success = False
            success_service: str | None = None

            # Track if we hit circuit breaker on any service
            hit_circuit_breaker = False
            diag: _DownloadRunDiagnostics | None = None

            try:
                # Sort streams by resolution and rank (highest first) using simple, fast sorting
                sorted_streams = sort_streams_by_quality(item.streams)
                diag = _DownloadRunDiagnostics(streams_total=len(sorted_streams))
                streams_total = len(sorted_streams)

                tried_streams = 0

                for stream in sorted_streams:
                    stream_index = tried_streams + 1
                    stream_label = (
                        f"Stream {stream_index}/{streams_total}"
                        if streams_total > 1
                        else "Stream 1/1"
                    )
                    self._set_active_job_activity(item_id, stream_label)

                    # Try each available service for this stream before blacklisting
                    stream_failed_on_all_services = True
                    stream_hit_circuit_breaker = False
                    stream_attempted_api = False
                    stream_infringing_on: list[str] = []

                    for service in available_services:
                        logger.debug(
                            f"Trying stream {stream.infohash} on {service.key} for {item.log_string}"
                        )

                        download_result: DownloadedTorrent | None = None

                        try:
                            stream_attempted_api = True
                            self._set_active_job_activity(
                                item_id,
                                f"{stream_label} · checking {service.key}",
                            )
                            # Validate stream on this specific service
                            container = self.validate_stream_on_service(
                                stream,
                                item,
                                service,
                            )

                            if not container:
                                if diag:
                                    diag.note_not_cached(service.key, stream.infohash)
                                logger.debug(
                                    f"Stream {stream.infohash} not available on {service.key}"
                                )
                                continue

                            self._set_active_job_activity(
                                item_id,
                                f"{stream_label} · downloading on {service.key}",
                            )
                            # Try to download using this service
                            download_result = self.download_cached_stream_on_service(
                                stream,
                                container,
                                service,
                            )

                            if self.update_item_attributes(item, download_result, service):
                                logger.log(
                                    "DEBRID",
                                    f"Downloaded {item.log_string} from '{stream.raw_title}' [{stream.infohash}] using {service.key}",
                                )

                                download_success = True
                                success_service = service.key
                                stream_failed_on_all_services = False

                                break
                            else:
                                raise NoMatchingFilesException(
                                    f"No valid files found for {item.log_string} ({item.id})"
                                )
                        except CircuitBreakerOpen as e:
                            if diag:
                                diag.note_circuit_breaker(service.key)
                            self._on_circuit_breaker_open(
                                service,
                                e,
                                context=(
                                    f"trying next service for stream {stream.infohash}"
                                ),
                            )
                            stream_hit_circuit_breaker = True
                            hit_circuit_breaker = True

                            # If this is the only initialized service, don't mark stream as failed
                            # We want to retry this stream after cooldown
                            if len(self.initialized_services) == 1:
                                stream_failed_on_all_services = False
                            continue

                        except InfringingTorrentException as e:
                            stream_infringing_on.append(service.key)
                            if diag:
                                diag.note_api_error(
                                    service.key, stream.infohash, e
                                )
                            logger.info(
                                f"Stream {stream.infohash} rejected as infringing on "
                                f"{service.key}: {e}"
                            )
                            continue

                        except NoMatchingFilesException as e:
                            if diag:
                                diag.note_no_matching_files(
                                    service.key, stream.infohash
                                )
                            logger.debug(
                                f"Stream {stream.infohash} failed on {service.key}: {e}"
                            )

                            if download_result and download_result.id:
                                try:
                                    service.delete_torrent(download_result.id)

                                    logger.debug(
                                        f"Deleted failed torrent {stream.infohash} for {item.log_string} ({item.id}) on {service.key}."
                                    )
                                except Exception as del_e:
                                    logger.debug(
                                        f"Failed to delete torrent {stream.infohash} for {item.log_string} ({item.id}) on {service.key}: {del_e}"
                                    )
                            continue

                        except NotCachedException as e:
                            if diag:
                                diag.note_not_cached(service.key, stream.infohash)
                            logger.debug(
                                f"Stream {stream.infohash} failed on {service.key}: {e}"
                            )

                            if download_result and download_result.id:
                                try:
                                    service.delete_torrent(download_result.id)

                                    logger.debug(
                                        f"Deleted failed torrent {stream.infohash} for {item.log_string} ({item.id}) on {service.key}."
                                    )
                                except Exception as del_e:
                                    logger.debug(
                                        f"Failed to delete torrent {stream.infohash} for {item.log_string} ({item.id}) on {service.key}: {del_e}"
                                    )
                            continue

                        except Exception as e:
                            if diag:
                                diag.note_api_error(
                                    service.key, stream.infohash, e
                                )
                            logger.opt(exception=True).debug(
                                f"Stream {stream.infohash} failed on {service.key}: {e}"
                            )

                            if download_result and download_result.id:
                                try:
                                    service.delete_torrent(download_result.id)

                                    logger.debug(
                                        f"Deleted failed torrent {stream.infohash} for {item.log_string} ({item.id}) on {service.key}."
                                    )
                                except Exception as del_e:
                                    logger.debug(
                                        f"Failed to delete torrent {stream.infohash} for {item.log_string} ({item.id}) on {service.key}: {del_e}"
                                    )
                            continue

                    # If stream succeeded on any service, we're done
                    if download_success:
                        # Add probed data if required
                        if self.subtitles_enabled:
                            from program.services.media_analysis import (
                                media_analysis_service,
                            )

                            if media_analysis_service.should_submit(item):
                                self._set_active_job_activity(
                                    item_id, "Analyzing media"
                                )
                                success = media_analysis_service.run(item)

                                if success:
                                    logger.debug(
                                        f"Media analysis completed for {item.log_string}"
                                    )
                                    break
                                else:
                                    logger.error(
                                        f"Failed to analyze media file for {item.log_string}"
                                    )
                        else:
                            break

                    # Only blacklist if stream genuinely failed on ALL available services
                    # Don't blacklist if we hit circuit breaker in single-provider mode
                    if stream_failed_on_all_services:
                        if (
                            stream_hit_circuit_breaker
                            and len(self.initialized_services) == 1
                        ):
                            logger.debug(
                                f"Stream {stream.infohash} hit circuit breaker on single provider, will retry after cooldown"
                            )
                        elif len(stream_infringing_on) == len(available_services):
                            logger.info(
                                f"Stream {stream.infohash} rejected as infringing on all "
                                f"{len(available_services)} available service(s), blacklisting"
                            )
                            item.blacklist_stream(stream)
                        else:
                            logger.debug(
                                f"Stream {stream.infohash} failed on all {len(available_services)} available service(s), blacklisting"
                            )
                            item.blacklist_stream(stream)

                    tried_streams += 1
                    if diag:
                        diag.note_stream_tried()

                    if stream_attempted_api and not download_success:
                        self._space_after_stream_attempt()

                    if tried_streams >= self.max_streams_per_job:
                        if download_success:
                            completion = _JobCompletion(
                                "success", service=success_service
                            )
                            yield RunnerResult(media_items=[item])
                            return

                        streams_left_in_job = len(sorted_streams) - tried_streams
                        if streams_left_in_job > 0:
                            logger.info(
                                f"Downloader hit per-job limit "
                                f"({self.max_streams_per_job}) for {item.log_string}; "
                                f"{streams_left_in_job} stream(s) remaining, re-queuing"
                            )
                            yield RunnerResult(
                                media_items=[item],
                                run_at=self._download_retry_run_at(),
                            )
                            return

                        fail_detail = (
                            diag.build_detail()
                            if diag
                            else f"Tried {tried_streams} streams. Download failed"
                        )
                        completion = _JobCompletion("failed", detail=fail_detail)
                        self._fail_download(item, completion)
                        yield RunnerResult(media_items=[item])
                        return

            except Exception as e:
                logger.error(
                    f"Unexpected error in downloader for {item.log_string} ({item.id}): {e}"
                )
                completion = _JobCompletion(
                    "failed",
                    detail=f"Unexpected error: {e!r}",
                )
                self._fail_download(item, completion)
                yield RunnerResult(media_items=[item])
                return

            if not download_success:
                # Check if we hit circuit breaker in single-provider mode
                if hit_circuit_breaker and len(self.initialized_services) == 1:
                    # Reschedule for after cooldown instead of failing
                    next_attempt = min(self._service_cooldowns.values())
                    cb_key = self.initialized_services[0].key
                    self._set_active_job_activity(
                        item_id, f"Deferred — circuit breaker on {cb_key}"
                    )

                    self._throttled_logs.warning(
                        f"single_cb:{next_attempt.isoformat(timespec='minutes')}",
                        f"Downloader circuit breaker open ({self.initialized_services[0].key}), "
                        f"deferring downloads until {next_attempt.strftime('%m/%d/%y %H:%M:%S')}",
                    )

                    completion = _JobCompletion(
                        "deferred",
                        detail=f"Circuit breaker open on {cb_key}",
                        service=cb_key,
                    )
                    yield RunnerResult(media_items=[item], run_at=next_attempt)
                    return

                if item.streams:
                    remaining = len(item.streams)
                    logger.info(
                        f"Downloader re-queuing {item.log_string} "
                        f"({remaining} stream(s) still to try)"
                    )
                    yield RunnerResult(
                        media_items=[item],
                        run_at=self._download_retry_run_at(),
                    )
                    return

                fail_detail = (
                    diag.build_detail()
                    if diag
                    else "No stream could be downloaded"
                )
                completion = _JobCompletion("failed", detail=fail_detail)
                self._fail_download(item, completion)
                yield RunnerResult(media_items=[item])
            else:
                # Clear service cooldowns on successful download
                self._service_cooldowns.clear()
                self._throttled_logs.reset()

                self._set_active_job_activity(item_id, "Finishing download")
                completion = _JobCompletion("success", service=success_service)
                yield RunnerResult(media_items=[item])
        finally:
            self._clear_active_job_activity(item_id)
            if completion is not None:
                self._append_completed_job(item, completion)

    def validate_stream(
        self,
        stream: Stream,
        item: MediaItem,
    ) -> TorrentContainer | None:
        """
        Validate a single stream by ensuring its files match the item's requirements.
        Uses the primary service for backward compatibility.
        """

        assert self.service, "No primary downloader service initialized."

        return self.validate_stream_on_service(stream, item, self.service)

    def validate_stream_on_service(
        self,
        stream: Stream,
        item: MediaItem,
        service: "DownloaderBase",
    ) -> TorrentContainer | None:
        """
        Validate a single stream on a specific service by ensuring its files match the item's requirements.
        """

        if item.type == "mediaitem":
            logger.debug(
                f"Item {item.log_string} has generic type 'mediaitem', cannot validate stream {stream.infohash}."
            )

            return None

        try:
            container = service.get_instant_availability(stream.infohash, item.type)
        except CircuitBreakerOpen as e:
            self._on_circuit_breaker_open(
                service,
                e,
                context=f"validating stream {stream.infohash}",
            )
            raise

        if not container:
            logger.debug(
                f"Stream {stream.infohash} is not cached or valid on {service.key}."
            )
            return None

        if container.files:
            return container

        return None

    def update_item_attributes(
        self,
        item: MediaItem,
        download_result: DownloadedTorrent,
        service: DownloaderBase | None = None,
        *,
        replace_existing: bool = False,
    ) -> bool:
        """Update the item attributes with the downloaded files and active stream."""

        if service is None:
            service = self.service

        try:
            if not download_result.container:
                raise NotCachedException(
                    f"No container found for {item.log_string} ({item.id})"
                )

            episode_cap: int | None = None
            show: Show | None = None

            if isinstance(item, (Show, Season, Episode)):
                show = item.top_parent

                try:
                    method_1 = sum(len(season.episodes) for season in show.seasons)

                    try:
                        method_2 = show.seasons[-1].episodes[-1].number
                    except IndexError:
                        # happens if there's a new season with no episodes yet
                        method_2 = show.seasons[-2].episodes[-1].number

                    episode_cap = max([method_1, method_2])
                except Exception as e:
                    pass

            found = False
            files = download_result.container.files

            # Track episodes we've already processed to avoid duplicates
            processed_episode_ids = set[str]()

            for file in files:
                try:
                    assert file.filename

                    file_data = parse_filename(file.filename)
                except Exception as e:
                    continue

                if isinstance(item, (Show, Season, Episode)):
                    if not file_data.episodes:
                        continue
                    elif 0 in file_data.episodes and len(file_data.episodes) == 1:
                        continue
                    elif file_data.seasons and file_data.seasons[0] == 0:
                        continue

                if self.match_file_to_item(
                    item,
                    file_data,
                    file,
                    download_result,
                    show,
                    episode_cap,
                    processed_episode_ids,
                    service,
                    replace_existing=replace_existing,
                ):
                    found = True

            return found
        except Exception as e:
            logger.debug(f"update_item_attributes: exception for item {item.id}: {e}")
            raise

    def match_file_to_item(
        self,
        item: MediaItem,
        file_data: ParsedData,
        file: DebridFile,
        download_result: DownloadedTorrent,
        show: Show | None = None,
        episode_cap: int | None = None,
        processed_episode_ids: set[str] | None = None,
        service: DownloaderBase | None = None,
        *,
        replace_existing: bool = False,
    ) -> bool:
        """
        Determine whether a parsed file corresponds to the given media item (movie, show, season, or episode) and update the item's attributes when matches are found.

        Checks movie matches for movie items and episode-level matches for shows/seasons/episodes. For each matched episode or movie file, calls _update_attributes to attach filesystem metadata and marks the item.active_stream when appropriate.

        Parameters:
            item (MediaItem): The target media item to match against.
            file_data (ParsedData): Parsed metadata from RTN (item type, season, episode list, etc.).
            file (DebridFile): The debrid file candidate containing filename, download URL, and size.
            download_result (DownloadedTorrent): The download context containing infohash and torrent id.
            show (Show | None): The show object used to resolve absolute episode numbers when matching episodes.
            episode_cap (int, optional): Maximum episode number allowed for matching; episodes greater than this are skipped.
            processed_episode_ids (set[str] | None): Set of episode IDs already processed in this container to avoid duplicate updates.
            service (optional): Service instance used for attribute updates; defaults to the Downloader's primary service.

        Returns:
            bool: `true` if at least one file-to-item match was found and attributes were updated, `false` otherwise.
        """

        if service is None:
            service = self.service

        logger.debug(
            f"match_file_to_item: item={item.id} type={item.type} file='{file.filename}'"
        )

        found = False

        if isinstance(item, Movie) and file_data.type == "movie":
            logger.debug("match_file_to_item: movie match -> updating attributes")

            self._update_attributes(
                item,
                file,
                download_result,
                service,
                file_data,
            )

            return True

        if isinstance(item, (Show, Season, Episode)):
            season_number = file_data.seasons[0] if file_data.seasons else None

            for file_episode in file_data.episodes:
                if episode_cap and file_episode > episode_cap:
                    logger.debug(
                        f"Invalid episode number {file_episode} for {show.log_string if show else 'show?'} Skipping '{file.filename}'"
                    )

                    continue

                assert show

                episode = show.get_absolute_episode(file_episode, season_number)

                if episode is None:
                    logger.debug(
                        f"Episode {file_episode} from file does not match any episode in {show.log_string if show else 'show?'}"
                    )

                    continue

                if isinstance(item, Season) and season_number is not None:
                    if season_number != item.number:
                        continue

                if isinstance(item, Episode) and episode.id != item.id:
                    continue

                if episode.filesystem_entry and not replace_existing:
                    logger.debug(
                        f"Episode {episode.log_string} already has filesystem_entry; skipping"
                    )

                    continue

                can_update = replace_existing or episode.state not in [
                    States.Completed,
                    States.Symlinked,
                    States.Downloaded,
                ]

                if not can_update:
                    continue

                # Skip if we've already processed this episode in this container
                if (
                    processed_episode_ids is not None
                    and str(episode.id) in processed_episode_ids
                ):
                    continue

                logger.debug(
                    f"match_file_to_item: updating episode {episode.id} from file '{file.filename}'"
                )

                self._update_attributes(
                    episode,
                    file,
                    download_result,
                    service,
                    file_data,
                )

                if processed_episode_ids is not None:
                    processed_episode_ids.add(str(episode.id))

                logger.debug(
                    f"Matched episode {episode.log_string} to file {file.filename}"
                )

                found = True

        if found and isinstance(item, (Show, Season)):
            item.active_stream = ActiveStream(
                infohash=download_result.infohash,
                id=download_result.info.id,
            )

        return found

    def download_cached_stream_on_service(
        self,
        stream: Stream,
        container: TorrentContainer,
        service: DownloaderBase,
    ) -> DownloadedTorrent:
        """
        Prepare and return a DownloadedTorrent for a stream using the given service.

        Uses values already present on `container` when available (e.g., `torrent_id`, `torrent_info`); otherwise adds the torrent and/or fetches its info from the service.

        Returns:
            DownloadedTorrent: An object containing the torrent id, torrent info, the stream's infohash, and the (possibly updated) container.
        """

        torrent_id = None

        # Check if we already have a torrent_id from validation (Real-Debrid optimization)
        if container.torrent_id:
            torrent_id = container.torrent_id

            logger.debug(
                f"Reusing torrent_id {torrent_id} from validation for {stream.infohash}"
            )

        assert torrent_id

        # Check if we already have torrent_info from validation (Real-Debrid optimization)
        if container.torrent_info:
            info = container.torrent_info
            logger.debug(f"Reusing cached torrent_info for {stream.infohash}")
        else:
            # Fallback: fetch info if not cached
            info = service.get_torrent_info(torrent_id)

        if container.file_ids:
            service.select_files(torrent_id, container.file_ids)

        return DownloadedTorrent(
            id=torrent_id,
            info=info,
            infohash=stream.infohash,
            container=container,
        )

    def _update_attributes(
        self,
        item: Movie | Episode,
        debrid_file: DebridFile,
        download_result: DownloadedTorrent,
        service: DownloaderBase | None = None,
        file_data: ParsedData | None = None,
    ) -> None:
        """
        Update the media item's active stream and filesystem entries using a debrid file from a completed download.

        Sets item.active_stream from the download_result and, if the debrid file exposes a download URL,
        creates a MediaEntry with the original filename, download URL, and provider information.
        Path generation is now handled by RivenVFS when the entry is registered.

        Parameters:
            item (Movie|Episode): The media item to update.
            debrid_file (DebridFile): Debrid file metadata (must include filename and optionally download_url and filesize).
            download_result (DownloadedTorrent): Result of the download containing id and infohash.
            service: Optional debrid service instance; defaults to the downloader's configured service.
            file_data (ParsedData, optional): Parsed filename metadata from RTN to cache in MediaEntry.
        """

        if service is None:
            service = self.service

        if file_data:
            item.active_stream = ActiveStream(
                infohash=download_result.infohash,
                id=download_result.info.id,
            )

        # Create MediaEntry for virtual file if download URL is available
        if debrid_file.download_url:
            from program.services.library_profile_matcher import LibraryProfileMatcher

            # Match library profiles for this item
            matcher = LibraryProfileMatcher()
            library_profiles = matcher.get_matching_profiles(item)

            # Create MediaEntry with original_filename as source of truth
            # Path generation is now handled by RivenVFS during registration
            # Convert parsed file_data to MediaMetadata if available
            media_metadata = None

            if file_data:
                media_metadata = MediaMetadata.from_parsed_data(
                    parsed_data=file_data,
                    filename=debrid_file.filename,
                )

            assert debrid_file.filename
            assert service

            entry = MediaEntry.create_virtual_entry(
                original_filename=debrid_file.filename,
                download_url=debrid_file.download_url,
                provider=service.key,
                provider_download_id=str(download_result.info.id),
                file_size=debrid_file.filesize,
                media_metadata=media_metadata,
            )

            # Populate library profiles
            entry.library_profiles = library_profiles

            # Clear existing entries and add the new one
            item.filesystem_entries.clear()
            item.filesystem_entries.append(entry)

            logger.debug(
                f"Created MediaEntry for {item.log_string} with original_filename={debrid_file.filename}"
            )
            if library_profiles:
                logger.debug(
                    f"Matched library profiles for {item.log_string}: {library_profiles}"
                )

    def get_instant_availability(
        self,
        infohash: str,
        item_type: ProcessedItemType,
    ) -> TorrentContainer | None:
        """
        Retrieve cached availability information for a torrent identified by its infohash and item type.

        Queries the active downloader service for instant availability and returns any matching cached torrent containers.

        Returns:
            list[TorrentContainer]: A list of TorrentContainer objects representing available cached torrents; empty list if none are found.
        """

        assert self.service

        return self.service.get_instant_availability(infohash, item_type)

    def add_torrent(self, infohash: str) -> int | str:
        """Add a torrent by infohash"""

        assert self.service

        return self.service.add_torrent(infohash)

    def get_torrent_info(
        self,
        torrent_id: int | str,
    ) -> TorrentInfo:
        """Get information about a torrent"""

        assert self.service

        return self.service.get_torrent_info(
            torrent_id,
        )

    def select_files(self, torrent_id: int | str, container: list[int]) -> None:
        """Select files from a torrent"""

        assert self.service

        self.service.select_files(torrent_id, container)

    def delete_torrent(self, torrent_id: int | str) -> None:
        """Delete a torrent"""

        assert self.service

        self.service.delete_torrent(torrent_id)

    def _any_service_subscription_active(self, services: Sequence[DownloaderBase]) -> bool:
        """Return True if at least one service currently has an active premium subscription."""
        for service in services:
            try:
                user_info = service.get_user_info()
                if user_info and user_info.premium_status == "premium":
                    return True
            except Exception as e:
                logger.debug(f"Failed to check subscription status for {service.key}: {e}")
        return False

    def get_user_info(self, service: "DownloaderBase") -> UserInfo | None:
        """Get user information"""

        return service.get_user_info()

    def start_manual_download(
        self,
        item: MediaItem,
        stream: Stream,
        service: DownloaderBase,
        file_ids: list[int] | None = None,
    ) -> bool:
        """
        Manually start a download for a specific stream.
        Uses the same pipeline as the standard automated download flow:
        1. validate_stream_on_service (validates and gets TorrentContainer)
        2. download_cached_stream_on_service (adds torrent and gets info)
        3. update_item_attributes (matches files and sets active_stream)
        """
        
        # 1. Ensure stream is persisted on item (relationship)
        if stream not in item.streams:
            item.streams.append(stream)
            # Session commit is expected to be handled by caller
        
        # 2. Validate stream and get container (same as standard flow)
        container = self.validate_stream_on_service(
            stream,
            item,
            service,
        )

        if not container:
            logger.warning(f"START_MANUAL_DOWNLOAD: Stream {stream.infohash} not available on {service.key}")
            return False
        
        if container and file_ids and container.files:
            # Filter the container.files list to only include selected files
            container.files = [f for f in container.files if f.file_id in file_ids]

        logger.info(f"START_MANUAL_DOWNLOAD: Validated stream {stream.infohash} on {service.key}")
        
        # 3. Download using standard method (same as standard flow)
        try:
            result = self.download_cached_stream_on_service(stream, container, service)
        except CircuitBreakerOpen as e:
            self._on_circuit_breaker_open(
                service,
                e,
                context=f"manual download for stream {stream.infohash}",
            )
            raise
        except Exception as e:
            logger.error(
                f"START_MANUAL_DOWNLOAD: download_cached_stream_on_service raised: {e}"
            )
            return False
        
        if not result:
            logger.warning(f"START_MANUAL_DOWNLOAD: download_cached_stream_on_service returned None")
            return False
        
        # 4. Update item attributes (same as standard flow)
        if self.update_item_attributes(item, result, service, replace_existing=True):
            # Store state - Manual download completes the 'Downloader' phase, so we are now Downloaded
            item.store_state(States.Downloaded)
            logger.info(f"START_MANUAL_DOWNLOAD: Successfully downloaded {item.log_string} from '{stream.raw_title}'")
            return True
        else:
            logger.warning(f"START_MANUAL_DOWNLOAD: update_item_attributes failed for {item.log_string}")
            return False
