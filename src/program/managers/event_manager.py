from dataclasses import dataclass
from enum import Enum
import heapq
import json
import threading
import time
import traceback
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime, timedelta
from queue import Empty
from threading import Lock
from typing import TYPE_CHECKING, Any, Literal

import sqlalchemy.orm
from loguru import logger
from pydantic import BaseModel

from program.db import db_functions
from program.db.db import db_session
from program.managers.sse_manager import sse_manager
from program.media.item import MediaItem
from program.shutdown import request_shutdown, shutting_down
from program.types import Event, Service
from program.media.state import States
from program.utils import format_api_datetime

if TYPE_CHECKING:
    from program.program import Program


class EventUpdate(BaseModel):
    item_id: int
    emitted_by: str
    run_at: str


@dataclass
class ServiceExecutor:
    service_name: str
    executor: ThreadPoolExecutor


@dataclass(frozen=True)
class FutureWithEvent:
    future: Future[int | tuple[int, datetime] | None]
    event: Event | None
    cancellation_event: threading.Event


class EventType(Enum):
    Completed = 0
    PartiallyCompleted = 1
    Symlinked = 2
    Downloaded = 3
    Scraped = 4


_IN_FLIGHT_SERVICE_TO_PHASE: dict[str, str] = {
    "IndexerService": "indexing",
    "Scraping": "scraping",
    "Downloader": "downloading",
    "FilesystemService": "symlinking",
    "Updater": "updating",
    "PostProcessing": "post_processing",
}

_PHASE_TO_KANBAN: dict[str, str] = {
    "indexing": "added",
    "queued_index": "added",
    "scraping": "scrape",
    "queued_scrape": "scrape",
    "downloading": "download",
    "queued_download": "download",
    "queued_download_deferred": "download",
    "symlinking": "symlink",
    "queued_symlink": "symlink",
    "updating": "update",
    "queued_update": "update",
    "post_processing": "update",
    "queued_post_process": "update",
    "queued_other": "finish",
}

KANBAN_COLUMN_ORDER: tuple[str, ...] = (
    "added",
    "scrape",
    "download",
    "symlink",
    "update",
    "finish",
)

_RECENTLY_FINISHED_TTL = timedelta(minutes=2)


@dataclass
class _RecentlyFinishedEntry:
    item_id: int
    completed_at: datetime
    outcome: Literal["success", "failed"] = "success"
    service_name: str | None = None
    failure_service: str | None = None
    completion_detail: str | None = None


def _queued_pipeline_phase(item_state: States | None, *, deferred: bool) -> str:
    if item_state in (States.Requested, States.Unknown, None):
        return "queued_index"
    if item_state == States.Indexed:
        return "queued_scrape"
    if item_state == States.Scraped:
        return "queued_download_deferred" if deferred else "queued_download"
    if item_state == States.Downloaded:
        return "queued_symlink"
    if item_state == States.Symlinked:
        return "queued_update"
    if item_state in (States.Completed, States.PartiallyCompleted):
        return "queued_post_process"
    return "queued_other"


def resolve_pipeline_phase(
    *,
    item_state: States | None,
    deferred: bool,
    in_flight_service: str | None,
) -> str:
    if in_flight_service:
        return _IN_FLIGHT_SERVICE_TO_PHASE.get(in_flight_service, "queued_other")
    return _queued_pipeline_phase(item_state, deferred=deferred)


def pipeline_phase_to_kanban(phase: str) -> str:
    return _PHASE_TO_KANBAN.get(phase, "finish")


def pipeline_column_sort_key(
    kanban_column: str,
    *,
    in_flight: bool,
    deferred: bool,
    run_at: datetime,
) -> tuple[int, int, int, datetime]:
    """Lower = higher in column (in-flight first, then due, then deferred)."""

    col_order = KANBAN_COLUMN_ORDER.index(kanban_column)
    flight_rank = 0 if in_flight else 1
    defer_rank = 1 if deferred else 0
    return (col_order, flight_rank, defer_rank, run_at)


def pipeline_within_column_sort_key(
    *,
    in_flight: bool,
    deferred: bool,
    run_at: datetime,
) -> tuple[int, int, datetime]:
    """Sort key inside a single Kanban column."""

    flight_rank = 0 if in_flight else 1
    defer_rank = 1 if deferred else 0
    return (flight_rank, defer_rank, run_at)


def limit_pipeline_rows_per_column(
    rows: list[dict[str, Any]],
    per_column_limit: int,
) -> tuple[list[dict[str, Any]], bool]:
    """Cap display rows per column so scrape/index backlog cannot hide the download queue."""

    by_column: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        col = str(row.get("kanban_column") or "finish")
        by_column.setdefault(col, []).append(row)

    limited: list[dict[str, Any]] = []
    truncated = False
    for col in KANBAN_COLUMN_ORDER:
        col_rows = by_column.get(col, [])
        col_rows.sort(
            key=lambda r: pipeline_within_column_sort_key(
                in_flight=bool(r.get("in_flight")),
                deferred=bool(r.get("deferred")),
                run_at=r["run_at"],
            )
        )
        if len(col_rows) > per_column_limit:
            truncated = True
            col_rows = col_rows[:per_column_limit]
        limited.extend(col_rows)

    return limited, truncated


