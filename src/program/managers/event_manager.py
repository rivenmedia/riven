from dataclasses import dataclass
from enum import Enum
import heapq
import json
import threading
import time
import traceback
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
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
from program.queue.adapter import (
    content_entry_to_event,
    entry_to_event,
    event_to_content_entry,
    event_to_entry,
)
from program.queue.finished import RecentlyFinishedStore
from program.queue.mapping import (
    KANBAN_COLUMN_ORDER,
    dispatch_priority,
    pipeline_phase_for_entry,
    pipeline_phase_to_kanban,
    resolve_pipeline_phase,
    service_to_stage,
)
from program.queue.pipeline_services import (
    PIPELINE_DISPATCH_SERVICES,
    is_pipeline_service,
)
from program.queue.models import EnqueueResult, PipelineStage, QueueEntry
from program.queue.store import PipelineQueueStore
from program.types import Event, Service
from program.media.state import States
from program.utils import format_api_datetime, naive_local_datetime

_SYNC_CHUNK_SIZE = 500

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


def pipeline_column_sort_key(
    kanban_column: str,
    *,
    in_flight: bool,
    deferred: bool,
    run_at: datetime,
) -> tuple[int, int, int, datetime]:
    """Lower = higher in column (in-flight first, then due, then deferred)."""

    try:
        col_order = KANBAN_COLUMN_ORDER.index(kanban_column)
    except ValueError:
        col_order = len(KANBAN_COLUMN_ORDER)
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
        in_flight_rows = [r for r in col_rows if r.get("in_flight")]
        queued_rows = [r for r in col_rows if not r.get("in_flight")]

        sort_key = lambda r: pipeline_within_column_sort_key(
            in_flight=bool(r.get("in_flight")),
            deferred=bool(r.get("deferred")),
            run_at=naive_local_datetime(r["run_at"]),
        )
        in_flight_rows.sort(key=sort_key)
        queued_rows.sort(key=sort_key)

        remaining = max(0, per_column_limit - len(in_flight_rows))
        if len(queued_rows) > remaining:
            truncated = True
            queued_rows = queued_rows[:remaining]

        limited.extend(in_flight_rows + queued_rows)

    return limited, truncated