class EventManager:
    """
    Manages the execution of services and the handling of events.
    """

    _DOWNLOADER_QUEUE_LIMIT = 50
    _PIPELINE_PER_COLUMN_LIMIT = 50
    _PIPELINE_RESTORE_WARN_THRESHOLD = 10_000

    # Closest-to-done services first within each dispatch tick.
    _PIPELINE_DISPATCH_SERVICE_ORDER: tuple[str, ...] = (
        "PostProcessing",
        "Updater",
        "FilesystemService",
        "Downloader",
        "Scraping",
        "IndexerService",
    )

    # Narrow dispatch scans: with tens of thousands of queued rows, linear scan +
    # per-row DB load prevents symlink/download/index work from ever being reached.
    _SERVICE_DISPATCH_STATES: dict[str, frozenset[States | None]] = {
        "PostProcessing": frozenset({States.Completed, States.PartiallyCompleted}),
        "Updater": frozenset({States.Symlinked}),
        "FilesystemService": frozenset({States.Downloaded}),
        "Downloader": frozenset({States.Scraped}),
        "Scraping": frozenset({States.Indexed}),
        "IndexerService": frozenset({States.Unknown, States.Requested, None}),
    }

    _RESTORE_STATES: tuple[States, ...] = (
        States.Completed,
        States.Symlinked,
        States.Downloaded,
        States.Scraped,
        States.Indexed,
        States.Requested,
        States.Unknown,
    )

    def __init__(self):
        self._executors = list[ServiceExecutor]()
        self._futures = list[FutureWithEvent]()
        self._queued_events = list[Event]()
        self._running_events = list[Event]()
        self.mutex = Lock()
        self._shutdown = False
        self._downloader_dispatch_lock = threading.Lock()
        self._next_downloader_dispatch_at = 0.0
        self._recently_finished: dict[int, _RecentlyFinishedEntry] = {}
        self._recently_finished_lock = Lock()
        self._pipeline_activity: dict[int, str] = {}
        self._pipeline_activity_lock = Lock()

    _PIPELINE_ACTIVITY_MAX_LEN = 120

    def set_pipeline_activity(self, item_id: int, detail: str) -> None:
        trimmed = detail.strip()
        if not trimmed:
            return
        if len(trimmed) > self._PIPELINE_ACTIVITY_MAX_LEN:
            trimmed = trimmed[: self._PIPELINE_ACTIVITY_MAX_LEN - 3] + "..."
        with self._pipeline_activity_lock:
            self._pipeline_activity[int(item_id)] = trimmed

    def clear_pipeline_activity(self, item_id: int) -> None:
        with self._pipeline_activity_lock:
            self._pipeline_activity.pop(int(item_id), None)

    def get_pipeline_activities(self) -> dict[int, str]:
        with self._pipeline_activity_lock:
            return dict(self._pipeline_activity)

    def shutdown(self, *, wait: bool = False, timeout: float = 3.0) -> None:
        """Stop accepting work and tear down service thread pools."""
        if self._shutdown:
            return

        self._shutdown = True
        request_shutdown()

        with self.mutex:
            for future_with_event in list(self._futures):
                future_with_event.cancellation_event.set()
                if not future_with_event.future.done():
                    future_with_event.future.cancel()
            self._queued_events.clear()

        if wait:
            import concurrent.futures

            pending = [
                future_with_event.future
                for future_with_event in list(self._futures)
                if not future_with_event.future.done()
            ]
            if pending:
                _, not_done = concurrent.futures.wait(
                    pending,
                    timeout=timeout,
                    return_when=concurrent.futures.ALL_COMPLETED,
                )
                if not_done:
                    logger.warning(
                        f"{len(not_done)} background job(s) still running after {timeout}s"
                    )

        for service_executor in self._executors:
            service_executor.executor.shutdown(wait=False, cancel_futures=True)

        self._executors.clear()
        self._futures.clear()
        self._running_events.clear()

    def _find_or_create_executor(self, service_cls: Service) -> ThreadPoolExecutor:
        """
        Finds or creates a ThreadPoolExecutor for the given service class.

        Args:
            service_cls (Service): The service class for which to find or create an executor.

        Returns:
            concurrent.futures.ThreadPoolExecutor: The executor for the service class.
        """

        if self._shutdown or shutting_down():
            raise RuntimeError("Event manager is shutting down")

        service_name = service_cls.__class__.__name__

        for service_executor in self._executors:
            if service_executor.service_name == service_name:
                logger.debug(f"Executor for {service_name} found.")

                return service_executor.executor

        _executor = ThreadPoolExecutor(
            thread_name_prefix=service_name,
            max_workers=self._pipeline_max_workers(),
        )

        self._executors.append(
            ServiceExecutor(service_name=service_name, executor=_executor)
        )

        logger.debug(f"Created executor for {service_name}")

        return _executor

    def _process_future(self, future_with_event: FutureWithEvent, service: Service):
        """
        Processes the result of a future once it is completed.

        Args:
            future (concurrent.futures.Future): The future to process.
            service (type): The service class associated with the future.
        """

        if future_with_event.future.cancelled():
            if future_with_event.event:
                logger.debug(
                    f"Future for {future_with_event.event.log_message} was cancelled."
                )
            else:
                logger.debug(f"Future for {future_with_event} was cancelled.")
            self._drop_future_from_tracking(future_with_event)
            return

        try:
            result = future_with_event.future.result()

            if future_with_event in self._futures:
                self._futures.remove(future_with_event)

            sse_manager.publish_event(
                "event_update", json.dumps(self.get_event_updates())
            )

            if isinstance(result, tuple):
                item_id, timestamp = result
            else:
                item_id, timestamp = result, datetime.now()

            event_item_id: int | None = None
            if future_with_event.event and future_with_event.event.item_id:
                event_item_id = int(future_with_event.event.item_id)

            effective_item_id = item_id or event_item_id

            if effective_item_id:
                self.clear_pipeline_activity(effective_item_id)

            if future_with_event.event:
                self.remove_event_from_running(future_with_event.event)
                if effective_item_id:
                    logger.debug(
                        f"Removed {future_with_event.event.log_message} from running events."
                    )

            if not item_id:
                return

            if future_with_event.cancellation_event.is_set():
                logger.debug(
                    f"Future with Item ID: {item_id} was cancelled; discarding results..."
                )
                return

            existing_item = db_functions.get_item_by_id(item_id)
            if existing_item and existing_item.last_state in (
                States.Paused,
                States.Failed,
            ):
                return

            # Propagate overrides to the new event to maintain setting context across service transitions
            event_overrides = (
                future_with_event.event.overrides if future_with_event.event else None
            )

            self.add_event(
                Event(
                    emitted_by=service,
                    item_id=item_id,
                    run_at=timestamp,
                    overrides=event_overrides,
                )
            )
        except RuntimeError as e:
            if shutting_down() or "interpreter shutdown" in str(e).lower():
                if future_with_event.event:
                    self.remove_event_from_running(future_with_event.event)
                logger.debug(
                    f"Skipped future during shutdown for {future_with_event.event.log_message if future_with_event.event else future_with_event}"
                )
                return
            logger.error(f"Error in future for {future_with_event}: {e}")
            logger.exception(traceback.format_exc())
            self._drop_future_from_tracking(future_with_event)
        except Exception as e:
            logger.error(f"Error in future for {future_with_event}: {e}")
            logger.exception(traceback.format_exc())
            self._drop_future_from_tracking(future_with_event)

        log_message = f"Service {service.__class__.__name__} executed"

        if future_with_event.event:
            log_message += f" with {future_with_event.event.log_message}"

        logger.debug(log_message)

    def _drop_future_from_tracking(self, future_with_event: FutureWithEvent) -> None:
        """Remove a finished or failed future so status endpoints do not grow without bound."""

        if future_with_event in self._futures:
            self._futures.remove(future_with_event)
        if future_with_event.event:
            self.remove_event_from_running(future_with_event.event)
            if future_with_event.event.item_id:
                self.clear_pipeline_activity(int(future_with_event.event.item_id))

    @staticmethod
    def _emitted_by_name(emitted_by: Service | str) -> str:
        if isinstance(emitted_by, str):
            return emitted_by
        if isinstance(emitted_by, type):
            return emitted_by.__name__
        return emitted_by.__class__.__name__

    @staticmethod
    def _service_class_name(service: Service) -> str:
        if isinstance(service, type):
            return service.__name__
        return service.__class__.__name__

    @staticmethod
    def _pipeline_max_workers() -> int:
        try:
            from program.settings import settings_manager

            return int(settings_manager.settings.pipeline_max_workers)
        except Exception:
            return 4

    def _active_future_count(self, service_name: str) -> int:
        count = 0
        for future_with_event in self._futures:
            if not future_with_event.event or future_with_event.future.done():
                continue
            if (
                self._emitted_by_name(future_with_event.event.emitted_by)
                == service_name
            ):
                count += 1
        return count

    def _service_capacity_limit(self) -> int:
        return self._pipeline_max_workers()

    def _service_has_capacity(
        self, service_name: str, program: "Program | None"
    ) -> bool:
        if self._active_future_count(service_name) >= self._service_capacity_limit():
            return False

        if (
            service_name == "Downloader"
            and program
            and program.services
            and program.services.downloader
            and program.services.downloader.initialized
        ):
            pause_until = program.services.downloader.pause_until()
            if pause_until and pause_until > datetime.now():
                return False

        return True

    def _has_active_downloader_future(self) -> bool:
        return self._active_future_count("Downloader") > 0

    def _requeue_for_later_dispatch(
        self,
        event: Event,
        program: "Program | None",
        *,
        service_name: str,
        log_message: bool = True,
    ) -> None:
        if service_name == "Downloader" and program:
            event.run_at = max(
                event.run_at, self._reserve_downloader_dispatch_time(program)
            )
        else:
            event.run_at = max(event.run_at, datetime.now())
        self.add_event_to_queue(event, log_message=log_message)

    def _due_events_for_service(
        self, due_events: list[Event], service_name: str
    ) -> list[Event]:
        """Filter due rows by cached item_state so dispatch does not scan the full queue."""

        target_states = self._SERVICE_DISPATCH_STATES.get(service_name)
        if target_states is None:
            return due_events

        if service_name == "IndexerService":
            return [
                event
                for event in due_events
                if event.item_state in target_states
                or (not event.item_id and event.content_item is not None)
            ]

        return [event for event in due_events if event.item_state in target_states]

    @staticmethod
    def _transition_event_priority(event: Event) -> tuple[int, datetime]:
        state_priority = {
            States.Completed: 0,
            States.PartiallyCompleted: 1,
            States.Symlinked: 2,
            States.Downloaded: 3,
            States.Scraped: 4,
            States.Indexed: 5,
        }
        if event.item_state:
            priority = state_priority.get(event.item_state, 999)
            return (priority, event.run_at)
        return (0, event.run_at)

    def _pipeline_service_by_name(
        self, program: "Program", service_name: str
    ) -> Service | None:
        services = program.services
        if services is None:
            return None

        mapping: dict[str, Service | None] = {
            "IndexerService": services.indexer,
            "Scraping": services.scraping,
            "Downloader": services.downloader,
            "FilesystemService": services.filesystem,
            "Updater": services.updater,
            "PostProcessing": services.post_processing,
        }
        service = mapping.get(service_name)
        if service is None or not getattr(service, "initialized", False):
            return None
        return service

    def _dispatch_one_due_event(
        self,
        program: "Program",
        service: Service,
        service_name: str,
    ) -> Event | None:
        """Remove one due queued event whose next step matches service_name, or fan-out."""

        from program.state_transition import process_event

        now = datetime.now()

        with self.mutex:
            due_events = [
                event for event in self._queued_events if event.run_at <= now
            ]

        candidates = self._due_events_for_service(due_events, service_name)
        candidates.sort(key=self._transition_event_priority)

        for event in candidates:
            if event.item_id:
                existing_item = db_functions.get_item_by_id(event.item_id)
            else:
                existing_item = None

            if existing_item and existing_item.last_state in (
                States.Paused,
                States.Failed,
            ):
                with self.mutex:
                    if event in self._queued_events:
                        self._queued_events.remove(event)
                logger.info(
                    f"Removed queued pipeline event for {existing_item.log_string}: "
                    f"item is {existing_item.last_state.name}"
                )
                continue

            processed = process_event(
                event.emitted_by,
                existing_item,
                event.content_item,
                event.overrides,
            )

            if processed.service is None:
                continue

            if self._service_class_name(processed.service) != service_name:
                continue

            with self.mutex:
                if event not in self._queued_events:
                    continue
                self._queued_events.remove(event)

            items = processed.related_media_items
            if not items:
                continue

            if len(items) > 1:
                for item in items:
                    if item.id:
                        self.add_event(
                            Event(
                                service,
                                item_id=item.id,
                                overrides=processed.overrides,
                            )
                        )
                    else:
                        self.add_event(
                            Event(
                                service,
                                content_item=item,
                                overrides=processed.overrides,
                            )
                        )
                return None

            item = items[0]
            if item.id:
                return Event(
                    service,
                    item_id=item.id,
                    overrides=processed.overrides,
                )
            return Event(
                service,
                content_item=item,
                overrides=processed.overrides,
            )

        return None

    def dispatch_due_jobs(self, program: "Program") -> int:
        """Start due pipeline work up to per-service capacity (no executor backlog)."""

        if program.services is None:
            return 0

        self._compact_queued_item_duplicates(datetime.now())

        dispatched = 0
        for service_name in self._PIPELINE_DISPATCH_SERVICE_ORDER:
            service = self._pipeline_service_by_name(program, service_name)
            if service is None:
                continue

            while self._service_has_capacity(service_name, program):
                event = self._dispatch_one_due_event(program, service, service_name)
                if event is None:
                    break
                self.submit_job(service, program, event)
                dispatched += 1

        return dispatched

    def _in_flight_rows_metadata(self) -> dict[int, tuple[str, bool]]:
        result: dict[int, tuple[str, bool]] = {}
        for future_with_event in self._futures:
            if (
                not future_with_event.event
                or not future_with_event.event.item_id
                or future_with_event.future.done()
            ):
                continue
            item_id = int(future_with_event.event.item_id)
            result[item_id] = (
                self._emitted_by_name(future_with_event.event.emitted_by),
                future_with_event.future.running(),
            )
        return result

    def _downloader_dispatch_interval(self, program: "Program | None") -> float:
        if (
            program
            and program.services
            and program.services.downloader
            and program.services.downloader.initialized
        ):
            return float(program.services.downloader.min_job_interval_seconds)
        return 0.2

    def _reserve_downloader_dispatch_time(self, program: "Program | None") -> datetime:
        """Reserve the next downloader dispatch slot (wall-clock run_at)."""

        interval = self._downloader_dispatch_interval(program)
        with self._downloader_dispatch_lock:
            now_mono = time.monotonic()
            slot_mono = max(now_mono, self._next_downloader_dispatch_at)
            self._next_downloader_dispatch_at = slot_mono + interval
            delay = max(0.0, slot_mono - now_mono)

        return datetime.now() + timedelta(seconds=delay)

    def _maybe_stagger_scraped_run_at(self, event: Event, program: "Program | None") -> None:
        """Space new Scraped queue entries when downloader work is already pending."""

        if event.item_state != States.Scraped:
            return

        has_other_scraped = any(
            e is not event and e.item_state == States.Scraped for e in self._queued_events
        )
        if not self._has_active_downloader_future() and not has_other_scraped:
            return

        event.run_at = max(event.run_at, self._reserve_downloader_dispatch_time(program))

    def _is_downloader_relevant_queued_event(self, event: Event) -> bool:
        if not event.item_id:
            return False
        emitted_by = self._emitted_by_name(event.emitted_by)
        return event.item_state == States.Scraped or emitted_by == "Downloader"

    @staticmethod
    def _queue_event_rank(event: Event, now: datetime) -> tuple[int, datetime]:
        """Lower rank = closer to downloading (due before deferred)."""
        is_deferred = 1 if event.run_at > now else 0
        return (is_deferred, event.run_at)

    def _dedupe_queue_events_by_item_id(
        self, events: list[Event], now: datetime
    ) -> list[Event]:
        best: dict[int, Event] = {}
        for event in events:
            if not event.item_id:
                continue
            item_id = int(event.item_id)
            current = best.get(item_id)
            if current is None or self._queue_event_rank(
                event, now
            ) < self._queue_event_rank(current, now):
                best[item_id] = event
        return list(best.values())

    def _compact_queued_item_duplicates(self, now: datetime) -> int:
        """Collapse duplicate item_id rows in the live queue (in-place)."""

        with self.mutex:
            without_id = [e for e in self._queued_events if not e.item_id]
            with_id = [e for e in self._queued_events if e.item_id]
            deduped = self._dedupe_queue_events_by_item_id(with_id, now)
            removed = len(with_id) - len(deduped)
            if removed <= 0:
                return 0
            self._queued_events = without_id + deduped
            return removed

    def _downloader_relevant_queued_events_locked(self) -> list[Event]:
        return [
            e
            for e in self._queued_events
            if self._is_downloader_relevant_queued_event(e)
        ]

    def _downloader_queue_events_for_item_locked(self, item_id: int) -> list[Event]:
        return [
            e
            for e in self._queued_events
            if e.item_id == item_id and self._is_downloader_relevant_queued_event(e)
        ]

    def _pipeline_queue_events_for_item_locked(self, item_id: int) -> list[Event]:
        return [e for e in self._queued_events if e.item_id == item_id]

    def _deduped_queued_item_events_locked(self, now: datetime) -> list[Event]:
        with_id = [e for e in self._queued_events if e.item_id]
        return self._dedupe_queue_events_by_item_id(with_id, now)

    def _set_downloader_queue_run_at_locked(
        self, item_id: int, new_run_at: datetime
    ) -> list[Event]:
        targets = self._downloader_queue_events_for_item_locked(item_id)
        for event in targets:
            event.run_at = new_run_at
        return targets

    def _set_pipeline_queue_run_at_locked(
        self, item_id: int, new_run_at: datetime
    ) -> list[Event]:
        targets = self._pipeline_queue_events_for_item_locked(item_id)
        for event in targets:
            event.run_at = new_run_at
        return targets

    def _in_flight_service_by_item_id(self) -> dict[int, str]:
        result: dict[int, str] = {}
        for future_with_event in self._futures:
            if (
                not future_with_event.event
                or not future_with_event.event.item_id
                or future_with_event.future.done()
            ):
                continue
            item_id = int(future_with_event.event.item_id)
            result[item_id] = self._emitted_by_name(future_with_event.event.emitted_by)
        return result

    def _program_for_queue_reorder(self) -> "Program | None":
        try:
            from kink import di

            from program.program import Program

            return di[Program]
        except Exception:
            return None

    def prioritize_pipeline_queue_item(self, item_id: int) -> bool:
        """Move a queued pipeline item toward the front by lowering run_at."""

        program = self._program_for_queue_reorder()
        interval = timedelta(seconds=self._downloader_dispatch_interval(program))

        with self.mutex:
            targets = self._pipeline_queue_events_for_item_locked(item_id)
            if not targets or self._id_in_running_events(item_id):
                return False

            now = datetime.now()
            all_peers = self._deduped_queued_item_events_locked(now)
            due_peers = [e for e in all_peers if e.run_at <= now]
            if due_peers:
                new_run_at = min(e.run_at for e in due_peers) - interval
            else:
                new_run_at = now

            current_min = min(e.run_at for e in targets)
            while new_run_at >= current_min:
                new_run_at -= interval

            self._set_pipeline_queue_run_at_locked(item_id, new_run_at)
            logger.debug(
                f"Prioritized item {item_id} in pipeline queue "
                f"(run_at {new_run_at.isoformat()})"
            )
            return True

    def deprioritize_pipeline_queue_item(self, item_id: int) -> bool:
        """Move a queued pipeline item toward the back by raising run_at."""

        program = self._program_for_queue_reorder()
        interval = timedelta(seconds=self._downloader_dispatch_interval(program))

        with self.mutex:
            targets = self._pipeline_queue_events_for_item_locked(item_id)
            if not targets or self._id_in_running_events(item_id):
                return False

            now = datetime.now()
            all_peers = self._deduped_queued_item_events_locked(now)
            max_run_at = max(e.run_at for e in all_peers) if all_peers else now
            new_run_at = max_run_at + interval

            current_max = max(e.run_at for e in targets)
            while new_run_at <= current_max:
                new_run_at += interval

            self._set_pipeline_queue_run_at_locked(item_id, new_run_at)
            logger.debug(
                f"Deprioritized item {item_id} in pipeline queue "
                f"(run_at {new_run_at.isoformat()})"
            )
            return True

    def dequeue_pipeline_queue_item(self, item_id: int) -> bool:
        """Remove queued pipeline events for an item without changing library state."""

        with self.mutex:
            if self._id_in_running_events(item_id):
                return False
            targets = self._pipeline_queue_events_for_item_locked(item_id)
            if not targets:
                return False
            for event in targets:
                if event in self._queued_events:
                    self._queued_events.remove(event)
            logger.debug(
                f"Dequeued item {item_id} from pipeline queue "
                f"({len(targets)} event(s))"
            )
            return True

    def prioritize_downloader_queue_item(self, item_id: int) -> bool:
        """Move a queued downloader item toward the front by lowering run_at."""

        return self.prioritize_pipeline_queue_item(item_id)

    def deprioritize_downloader_queue_item(self, item_id: int) -> bool:
        """Move a queued downloader item toward the back by raising run_at."""

        return self.deprioritize_pipeline_queue_item(item_id)

    def add_event_to_queue(self, event: Event, log_message: bool = True):
        """
        Adds an event to the queue.

        Args:
            event (Event): The event to add to the queue.
        """

        with self.mutex:
            if event.item_id:
                with db_session() as session:
                    try:
                        # Query just the columns we need, avoiding relationship loading entirely
                        item = (
                            session.query(MediaItem)
                            .filter_by(id=event.item_id)
                            .options(
                                sqlalchemy.orm.load_only(
                                    MediaItem.id, MediaItem.last_state
                                )
                            )
                            .one_or_none()
                        )
                    except Exception as e:
                        logger.error(f"Error getting item from database: {e}")
                        return

                    if not item and not event.content_item:
                        logger.error(f"No item found from event: {event.log_message}")
                        return

                    if item:
                        try:
                            parent_blocked = item.is_parent_blocked()
                        except Exception as e:
                            logger.warning(
                                f"Skipping queue for item {event.item_id}: "
                                f"could not resolve parent state ({e})"
                            )
                            return

                        if parent_blocked:
                            logger.debug(
                                f"Not queuing {item.log_string}: Item is {item.last_state}"
                            )
                            return

                        # Cache the item state in the event for efficient priority sorting
                        if item.last_state:
                            event.item_state = item.last_state

            program: Program | None = None
            try:
                from kink import di

                from program.program import Program

                program = di[Program]
            except Exception:
                program = None

            self._maybe_stagger_scraped_run_at(event, program)

            if event.item_id:
                for existing in self._queued_events:
                    if existing.item_id == event.item_id:
                        existing.run_at = max(existing.run_at, event.run_at)
                        if item and item.last_state:
                            existing.item_state = item.last_state
                        elif event.item_state:
                            existing.item_state = event.item_state
                        if log_message:
                            logger.debug(
                                f"Updated queued {event.log_message} "
                                f"(run_at {existing.run_at.isoformat()})"
                            )
                        return

            self._queued_events.append(event)

            if log_message:
                logger.debug(f"Added {event.log_message} to the queue.")

    def remove_event_from_queue(self, event: Event):
        """
        Removes an event from the queue.

        Args:
            event (Event): The event to remove from the queue.
        """

        with self.mutex:
            self._queued_events.remove(event)
            logger.debug(f"Removed {event.log_message} from the queue.")

    def remove_event_from_running(self, event: Event):
        """
        Removes an event from the running events.

        Args:
            event (Event): The event to remove from the running events.
        """

        with self.mutex:
            if event in self._running_events:
                self._running_events.remove(event)
                logger.debug(f"Removed {event.log_message} from running events.")

    def remove_id_from_queue(self, item_id: int):
        """
        Removes an item from the queue.

        Args:
            item (MediaItem): The event item to remove from the queue.
        """

        for event in self._queued_events:
            if event.item_id == item_id:
                self.remove_event_from_queue(event)

    def add_event_to_running(self, event: Event):
        """
        Adds an event to the running events.

        Args:
            event (Event): The event to add to the running events.
        """

        with self.mutex:
            self._running_events.append(event)
            logger.debug(f"Added {event.log_message} to running events.")

    def remove_id_from_running(self, item_id: int):
        """
        Removes an item from the running events.

        Args:
            item (MediaItem): The event item to remove from the running events.
        """

        for event in self._running_events:
            if event.item_id == item_id:
                self.remove_event_from_running(event)

    def remove_id_from_queues(self, item_id: int):
        """
        Removes an item from both the queue and the running events.

        Args:
            item_id: The event item to remove from both the queue and the running events.
        """

        self.remove_id_from_queue(item_id)
        self.remove_id_from_running(item_id)

    def submit_job(
        self,
        service: Service,
        program: "Program",
        event: Event | None = None,
    ) -> None:
        """
        Submits a job to be executed by the service.

        Args:
            service (type): The service class to execute.
            program (Program): The program containing the service.
            item (Event, optional): The event item to process. Defaults to None.
        """

        log_message = (
            f"Submitting service {self._service_class_name(service)} to be executed"
        )

        # Content services dont provide an event.
        if event:
            log_message += f" with {event.log_message}"

        logger.debug(log_message)

        if event is not None and event.item_id:
            service_name = self._service_class_name(service)
            if not self._service_has_capacity(service_name, program):
                if (
                    service_name == "Downloader"
                    and program.services
                    and program.services.downloader
                ):
                    downloader = program.services.downloader
                    pause_until = downloader.pause_until()
                    if pause_until and pause_until > datetime.now():
                        event.run_at = max(event.run_at, pause_until)
                        self.add_event_to_queue(event)
                        logger.debug(
                            f"Downloader paused until {pause_until.isoformat()}; "
                            f"re-queued {event.log_message}"
                        )
                        return

                self._requeue_for_later_dispatch(
                    event,
                    program,
                    service_name=service_name,
                    log_message=False,
                )
                logger.info(
                    f"{service_name} at capacity; re-queued {event.log_message} for "
                    f"{event.run_at.isoformat()}"
                )
                return

        if self._shutdown or shutting_down():
            if event:
                self.remove_event_from_running(event)
            return

        cancellation_event = threading.Event()

        executor = self._find_or_create_executor(service)

        assert program.services

        runner = program.services[service.get_key()]

        try:
            future = executor.submit(
                db_functions.run_thread_with_db_item,
                runner.run,
                service,
                program,
                event,
                cancellation_event,
            )
        except RuntimeError:
            if event:
                self.remove_event_from_running(event)
            return

        future_with_event = FutureWithEvent(
            future=future,
            event=event,
            cancellation_event=cancellation_event,
        )

        self._futures.append(future_with_event)

        sse_manager.publish_event(
            "event_update",
            json.dumps(self.get_event_updates()),
        )

        future.add_done_callback(
            lambda f: self._process_future(future_with_event, service),
        )

    def cancel_job(self, item_id: int, suppress_logs: bool = False):
        """
        Cancels a job associated with the given item.

        Args:
            item_id (int): The event item whose job needs to be canceled.
            suppress_logs (bool): If True, suppresses debug logging for this operation.
        """

        with db_session() as session:
            item_id, related_ids = db_functions.get_item_ids(session, item_id)
            ids_to_cancel = set([item_id] + related_ids)

            future_map = dict[int, list[FutureWithEvent]]()

            for future_with_event in self._futures:
                if future_with_event.event and future_with_event.event.item_id:
                    future_item_id = future_with_event.event.item_id
                    future_map.setdefault(future_item_id, []).append(future_with_event)

            for fid in ids_to_cancel:
                if fid in future_map:
                    for future_with_event in future_map[fid]:
                        self.remove_id_from_queues(fid)

                        if (
                            not future_with_event.future.done()
                            and not future_with_event.future.cancelled()
                        ):
                            try:
                                future_with_event.cancellation_event.set()
                                future_with_event.future.cancel()

                                logger.debug(f"Canceled job for Item ID {fid}")
                            except Exception as e:
                                if not suppress_logs:
                                    logger.error(
                                        f"Error cancelling future for {fid}: {str(e)}"
                                    )

            for fid in ids_to_cancel:
                self.remove_id_from_queues(fid)
                self.clear_pipeline_activity(fid)

    def next(self) -> Event:
        """
        Get the next event in the queue, prioritizing items closest to completion.

        Priority order (highest to lowest):
        0. Items in Completed state (closest to completion)
        1. Items in Symlinked state
        2. Items in Downloaded state
        3. Items in Scraped state
        4. Items in Indexed state
        5. All other states

        Within each priority level, events are sorted by run_at timestamp.

        Performance: Uses cached item_state from Event object to avoid database queries.

        Raises:
            Empty: If the queue is empty or no events are ready to run.

        Returns:
            Event: The next event in the queue.
        """

        while True:
            if self._queued_events:
                with self.mutex:
                    now = datetime.now()

                    # Filter events that are ready to run (run_at <= now)
                    ready_events = [
                        event for event in self._queued_events if event.run_at <= now
                    ]

                    if not ready_events:
                        raise Empty

                    # Define state priority (lower number = higher priority)
                    state_priority = dict[States, int](
                        {
                            States.Completed: 0,
                            States.PartiallyCompleted: 1,
                            States.Symlinked: 2,
                            States.Downloaded: 3,
                            States.Scraped: 4,
                            States.Indexed: 5,
                        }
                    )

                    def get_event_priority(event: Event) -> tuple[int, datetime]:
                        """
                        Returns a tuple for sorting: (state_priority, run_at)
                        Items with higher priority states come first, then sorted by run_at.
                        Uses cached item_state to avoid database queries.
                        """
                        if event.item_state:
                            priority = state_priority.get(event.item_state, 999)
                            return (priority, event.run_at)

                        # Default priority for items without state or content-only events
                        return (0, event.run_at)

                    # Sort by priority (state first, then run_at)
                    ready_events.sort(key=get_event_priority)

                    # Get the highest priority event
                    event = ready_events[0]
                    self._queued_events.remove(event)

                    return event
            raise Empty

    def _id_in_queue(self, _id: int) -> bool:
        """
        Checks if an item with the given ID is in the queue.

        Args:
            _id (int): The ID of the item to check.

        Returns:
            bool: True if the item is in the queue, False otherwise.
        """

        return any(event.item_id == _id for event in self._queued_events)

    def _id_in_running_events(self, _id: int) -> bool:
        """
        Checks if an item with the given ID is in the running events.

        Args:
            _id (int): The ID of the item to check.

        Returns:
            bool: True if the item is in the running events, False otherwise.
        """

        return any(event.item_id == _id for event in self._running_events)

    def _merge_followup_into_queued_item(self, item_id: int, event: Event) -> None:
        """Refresh state and pull run_at forward when a service completes but the item is still queued."""

        from sqlalchemy import select

        from program.media.item import MediaItem

        fresh_state: States | None = None
        with db_session() as session:
            last_state = session.execute(
                select(MediaItem.last_state).where(MediaItem.id == item_id)
            ).scalar_one_or_none()
            if last_state is not None:
                fresh_state = last_state

        with self.mutex:
            for existing in self._queued_events:
                if existing.item_id != item_id:
                    continue
                if fresh_state is not None:
                    existing.item_state = fresh_state
                elif event.item_state:
                    existing.item_state = event.item_state
                existing.run_at = min(existing.run_at, event.run_at)

    def add_event(self, event: Event) -> bool:
        """
        Adds an event to the queue if it is not already present in the queue or running events.

        - If the event has a DB-backed item_id, we keep your existing parent/child
        dedupe logic based on item_id + related ids.
        - If the event is content-only (no item_id), we now dedupe using *all* known ids
        (tmdb/tvdb/imdb) against both queued and running events with a single-pass check.

        Returns:
            True if queued; False if deduped away.
        """

        item_id = None
        related_ids = []

        # Check if the event's item is a show and its seasons or episodes are in the queue or running
        with db_session() as session:
            if event.item_id:
                item_id, related_ids = db_functions.get_item_ids(session, event.item_id)

        if item_id:
            if self._id_in_queue(item_id):
                self._merge_followup_into_queued_item(item_id, event)
                logger.info(
                    f"Item ID {item_id} is already in the queue; merged follow-up."
                )
                return False

            if self._id_in_running_events(item_id):
                logger.info(f"Item ID {item_id} is already running, skipping.")
                return False

            for related_id in related_ids:
                if self._id_in_queue(related_id) or self._id_in_running_events(
                    related_id
                ):
                    logger.info(
                        f"Related item ID {related_id} already in pipeline; "
                        f"skipping enqueue for item ID {item_id}."
                    )

                    return False
        else:
            # Content-only
            if (content_item := event.content_item) is None:
                logger.debug("Event has neither item_id nor content_item; skipping.")
                return False

            # Single-pass checks: queued and running
            if self.item_exists_in_queue(
                content_item,
                self._queued_events,
            ) or self.item_exists_in_queue(
                content_item,
                self._running_events,
            ):
                logger.info(
                    f"Content item {content_item.log_string} is already queued or running, skipping."
                )

                return False

        self.add_event_to_queue(event)

        return True

    def _item_id_in_pipeline(self, item_id: int) -> bool:
        if self._id_in_queue(item_id) or self._id_in_running_events(item_id):
            return True

        for future_with_event in self._futures:
            if (
                future_with_event.event
                and future_with_event.event.item_id == item_id
                and not future_with_event.future.done()
            ):
                return True

        return False

    def _restore_service_for_state(
        self, program: "Program", state: States
    ) -> Service | None:
        services = program.services
        if services is None:
            return None

        if state == States.Symlinked:
            return services.updater if services.updater.initialized else None
        if state == States.Downloaded:
            return (
                services.filesystem if services.filesystem.initialized else None
            )
        if state == States.Scraped:
            return services.downloader if services.downloader.initialized else None
        if state == States.Indexed:
            return services.scraping if services.scraping.initialized else None
        if state in (States.Requested, States.Unknown):
            return services.indexer if services.indexer.initialized else None
        if state in (States.Completed, States.PartiallyCompleted):
            return (
                services.post_processing
                if services.post_processing.initialized
                else None
            )
        return None

    def restore_pipeline_from_db(
        self,
        program: "Program",
        *,
        source: str = "startup",
    ) -> list[int]:
        """
        Re-queue actionable leaf items from the database (no cap, no futures).

        Closest-to-done states first; dispatch_due_jobs admits work under capacity.
        """

        from sqlalchemy import and_, case, exists, or_, select

        from program.media.item import Episode, Season, Show

        if program.services is None:
            return []

        restored_ids: list[int] = []

        state_order = case(
            (MediaItem.last_state == States.Completed, 0),
            (MediaItem.last_state == States.Symlinked, 1),
            (MediaItem.last_state == States.Downloaded, 2),
            (MediaItem.last_state == States.Scraped, 3),
            (MediaItem.last_state == States.Indexed, 4),
            else_=5,
        )

        # Nested exists avoids joining Season+Show (both map to MediaItem → SAWarning)
        episode_has_show = exists(
            select(1)
            .select_from(Episode)
            .where(
                Episode.id == MediaItem.id,
                exists(
                    select(1)
                    .select_from(Season)
                    .where(
                        Season.id == Episode.parent_id,
                        exists(
                            select(1)
                            .select_from(Show)
                            .where(Show.id == Season.parent_id),
                        ),
                    ),
                ),
            )
        )

        now = datetime.now()

        with db_session() as session:
            rows = session.execute(
                select(MediaItem.id, MediaItem.last_state)
                .where(MediaItem.last_state.in_(self._RESTORE_STATES))
                .where(
                    or_(
                        MediaItem.type == "movie",
                        and_(MediaItem.type == "episode", episode_has_show),
                    )
                )
                .order_by(
                    state_order,
                    MediaItem.requested_at.desc().nullslast(),
                    MediaItem.id.desc(),
                )
            ).all()

            for item_id, last_state in rows:
                item_id = int(item_id)
                if self._item_id_in_pipeline(item_id):
                    continue

                target = self._restore_service_for_state(program, last_state)
                # Always queue: use StateTransition when the next service is not up yet
                # so Activity shows the item and dispatch picks it up once initialized.
                emitter: Service | str = target if target is not None else "StateTransition"

                if self.add_event(
                    Event(
                        emitted_by=emitter,
                        item_id=item_id,
                        run_at=now,
                        item_state=last_state,
                    )
                ):
                    restored_ids.append(item_id)

        if restored_ids:
            count = len(restored_ids)
            log_fn = (
                logger.warning
                if count >= self._PIPELINE_RESTORE_WARN_THRESHOLD
                else logger.info
            )
            log_fn(
                f"Restored {count} pipeline queue entries from database ({source})"
            )

        return restored_ids

    def hydrate_scraped_backlog(
        self,
        program: "Program",
        *,
        limit: int | None = None,
    ) -> int:
        """Deprecated alias for startup compatibility."""

        del limit
        return len(self.restore_pipeline_from_db(program, source="startup"))

    def add_item(
        self,
        item: MediaItem,
        service: str | None = None,
    ) -> bool:
        """
        Adds an item to the queue as an event.

        Args:
            item (MediaItem): The item to add to the queue as an event.
        """

        if not db_functions.item_exists_by_any_id(
            item.id,
            item.tvdb_id,
            item.tmdb_id,
            item.imdb_id,
        ):
            if self.add_event(
                Event(
                    service or "Manual",
                    content_item=item,
                )
            ):
                logger.debug(f"Added item with {item.log_string} to the queue.")
                return True

        return False

    def get_event_updates(self) -> dict[str, list[int]]:
        """
        Get the event updates for the SSE manager.

        Returns:
            dict[str, list[int]]: A dictionary with the event types as keys and a list of item IDs as values.
        """

        # Completed futures can linger until their callback runs; do not treat them as in-flight.
        events = [
            future.event
            for future in self._futures
            if future.event and not future.future.done()
        ]
        event_types = [
            "IndexerService",
            "Scraping",
            "Downloader",
            "FilesystemService",
            "Symlinker",
            "Updater",
            "PostProcessing",
        ]

        updates = {event_type: list[int]() for event_type in event_types}

        for event in events:
            if isinstance(event.emitted_by, str):
                key = event.emitted_by
            else:
                key = event.emitted_by.__class__.__name__

            table = updates.get(key, None)

            if table is not None and event.item_id:
                table.append(event.item_id)

        return updates

    def get_downloader_queue_snapshot(
        self,
    ) -> tuple[dict[str, int | str | None | bool], list[dict[str, Any]]]:
        """
        Single pass over the queue: aggregate stats plus top-N rows for the API.

        Avoids scanning/sorting the full queue twice per /downloader_status poll.
        """

        now = datetime.now()
        scraped_queued = 0
        scraped_ready = 0
        deferred = 0
        total_queued = 0
        queue_by_source: dict[str, int] = {}
        next_deferred: datetime | None = None

        def sort_key(event: Event) -> tuple[int, datetime]:
            # Due (ready) before deferred; soonest run_at first within each band.
            is_deferred = 1 if event.run_at > now else 0
            return (is_deferred, event.run_at)

        self._compact_queued_item_duplicates(now)

        raw_matched: list[Event] = []

        with self.mutex:
            for event in self._queued_events:
                if self._is_downloader_relevant_queued_event(event):
                    raw_matched.append(event)

        matched = self._dedupe_queue_events_by_item_id(raw_matched, now)

        for event in matched:
            total_queued += 1

            if event.run_at > now:
                deferred += 1
                if next_deferred is None or event.run_at < next_deferred:
                    next_deferred = event.run_at

            source = self._emitted_by_name(event.emitted_by)
            queue_by_source[source] = queue_by_source.get(source, 0) + 1

            if event.item_state == States.Scraped:
                scraped_queued += 1
                if event.run_at <= now:
                    scraped_ready += 1

        top_events = heapq.nsmallest(
            self._DOWNLOADER_QUEUE_LIMIT, matched, key=sort_key
        )

        rows: list[dict[str, Any]] = []
        for event in top_events:
            rows.append(
                {
                    "item_id": int(event.item_id),
                    "run_at": event.run_at,
                    "queued_at": event.queued_at,
                    "item_state": (
                        event.item_state.name if event.item_state else None
                    ),
                    "emitted_by": self._emitted_by_name(event.emitted_by),
                    "deferred": event.run_at > now,
                }
            )

        next_ready_in_seconds: float | None = None
        if next_deferred is not None:
            next_ready_in_seconds = max(0.0, (next_deferred - now).total_seconds())

        stats = {
            "scraped_queued": scraped_queued,
            "scraped_ready": scraped_ready,
            "deferred": deferred,
            "total_queued": total_queued,
            "downloader_emitted": queue_by_source.get("Downloader", 0),
            "queue_by_source": queue_by_source,
            "next_ready_at": format_api_datetime(next_deferred),
            "next_ready_in_seconds": next_ready_in_seconds,
            "queue_truncated": total_queued > self._DOWNLOADER_QUEUE_LIMIT,
        }
        return stats, rows

    def get_downloader_queue_stats(self) -> dict[str, int | str | None | bool]:
        """Count downloader-related events in the queue."""
        stats, _ = self.get_downloader_queue_snapshot()
        return stats

    def get_downloader_queued_items(self) -> list[dict[str, Any]]:
        """List downloader-relevant queued events with timing metadata."""
        _, rows = self.get_downloader_queue_snapshot()
        return rows

    def record_recently_finished(
        self,
        item_id: int,
        *,
        outcome: Literal["success", "failed"] = "success",
        service_name: str | None = None,
        failure_service: str | None = None,
        completion_detail: str | None = None,
    ) -> None:
        """Remember a completed pipeline item for the Activity Done column (in-memory only)."""

        now = datetime.now()
        with self._recently_finished_lock:
            self._prune_recently_finished_locked(now)
            self._recently_finished[int(item_id)] = _RecentlyFinishedEntry(
                item_id=int(item_id),
                completed_at=now,
                outcome=outcome,
                service_name=service_name,
                failure_service=failure_service if outcome == "failed" else None,
                completion_detail=completion_detail,
            )

    def pop_recently_finished(self, item_id: int) -> None:
        with self._recently_finished_lock:
            self._recently_finished.pop(int(item_id), None)

    def _prune_recently_finished_locked(self, now: datetime | None = None) -> None:
        cutoff = (now or datetime.now()) - _RECENTLY_FINISHED_TTL
        stale = [
            item_id
            for item_id, entry in self._recently_finished.items()
            if entry.completed_at < cutoff
        ]
        for item_id in stale:
            del self._recently_finished[item_id]

    def count_scraped_not_in_pipeline(self) -> int:
        """Deprecated: use count_pipeline_backlog()."""

        return self.count_pipeline_backlog()

    def count_pipeline_backlog(self) -> int:
        """Leaf items restore would enqueue that are not in the live pipeline queue."""

        from sqlalchemy import func, select

        from program.media.item import MediaItem

        in_pipeline: set[int] = set()
        with self.mutex:
            for event in self._queued_events:
                if event.item_id:
                    in_pipeline.add(int(event.item_id))
            in_pipeline.update(self._in_flight_rows_metadata().keys())

        with db_session() as session:
            query = select(func.count(MediaItem.id)).where(
                MediaItem.last_state.in_(self._RESTORE_STATES),
                MediaItem.type.in_(["movie", "episode"]),
            )
            if in_pipeline:
                query = query.where(MediaItem.id.not_in(list(in_pipeline)))
            return int(session.execute(query).scalar_one())

    def get_recently_finished_rows(self) -> list[dict[str, Any]]:
        """Display rows for /activity_status Done column; does not touch the live queue."""

        now = datetime.now()
        with self._recently_finished_lock:
            self._prune_recently_finished_locked(now)
            entries = sorted(
                self._recently_finished.values(),
                key=lambda e: e.completed_at,
                reverse=True,
            )

        rows: list[dict[str, Any]] = []
        for entry in entries:
            failure_svc = entry.failure_service or entry.service_name
            rows.append(
                {
                    "item_id": entry.item_id,
                    "run_at": entry.completed_at,
                    "queued_at": entry.completed_at,
                    "item_state": (
                        States.Failed.name
                        if entry.outcome == "failed"
                        else States.Completed.name
                    ),
                    "emitted_by": entry.service_name or "Pipeline",
                    "deferred": False,
                    "in_flight": False,
                    "pipeline_phase": "recently_finished",
                    "kanban_column": "finish",
                    "completion_outcome": entry.outcome,
                    "failure_service": failure_svc,
                    "completion_detail": entry.completion_detail
                    or entry.service_name,
                }
            )
        return rows

    def retry_failed_pipeline_item(self, item_id: int) -> bool:
        """Re-queue a failed item at the pipeline step that failed."""

        from program.db import db_functions

        item = db_functions.get_item_by_id(item_id)
        if item is None or item.last_state != States.Failed:
            return False

        with self._recently_finished_lock:
            entry = self._recently_finished.get(int(item_id))

        failure_service = (
            (entry.failure_service or entry.service_name) if entry else None
        )
        if not failure_service:
            failure_service = "StateTransition"

        retry_state, event_emitter = self._retry_state_and_emitter_for_service(
            failure_service
        )
        if retry_state is None or event_emitter is None:
            return False

        item.store_state(retry_state)
        self.pop_recently_finished(item_id)
        self.add_event_to_queue(Event(event_emitter, item_id=item_id))
        logger.debug(
            f"Retry failed pipeline item {item_id} at {failure_service} "
            f"(state {retry_state.name})"
        )
        return True

    @staticmethod
    def _retry_state_and_emitter_for_service(
        service_name: str,
    ) -> tuple[States | None, str | None]:
        """Map failure service to library state and queue event emitter."""

        key = service_name.replace(" ", "").lower()
        if "downloader" in key:
            return States.Scraped, "Downloader"
        if "scraping" in key or key == "scraper":
            return States.Indexed, "Scraping"
        if "filesystem" in key:
            return States.Downloaded, "FilesystemService"
        if "updater" in key:
            return States.Symlinked, "Updater"
        if "postprocessing" in key or "post_processing" in key:
            return States.Completed, "PostProcessing"
        if "indexer" in key:
            return States.Requested, "StateTransition"
        return None, None

    def _sync_queued_item_states_from_db(self, events: list[Event]) -> None:
        """Refresh cached item_state from DB so Activity columns match pipeline progress."""

        item_ids = [
            int(event.item_id) for event in events if event.item_id is not None
        ]
        if not item_ids:
            return

        from sqlalchemy import select

        from program.media.item import MediaItem

        unique_ids = list(dict.fromkeys(item_ids))
        states_by_id: dict[int, States] = {}

        with db_session() as session:
            for item_id, last_state in session.execute(
                select(MediaItem.id, MediaItem.last_state).where(
                    MediaItem.id.in_(unique_ids)
                )
            ):
                if last_state is not None:
                    states_by_id[int(item_id)] = last_state

        for event in events:
            if event.item_id:
                state = states_by_id.get(int(event.item_id))
                if state is not None:
                    event.item_state = state

    def get_pipeline_queue_snapshot(
        self,
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        """
        Full pipeline queue: all item_id events plus content-only rows.

        Returns aggregate stats and sorted row dicts for /activity_status.
        """

        now = datetime.now()
        deferred = 0
        total_queued = 0
        queue_by_source: dict[str, int] = {}
        phase_counts: dict[str, int] = {}
        column_counts: dict[str, int] = {col: 0 for col in KANBAN_COLUMN_ORDER}
        next_deferred: datetime | None = None

        self._compact_queued_item_duplicates(now)

        with self.mutex:
            in_flight_meta = self._in_flight_rows_metadata()
            content_only = [e for e in self._queued_events if not e.item_id and e.content_item]
            matched = self._deduped_queued_item_events_locked(now)

        self._sync_queued_item_states_from_db(matched)

        rows: list[dict[str, Any]] = []

        for event in matched:
            item_id = int(event.item_id)
            if item_id in in_flight_meta:
                continue

            deferred_flag = event.run_at > now
            phase = resolve_pipeline_phase(
                item_state=event.item_state,
                deferred=deferred_flag,
                in_flight_service=None,
            )
            kanban = pipeline_phase_to_kanban(phase)
            source = self._emitted_by_name(event.emitted_by)

            total_queued += 1
            phase_counts[phase] = phase_counts.get(phase, 0) + 1
            column_counts[kanban] = column_counts.get(kanban, 0) + 1
            queue_by_source[source] = queue_by_source.get(source, 0) + 1

            if deferred_flag:
                deferred += 1
                if next_deferred is None or event.run_at < next_deferred:
                    next_deferred = event.run_at

            rows.append(
                {
                    "item_id": item_id,
                    "run_at": event.run_at,
                    "queued_at": event.queued_at,
                    "item_state": (
                        event.item_state.name if event.item_state else None
                    ),
                    "emitted_by": source,
                    "deferred": deferred_flag,
                    "in_flight": False,
                    "pipeline_phase": phase,
                    "kanban_column": kanban,
                }
            )

        for event in content_only:
            phase = "queued_index"
            kanban = pipeline_phase_to_kanban(phase)
            source = self._emitted_by_name(event.emitted_by)
            total_queued += 1
            phase_counts[phase] = phase_counts.get(phase, 0) + 1
            column_counts[kanban] = column_counts.get(kanban, 0) + 1
            queue_by_source[source] = queue_by_source.get(source, 0) + 1

            content = event.content_item
            rows.append(
                {
                    "item_id": None,
                    "content_title": content.log_string if content else "New item",
                    "run_at": event.run_at,
                    "queued_at": event.queued_at,
                    "item_state": None,
                    "emitted_by": source,
                    "deferred": event.run_at > now,
                    "in_flight": False,
                    "pipeline_phase": phase,
                    "kanban_column": kanban,
                }
            )

        for item_id, (service_name, actively_running) in in_flight_meta.items():
            phase = resolve_pipeline_phase(
                item_state=None,
                deferred=False,
                in_flight_service=service_name,
            )
            kanban = pipeline_phase_to_kanban(phase)
            phase_counts[phase] = phase_counts.get(phase, 0) + 1
            column_counts[kanban] = column_counts.get(kanban, 0) + 1

            rows.append(
                {
                    "item_id": item_id,
                    "run_at": now,
                    "queued_at": now,
                    "item_state": None,
                    "emitted_by": service_name,
                    "deferred": False,
                    "in_flight": True,
                    "actively_running": actively_running,
                    "pipeline_phase": phase,
                    "kanban_column": kanban,
                }
            )

        total_items = len(rows)
        rows, display_truncated = limit_pipeline_rows_per_column(
            rows, self._PIPELINE_PER_COLUMN_LIMIT
        )
        queue_truncated = display_truncated

        next_ready_in_seconds: float | None = None
        if next_deferred is not None:
            next_ready_in_seconds = max(0.0, (next_deferred - now).total_seconds())

        stats = {
            "total_queued": total_queued,
            "total_items": total_items,
            "deferred": deferred,
            "phase_counts": phase_counts,
            "column_counts": column_counts,
            "queue_by_source": queue_by_source,
            "next_ready_at": format_api_datetime(next_deferred),
            "next_ready_in_seconds": next_ready_in_seconds,
            "queue_truncated": queue_truncated,
        }
        return stats, rows

    def item_exists_in_queue(self, item: MediaItem, queue: list[Event]) -> bool:
        """
        Check in a single pass whether any of the item's identifying ids (id, tmdb_id,
        tvdb_id, imdb_id) is already represented in the given event queue.

        This avoids building temporary sets (lower allocs) and returns early on first match.
        Worst-case O(n), typically faster in practice.

        Args:
            item: The media item to check. Only non-None ids are considered.
            queue: The event list to search.

        Returns:
            True if a match is found; otherwise False.
        """

        item_id = item.id
        tmdb_id = item.tmdb_id
        tvdb_id = item.tvdb_id
        imdb_id = item.imdb_id

        if not (item_id or tmdb_id or tvdb_id or imdb_id):
            return False

        for ev in queue:
            if item_id and ev.item_id == item_id:
                return True

            if (content_item := ev.content_item) is None:
                continue

            if tmdb_id and content_item.tmdb_id == tmdb_id:
                return True

            if tvdb_id and content_item.tvdb_id == tvdb_id:
                return True

            if imdb_id and content_item.imdb_id == imdb_id:
                return True

        return False