class EventManager:
    """
    Manages the execution of services and the handling of events.
    """

    _DOWNLOADER_QUEUE_LIMIT = 50
    _PIPELINE_PER_COLUMN_LIMIT = 50
    _PIPELINE_RESTORE_WARN_THRESHOLD = 10_000

    # Library stages first so symlink/update/post-process are not starved by prepare backlog.
    _PIPELINE_DISPATCH_SERVICE_ORDER: tuple[str, ...] = (
        "FilesystemService",
        "Updater",
        "PostProcessing",
        "Downloader",
        "Scraping",
        "IndexerService",
    )

    _LIBRARY_PIPELINE_SERVICES: frozenset[str] = frozenset(
        {"FilesystemService", "Updater", "PostProcessing"}
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

    # Actionable pipeline steps only. Completed items are terminal (post-processing
    # already ran via store_state after updater); restoring them re-queues the whole
    # library for subtitles.
    _RESTORE_STATES: tuple[States, ...] = (
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
        self._queue = PipelineQueueStore()
        self._running_events = list[Event]()
        self.mutex = Lock()
        self._shutdown = False
        self._downloader_dispatch_lock = threading.Lock()
        self._next_downloader_dispatch_at = 0.0
        self._recently_finished = RecentlyFinishedStore()
        self._paused_pipeline_services: set[str] = set()
        self._paused_pipeline_services_lock = Lock()
        self._pipeline_activity: dict[int, str] = {}
        self._pipeline_activity_lock = Lock()

    @property
    def _queued_events(self) -> list[Event]:
        """Test/back-compat view of the pipeline queue."""

        events = [
            entry_to_event(entry, entry.emitted_by)
            for entry in self._queue.all_item_entries()
        ]
        events.extend(
            content_entry_to_event(entry)
            for entry in self._queue.content_entries()
        )
        return events

    @_queued_events.setter
    def _queued_events(self, events: list[Event]) -> None:
        self._queue.clear()
        now = datetime.now()
        best_by_id: dict[int, Event] = {}
        for event in events:
            if event.item_id:
                item_id = int(event.item_id)
                current = best_by_id.get(item_id)
                if current is None or self._queue_event_rank(
                    event, now
                ) < self._queue_event_rank(current, now):
                    best_by_id[item_id] = event
                continue
            content = event_to_content_entry(event)
            if content is not None:
                self._queue.enqueue_content(content)
        for event in best_by_id.values():
            entry = event_to_entry(event)
            if entry is not None:
                self._queue.enqueue(entry)

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
            self._queue.clear()

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
            max_workers=self._executor_max_workers(service_name),
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

            service_name = (
                service.__class__.__name__
                if not isinstance(service, str)
                else service
            )

            # Post-processing is terminal; re-queuing loops via dispatch + StateTransition.
            if service_name == "PostProcessing":
                self._record_terminal_outcome_if_applicable(int(item_id), service_name)
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
            self._record_terminal_outcome_if_applicable(int(item_id), service_name)
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

    @staticmethod
    def _pipeline_library_max_workers() -> int:
        try:
            from program.settings import settings_manager

            return int(settings_manager.settings.pipeline_library_max_workers)
        except Exception:
            return 32

    @staticmethod
    def _pipeline_post_processing_max_workers() -> int:
        try:
            from program.settings import settings_manager

            return int(settings_manager.settings.pipeline_post_processing_max_workers)
        except Exception:
            return 16

    def _executor_max_workers(self, service_name: str) -> int:
        return self._service_capacity_limit(service_name)

    def _service_capacity_limit(self, service_name: str) -> int:
        if service_name == "PostProcessing":
            return self._pipeline_post_processing_max_workers()
        if service_name in self._LIBRARY_PIPELINE_SERVICES:
            return self._pipeline_library_max_workers()
        return self._pipeline_max_workers()

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

    def _service_has_capacity(
        self, service_name: str, program: "Program | None"
    ) -> bool:
        if self._active_future_count(service_name) >= self._service_capacity_limit(
            service_name
        ):
            return False

        if (
            service_name == "Downloader"
            and program
            and program.services
            and program.services.downloader
            and program.services.downloader.initialized
        ):
            pause_until = naive_local_datetime(program.services.downloader.pause_until())
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
        run_at = naive_local_datetime(event.run_at)
        if service_name == "Downloader" and program:
            event.run_at = max(
                run_at, self._reserve_downloader_dispatch_time(program)
            )
        else:
            event.run_at = max(run_at, datetime.now())
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
    def _transition_event_priority(event: Event) -> tuple[int, datetime, datetime]:
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
            return (
                priority,
                naive_local_datetime(event.run_at),
                naive_local_datetime(event.queued_at),
            )
        return (
            0,
            naive_local_datetime(event.run_at),
            naive_local_datetime(event.queued_at),
        )

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
        stage = service_to_stage(service_name)
        if stage is None:
            return None

        if service_name == "IndexerService":
            content_entry = self._queue.pop_content_due(now)
            if content_entry is not None:
                event = content_entry_to_event(content_entry)
                processed = process_event(
                    "StateTransition",
                    None,
                    event.content_item,
                    event.overrides,
                )
                if (
                    processed.service is not None
                    and self._service_class_name(processed.service) == service_name
                    and processed.related_media_items
                ):
                    item = processed.related_media_items[0]
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
                self._queue.enqueue_content(content_entry)

        due_entries = self._queue.peek_due(stage, now, limit=500)
        due_entries.sort(key=dispatch_priority)

        for entry in due_entries:
            event = entry_to_event(entry, entry.emitted_by)
            if event.item_id:
                existing_item = db_functions.get_item_by_id(event.item_id)
            else:
                existing_item = None

            if existing_item and existing_item.last_state in (
                States.Paused,
                States.Failed,
            ):
                self._queue.dequeue(int(event.item_id))
                logger.info(
                    f"Removed queued pipeline event for {existing_item.log_string}: "
                    f"item is {existing_item.last_state.name}"
                )
                continue

            processed = process_event(
                "StateTransition",
                existing_item,
                event.content_item,
                event.overrides,
            )

            if processed.service is None:
                if (
                    service_name == "PostProcessing"
                    and existing_item
                    and existing_item.last_state == States.Completed
                    and self._emitted_by_name(entry.emitted_by) == "PostProcessing"
                ):
                    self._queue.dequeue(int(event.item_id))
                continue

            if self._service_class_name(processed.service) != service_name:
                continue

            if not self._queue.dequeue(int(event.item_id)):
                continue

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

    def pause_pipeline_service(self, service_name: str) -> bool:
        if not is_pipeline_service(service_name):
            return False
        with self._paused_pipeline_services_lock:
            self._paused_pipeline_services.add(service_name)
        logger.info(f"Paused pipeline dispatch for {service_name}")
        return True

    def resume_pipeline_service(self, service_name: str) -> bool:
        if not is_pipeline_service(service_name):
            return False
        with self._paused_pipeline_services_lock:
            self._paused_pipeline_services.discard(service_name)
        logger.info(f"Resumed pipeline dispatch for {service_name}")
        return True

    def is_pipeline_service_paused(self, service_name: str) -> bool:
        with self._paused_pipeline_services_lock:
            return service_name in self._paused_pipeline_services

    def get_pipeline_services_paused(self) -> dict[str, bool]:
        with self._paused_pipeline_services_lock:
            paused = set(self._paused_pipeline_services)
        return {
            name: name in paused for name in PIPELINE_DISPATCH_SERVICES
        }

    def dispatch_due_jobs(self, program: "Program") -> int:
        """Start due pipeline work up to per-service capacity (no executor backlog)."""

        self._normalize_queued_run_at_times()

        if program.services is None:
            return 0

        dispatched = 0
        for service_name in self._PIPELINE_DISPATCH_SERVICE_ORDER:
            if self.is_pipeline_service_paused(service_name):
                continue
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
            entry.item_state == States.Scraped
            for entry in self._queue.all_item_entries()
            if entry.item_id != event.item_id
        )
        if not self._has_active_downloader_future() and not has_other_scraped:
            return

        event.run_at = max(
            naive_local_datetime(event.run_at),
            self._reserve_downloader_dispatch_time(program),
        )

    def _is_downloader_relevant_queued_event(self, event: Event) -> bool:
        if not event.item_id:
            return False
        emitted_by = self._emitted_by_name(event.emitted_by)
        return event.item_state == States.Scraped or emitted_by == "Downloader"

    @staticmethod
    def _queue_event_rank(event: Event, now: datetime) -> tuple[int, datetime]:
        """Lower rank = closer to downloading (due before deferred)."""
        run_at = naive_local_datetime(event.run_at)
        is_deferred = 1 if run_at > now else 0
        return (is_deferred, run_at)

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
            entry = self._queue.get(int(item_id))
            if entry is None or self._id_in_running_events(item_id):
                return False

            now = datetime.now()
            all_peers = self._queue.all_item_entries()
            due_peers = [
                e for e in all_peers if naive_local_datetime(e.run_at) <= now
            ]
            if due_peers:
                new_run_at = (
                    min(naive_local_datetime(e.run_at) for e in due_peers) - interval
                )
            else:
                new_run_at = now

            current_min = naive_local_datetime(entry.run_at)
            while new_run_at >= current_min:
                new_run_at -= interval

            self._queue.update_run_at(int(item_id), new_run_at)
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
            entry = self._queue.get(int(item_id))
            if entry is None or self._id_in_running_events(item_id):
                return False

            now = datetime.now()
            all_peers = self._queue.all_item_entries()
            max_run_at = (
                max(naive_local_datetime(e.run_at) for e in all_peers)
                if all_peers
                else now
            )
            new_run_at = max_run_at + interval

            current_max = naive_local_datetime(entry.run_at)
            while new_run_at <= current_max:
                new_run_at += interval

            self._queue.update_run_at(int(item_id), new_run_at)
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
            if not self._queue.dequeue(int(item_id)):
                return False
            logger.debug(f"Dequeued item {item_id} from pipeline queue")
            return True

    def prioritize_downloader_queue_item(self, item_id: int) -> bool:
        """Move a queued downloader item toward the front by lowering run_at."""

        return self.prioritize_pipeline_queue_item(item_id)

    def deprioritize_downloader_queue_item(self, item_id: int) -> bool:
        """Move a queued downloader item toward the back by raising run_at."""

        return self.deprioritize_pipeline_queue_item(item_id)

    def _normalize_queued_run_at_times(self) -> None:
        """Repair aware run_at values so dispatch can compare with naive datetime.now()."""

        with self.mutex:
            self._queue.normalize_run_at()

    def add_event_to_queue(self, event: Event, log_message: bool = True):
        """
        Adds an event to the queue.

        Args:
            event (Event): The event to add to the queue.
        """

        event.run_at = naive_local_datetime(event.run_at)

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

            queue_entry = event_to_entry(event)
            if queue_entry is not None:
                if item and item.last_state:
                    queue_entry.item_state = item.last_state
                elif event.item_state:
                    queue_entry.item_state = event.item_state
                result = self._queue.enqueue(queue_entry)
                if result == EnqueueResult.merged:
                    if log_message:
                        existing = self._queue.get(int(event.item_id))
                        run_at = (
                            existing.run_at.isoformat()
                            if existing
                            else queue_entry.run_at.isoformat()
                        )
                        logger.debug(
                            f"Updated queued {event.log_message} (run_at {run_at})"
                        )
                    return
                if log_message:
                    logger.debug(f"Added {event.log_message} to the queue.")
                return

            content_entry = event_to_content_entry(event)
            if content_entry is not None:
                self._queue.enqueue_content(content_entry)
                if log_message:
                    logger.debug(f"Added {event.log_message} to the queue.")

    def remove_event_from_queue(self, event: Event):
        """
        Removes an event from the queue.

        Args:
            event (Event): The event to remove from the queue.
        """

        with self.mutex:
            if event.item_id:
                self._queue.dequeue(int(event.item_id))
            elif event.content_item:
                self._queue.dequeue_content(event.content_item)
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

        with self.mutex:
            self._queue.dequeue(int(item_id))

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
                    pause_until = naive_local_datetime(downloader.pause_until())
                    if pause_until and pause_until > datetime.now():
                        event.run_at = max(
                            naive_local_datetime(event.run_at), pause_until
                        )
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
            now = datetime.now()
            ready_events: list[Event] = []
            for stage in PipelineStage:
                for entry in self._queue.peek_due(stage, now, limit=1000):
                    ready_events.append(entry_to_event(entry, entry.emitted_by))
            for content in self._queue.content_entries():
                if naive_local_datetime(content.run_at) <= now:
                    ready_events.append(content_entry_to_event(content))

            if not ready_events:
                raise Empty

            ready_events.sort(key=self._transition_event_priority)
            winner = ready_events[0]
            entry = event_to_entry(winner)
            if entry is not None:
                self._queue.dequeue(int(entry.item_id))
            elif winner.content_item:
                self._queue.dequeue_content(winner.content_item)
            return winner

    def _id_in_queue(self, _id: int) -> bool:
        """
        Checks if an item with the given ID is in the queue.

        Args:
            _id (int): The ID of the item to check.

        Returns:
            bool: True if the item is in the queue, False otherwise.
        """

        return self._queue.contains_item(_id)

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
            self._queue.merge_item(
                int(item_id),
                run_at=event.run_at,
                item_state=fresh_state if fresh_state is not None else event.item_state,
            )

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
            if self._queue.contains_content(
                content_item
            ) or self.item_exists_in_queue(
                content_item,
                self._running_events,
            ):
                logger.info(
                    f"Content item {content_item.log_string} is already queued or running, skipping."
                )

                return False

        if event.item_id:
            self.pop_recently_finished(int(event.item_id))

        self.add_event_to_queue(event)

        return True

    def _record_terminal_outcome_if_applicable(
        self, item_id: int, service_name: str
    ) -> None:
        """Done column: failures and post-processing success only."""

        item = db_functions.get_item_by_id(item_id)
        if not item or not item.last_state:
            self.pop_recently_finished(item_id)
            return

        if item.last_state == States.Failed:
            self.record_recently_finished(
                item_id,
                outcome="failed",
                service_name=service_name,
                failure_service=service_name,
            )
        elif service_name == "PostProcessing":
            self.record_recently_finished(
                item_id,
                outcome="success",
                service_name="PostProcessing",
            )
        else:
            self.pop_recently_finished(item_id)

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
            (MediaItem.last_state == States.Symlinked, 0),
            (MediaItem.last_state == States.Downloaded, 1),
            (MediaItem.last_state == States.Scraped, 2),
            (MediaItem.last_state == States.Indexed, 3),
            else_=4,
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

        from program.pipeline.restore_targets import scrape_restore_target_id

        scraping = program.services.scraping
        now = datetime.now()
        seen_targets: set[int] = set()

        with db_session() as session:
            rows = session.execute(
                select(MediaItem.id, MediaItem.last_state, MediaItem.type)
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

            for item_id, last_state, item_type in rows:
                item_id = int(item_id)
                if (
                    last_state is None
                    or last_state not in self._RESTORE_STATES
                    or self._item_id_in_pipeline(item_id)
                ):
                    continue

                enqueue_id = item_id
                enqueue_state = last_state

                if (
                    last_state == States.Indexed
                    and item_type == "episode"
                    and scraping.initialized
                ):
                    coalesced_id = scrape_restore_target_id(
                        session, item_id, scraping
                    )
                    if coalesced_id is None:
                        continue
                    enqueue_id = coalesced_id
                    if enqueue_id != item_id:
                        target_item = db_functions.get_item_by_id(
                            enqueue_id, session=session
                        )
                        if target_item is not None and target_item.last_state is not None:
                            enqueue_state = target_item.last_state

                if enqueue_id in seen_targets:
                    continue

                _item_id, related_ids = db_functions.get_item_ids(session, enqueue_id)
                skip = False
                for related_id in related_ids:
                    if self._queue.contains_item(related_id) or self._id_in_running_events(
                        related_id
                    ):
                        skip = True
                        break
                if skip:
                    continue

                self.pop_recently_finished(enqueue_id)
                entry = QueueEntry(
                    item_id=enqueue_id,
                    item_state=enqueue_state,
                    run_at=now,
                    queued_at=now,
                    emitted_by="StateTransition",
                )
                if self._queue.enqueue(entry) == EnqueueResult.added:
                    seen_targets.add(enqueue_id)
                    restored_ids.append(enqueue_id)

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

        def sort_key(entry: QueueEntry) -> tuple[int, datetime]:
            run_at = naive_local_datetime(entry.run_at)
            is_deferred = 1 if run_at > now else 0
            return (is_deferred, run_at)

        self._normalize_queued_run_at_times()

        with self.mutex:
            matched = self._queue.downloader_entries(now)

        for entry in matched:
            total_queued += 1
            run_at = naive_local_datetime(entry.run_at)

            if run_at > now:
                deferred += 1
                if next_deferred is None or run_at < next_deferred:
                    next_deferred = run_at

            source = entry.emitted_by
            queue_by_source[source] = queue_by_source.get(source, 0) + 1

            if entry.item_state == States.Scraped:
                scraped_queued += 1
                if run_at <= now:
                    scraped_ready += 1

        top_entries = heapq.nsmallest(
            self._DOWNLOADER_QUEUE_LIMIT, matched, key=sort_key
        )

        rows: list[dict[str, Any]] = []
        for entry in top_entries:
            rows.append(
                {
                    "item_id": int(entry.item_id),
                    "run_at": entry.run_at,
                    "queued_at": entry.queued_at,
                    "item_state": (
                        entry.item_state.name if entry.item_state else None
                    ),
                    "emitted_by": entry.emitted_by,
                    "deferred": naive_local_datetime(entry.run_at) > now,
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

        self._recently_finished.record(
            item_id,
            outcome=outcome,
            service_name=service_name,
            failure_service=failure_service,
            completion_detail=completion_detail,
        )

    def pop_recently_finished(self, item_id: int) -> None:
        self._recently_finished.pop(item_id)

    def count_scraped_not_in_pipeline(self) -> int:
        """Deprecated: use count_pipeline_backlog()."""

        return self.count_pipeline_backlog()

    def count_pipeline_backlog(self) -> int:
        """Leaf items restore would enqueue that are not in the live pipeline queue."""

        from sqlalchemy import func, select

        from program.media.item import MediaItem

        in_pipeline: set[int] = set()
        with self.mutex:
            in_pipeline.update(
                int(entry.item_id) for entry in self._queue.all_item_entries()
            )
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

        return self._recently_finished.display_rows()

    def retry_failed_pipeline_item(self, item_id: int) -> bool:
        """Re-queue a failed item at the pipeline step that failed."""

        from program.db import db_functions

        item = db_functions.get_item_by_id(item_id)
        if item is None or item.last_state != States.Failed:
            return False

        failure_service = self._recently_finished.failure_service_for(item_id)
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
            for offset in range(0, len(unique_ids), _SYNC_CHUNK_SIZE):
                chunk = unique_ids[offset : offset + _SYNC_CHUNK_SIZE]
                for item_id, last_state in session.execute(
                    select(MediaItem.id, MediaItem.last_state).where(
                        MediaItem.id.in_(chunk)
                    )
                ):
                    if last_state is not None:
                        states_by_id[int(item_id)] = last_state

        for event in events:
            if event.item_id:
                state = states_by_id.get(int(event.item_id))
                if state is not None:
                    event.item_state = state

    def _queued_event_row_dict(
        self,
        event: Event,
        *,
        now: datetime,
        in_flight: bool = False,
        in_flight_service: str | None = None,
        actively_running: bool = False,
    ) -> dict[str, Any]:
        deferred_flag = (
            naive_local_datetime(event.run_at) > now if not in_flight else False
        )
        phase = resolve_pipeline_phase(
            item_state=event.item_state if not in_flight else None,
            deferred=deferred_flag,
            in_flight_service=in_flight_service,
        )
        kanban = pipeline_phase_to_kanban(phase)
        source = self._emitted_by_name(event.emitted_by)
        row: dict[str, Any] = {
            "item_id": int(event.item_id) if event.item_id else None,
            "run_at": now if in_flight else event.run_at,
            "queued_at": now if in_flight else event.queued_at,
            "item_state": (
                event.item_state.name if event.item_state and not in_flight else None
            ),
            "emitted_by": in_flight_service or source,
            "deferred": deferred_flag,
            "in_flight": in_flight,
            "pipeline_phase": phase,
            "kanban_column": kanban,
        }
        if in_flight:
            row["actively_running"] = actively_running
        return row

    def get_pipeline_queue_snapshot(
        self,
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        """
        Pipeline queue stats over the full deduped queue; display rows only for
        per-column top-K (plus all in-flight and content-only rows).
        """

        now = datetime.now()
        self._normalize_queued_run_at_times()
        per_limit = self._PIPELINE_PER_COLUMN_LIMIT

        with self.mutex:
            in_flight_meta = self._in_flight_rows_metadata()
            qstats = self._queue.stats(now)

        total_queued = qstats.total_queued
        deferred = qstats.deferred
        next_deferred = qstats.next_deferred
        phase_counts = dict(qstats.phase_counts)
        column_counts = dict(qstats.column_counts)
        queue_by_source = dict(qstats.queue_by_source)
        queue_truncated = qstats.queue_truncated

        in_flight_by_column: dict[str, list[tuple[int, str, bool]]] = {}
        for item_id, (service_name, actively_running) in in_flight_meta.items():
            phase = resolve_pipeline_phase(
                item_state=None,
                deferred=False,
                in_flight_service=service_name,
            )
            kanban = pipeline_phase_to_kanban(phase)
            phase_counts[phase] = phase_counts.get(phase, 0) + 1
            column_counts[kanban] = column_counts.get(kanban, 0) + 1
            in_flight_by_column.setdefault(kanban, []).append(
                (item_id, service_name, actively_running)
            )

        display_queued: list[Event] = []
        for col in KANBAN_COLUMN_ORDER:
            inflight = in_flight_by_column.get(col, [])
            remaining = max(0, per_limit - len(inflight))
            queued_entries, col_truncated = self._queue.peek_display_for_kanban(
                col, now, remaining
            )
            if col_truncated:
                queue_truncated = True
            for entry in queued_entries:
                if int(entry.item_id) in in_flight_meta:
                    continue
                display_queued.append(entry_to_event(entry, entry.emitted_by))

        self._sync_queued_item_states_from_db(display_queued)

        rows: list[dict[str, Any]] = []
        for col in KANBAN_COLUMN_ORDER:
            inflight = in_flight_by_column.get(col, [])
            inflight.sort(
                key=lambda row: pipeline_within_column_sort_key(
                    in_flight=True,
                    deferred=False,
                    run_at=now,
                )
            )
            for item_id, service_name, actively_running in inflight:
                phase = resolve_pipeline_phase(
                    item_state=None,
                    deferred=False,
                    in_flight_service=service_name,
                )
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
                        "kanban_column": col,
                    }
                )

            col_events = [
                event
                for event in display_queued
                if pipeline_phase_to_kanban(
                    resolve_pipeline_phase(
                        item_state=event.item_state,
                        deferred=naive_local_datetime(event.run_at) > now,
                        in_flight_service=None,
                    )
                )
                == col
            ]
            col_events.sort(
                key=lambda event: pipeline_within_column_sort_key(
                    in_flight=False,
                    deferred=naive_local_datetime(event.run_at) > now,
                    run_at=naive_local_datetime(event.run_at),
                )
            )
            for event in col_events:
                rows.append(self._queued_event_row_dict(event, now=now))

        with self.mutex:
            for content in self._queue.content_entries():
                phase = "queued_index"
                kanban = pipeline_phase_to_kanban(phase)
                source = content.emitted_by
                rows.append(
                    {
                        "item_id": None,
                        "content_title": (
                            content.content_item.log_string
                            if content.content_item
                            else "New item"
                        ),
                        "run_at": content.run_at,
                        "queued_at": content.queued_at,
                        "item_state": None,
                        "emitted_by": source,
                        "deferred": naive_local_datetime(content.run_at) > now,
                        "in_flight": False,
                        "pipeline_phase": phase,
                        "kanban_column": kanban,
                    }
                )

        total_items = total_queued + len(in_flight_meta)
        recently_finished_count = self._recently_finished.count()
        if recently_finished_count:
            column_counts["finish"] = (
                column_counts.get("finish", 0) + recently_finished_count
            )

        next_ready_in_seconds: float | None = None
        if next_deferred is not None:
            next_ready_in_seconds = max(0.0, (next_deferred - now).total_seconds())

        stats = {
            "total_queued": total_queued,
            "total_items": total_items,
            "in_flight_total": len(in_flight_meta),
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
