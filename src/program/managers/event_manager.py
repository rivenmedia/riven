import heapq
import os
import threading
import time
import traceback
from collections import deque
from typing import List, Optional
import sqlalchemy.orm
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime
from queue import Empty
from threading import Lock
from typing import Dict, List

from loguru import logger
from pydantic import BaseModel

from program.db import db_functions
from program.db.db import db
from program.managers.websocket_manager import manager as websocket_manager
from program.types import Event
from program.media.item import MediaItem
from program.utils.logging import (
    log_memory_usage, log_queue_operation, perf_logger
)


class EventUpdate(BaseModel):
    item_id: int
    emitted_by: str
    run_at: str


class EventManager:
    """
    Manages the execution of services and the handling of events with memory management.
    """
    def __init__(self):
        self._executors: list[ThreadPoolExecutor] = []
        self._futures: list[Future] = []
        # Use heap for efficient priority queue operations
        self._queued_events: list[tuple[datetime, int, Event]] = []  # (run_at, counter, event)
        self._running_events: list[Event] = []
        self.mutex = Lock()
        self._counter = 0  # For stable sorting when run_at times are equal
        self._last_cleanup = time.time()  # Track last executor cleanup

        # Memory management limits - balanced for concurrent processing
        self.MAX_QUEUED_EVENTS = int(os.environ.get('RIVEN_MAX_QUEUED_EVENTS', '500'))   # Increased for concurrent processing
        self.MAX_RUNNING_EVENTS = int(os.environ.get('RIVEN_MAX_RUNNING_EVENTS', '1000'))  # Removed artificial bottleneck
        self.MAX_FUTURES = int(os.environ.get('RIVEN_MAX_FUTURES', '1000'))               # Increased for concurrent futures
        self.MAX_BATCH_QUEUE = int(os.environ.get('RIVEN_MAX_BATCH_QUEUE', '50'))        # Increased for batching

        # Service-specific concurrency limits - balanced for performance
        self.SERVICE_CONCURRENCY_LIMITS = {
            'Downloader': int(os.environ.get('RIVEN_MAX_DOWNLOADER_CONCURRENT', '2')),   # Conservative for API limits
            'Scraping': int(os.environ.get('RIVEN_MAX_SCRAPING_CONCURRENT', '10')),      # Higher for scrapers
            'TraktIndexer': int(os.environ.get('RIVEN_MAX_TRAKT_CONCURRENT', '5')),      # Moderate for Trakt
            'StateTransition': int(os.environ.get('RIVEN_MAX_STATE_CONCURRENT', '20')),  # Increased - lightweight operations
            'RetryLibrary': int(os.environ.get('RIVEN_MAX_RETRY_CONCURRENT', '5')),      # Increased for retries
            'ManualAPI': int(os.environ.get('RIVEN_MAX_MANUAL_CONCURRENT', '10')),       # Manual API operations
        }

        # Memory monitoring
        self._memory_warnings_sent = 0
        self._last_memory_check = time.time()
        self._memory_check_interval = 60  # Check every minute

        # Queue status monitoring
        self._last_queue_status_log = time.time()
        self._last_running_events_log = time.time()
        self._running_events_log_interval = 30  # Log running events every 30 seconds

        # Performance tracking disabled to prevent hanging
        # self._event_start_times = {}  # Track when events start processing
        # self._slow_service_threshold = 15  # Log if service takes longer than 15 seconds
        self._queue_status_interval = 30  # Log queue status every 30 seconds

        # Batch processing optimization
        self._batch_queue = deque()  # Queue for batching similar events
        self._batch_size = 5  # Process events in batches
        self._last_batch_process = time.time()
        self._batch_timeout = 2.0  # Process batch after 2 seconds even if not full

    def _find_or_create_executor(self, service_cls) -> ThreadPoolExecutor:
        """
        Finds or creates an optimized ThreadPoolExecutor for the given service class.

        Args:
            service_cls (type): The service class for which to find or create an executor.

        Returns:
            concurrent.futures.ThreadPoolExecutor: The executor for the service class.
        """
        service_name = getattr(service_cls, '__name__', str(service_cls))
        env_var_name = f"{service_name.upper()}_MAX_WORKERS"

        # Get optimized default worker counts based on service type
        default_workers = self._get_optimal_worker_count(service_name)
        max_workers = int(os.environ.get(env_var_name, default_workers))

        # Find existing executor
        for executor in self._executors:
            if executor["_name_prefix"] == service_name:
                # Check if executor is still healthy
                if not executor["_executor"]._shutdown:
                    logger.debug(f"Executor for {service_name} found.")
                    return executor["_executor"]
                else:
                    # Remove shutdown executor
                    logger.warning(f"Removing shutdown executor for {service_name}")
                    self._executors.remove(executor)
                    break

        # Create new optimized executor
        _executor = ThreadPoolExecutor(
            thread_name_prefix=service_name,
            max_workers=max_workers
        )

        executor_info = {
            "_name_prefix": service_name,
            "_executor": _executor,
            "_max_workers": max_workers,
            "_created_at": time.time()
        }

        self._executors.append(executor_info)
        logger.debug(f"Created optimized executor for {service_name} with {max_workers} max workers.")
        return _executor

    def _get_optimal_worker_count(self, service_name: str) -> int:
        """
        Get optimal worker count based on service type and system capabilities.

        Args:
            service_name: Name of the service

        Returns:
            Optimal number of workers for the service
        """
        import os
        cpu_count = os.cpu_count() or 4

        # Service-specific optimizations
        service_configs = {
            # I/O intensive services can handle more workers
            'Scraping': min(8, cpu_count * 2),  # High concurrency for scraping
            'Downloader': min(4, cpu_count),    # Moderate concurrency for downloads
            'TraktIndexer': min(3, cpu_count),  # Conservative for API rate limits
            'Symlinker': min(2, cpu_count),     # File I/O operations
            'Updater': min(2, cpu_count),       # File operations
            'SymlinkLibrary': 1,                # Sequential file operations
            'PostProcessing': 1,                # Sequential processing
            'ManualAPI': min(3, cpu_count),     # Manual API operations
        }

        return service_configs.get(service_name, 1)  # Conservative default

    def _check_memory_limits(self) -> bool:
        """
        Check if we're approaching memory limits and take action if needed.

        Returns:
            bool: True if within limits, False if limits exceeded
        """
        current_time = time.time()

        # Only check periodically to avoid overhead
        if current_time - self._last_memory_check < self._memory_check_interval:
            return True

        self._last_memory_check = current_time

        # Check queue sizes
        queued_count = len(self._queued_events)
        running_count = len(self._running_events)
        futures_count = len(self._futures)
        batch_count = len(self._batch_queue)

        # More aggressive warnings at lower thresholds
        if queued_count > self.MAX_QUEUED_EVENTS * 0.5:  # 50% threshold
            logger.log("QUEUE", f"Queue growing: {queued_count}/{self.MAX_QUEUED_EVENTS} events")

        if queued_count > self.MAX_QUEUED_EVENTS * 0.8:  # 80% threshold
            logger.warning(f"Queue approaching limit: {queued_count}/{self.MAX_QUEUED_EVENTS} events")
            # Start cleanup early
            self._cleanup_old_queued_events()

        if running_count > self.MAX_RUNNING_EVENTS * 0.7:  # 70% threshold
            logger.warning(f"Running events approaching limit: {running_count}/{self.MAX_RUNNING_EVENTS}")

        # Enforce hard limits
        if queued_count >= self.MAX_QUEUED_EVENTS:
            logger.error(f"Queue limit reached: {queued_count}/{self.MAX_QUEUED_EVENTS}. Dropping new events.")
            self._cleanup_old_queued_events()
            return False

        if running_count >= self.MAX_RUNNING_EVENTS:
            logger.error(f"Too many running events: {running_count}. System may be overloaded.")
            return False

        if futures_count >= self.MAX_FUTURES:
            self._cleanup_completed_futures()
            return False

        if batch_count >= self.MAX_BATCH_QUEUE:
            self._process_event_batch()  # Force process batch

        # Periodic queue status logging
        if current_time - self._last_queue_status_log > self._queue_status_interval:
            self._log_queue_status()
            self._last_queue_status_log = current_time

        return True

    def _cleanup_old_queued_events(self):
        """Remove oldest queued events when limit is reached."""
        with self.mutex:
            current_count = len(self._queued_events)
            if current_count >= self.MAX_QUEUED_EVENTS * 0.8:  # Start cleanup at 80%
                # Remove more aggressively - 30% of events to give more breathing room
                remove_count = max(current_count // 3, 10)  # Remove at least 10 events

                # Sort by run_at time and remove oldest
                self._queued_events.sort(key=lambda x: x[0])  # Sort by run_at
                removed_events = self._queued_events[:remove_count]
                self._queued_events = self._queued_events[remove_count:]

                # Re-heapify after removal
                heapq.heapify(self._queued_events)

                logger.log("CLEANUP", f"Removed {remove_count} oldest queued events to prevent memory overflow")
                perf_logger.increment_counter("events_cleaned_up", remove_count)

                # Log some details about removed events
                for run_at, counter, event in removed_events[:3]:  # Log first 3
                    logger.debug(f"Cleaned up old event: {event.log_message} (scheduled for {run_at})")

                log_memory_usage("After queue cleanup")

    def _log_queue_status(self):
        """Log current queue status for monitoring."""
        stats = self.get_memory_stats()

        if stats["queued_events"] > 0 or stats["running_events"] > 0:
            queue_msg = f"Queue: {stats['queued_events']}/{stats['max_queued_events']}"
            running_msg = f"Running: {stats['running_events']}/{stats['max_running_events']}"
            futures_msg = f"Futures: {stats['futures']}"

            # Show breakdown if there are items
            breakdown_parts = []
            if stats.get("queue_breakdown"):
                for service, count in stats["queue_breakdown"].items():
                    breakdown_parts.append(f"{service}:{count}")

            breakdown_str = f" ({', '.join(breakdown_parts)})" if breakdown_parts else ""

            logger.log("QUEUE", f"{queue_msg} | {running_msg} | {futures_msg}{breakdown_str}")

    def _cleanup_completed_futures(self):
        """Remove completed futures to prevent memory accumulation."""
        completed_futures = []
        active_futures = []

        for future in self._futures:
            if future.done():
                completed_futures.append(future)
            else:
                active_futures.append(future)

        self._futures = active_futures

        if completed_futures:
            logger.debug(f"Cleaned up {len(completed_futures)} completed futures")

    def get_memory_stats(self) -> Dict[str, int]:
        """Get current memory usage statistics."""
        # Get queue breakdown by service type
        queue_breakdown = {}
        running_breakdown = {}

        with self.mutex:
            for run_at, counter, event in self._queued_events:
                service_name = getattr(event.emitted_by, '__name__', str(event.emitted_by))
                queue_breakdown[service_name] = queue_breakdown.get(service_name, 0) + 1

            for event in self._running_events:
                service_name = getattr(event.emitted_by, '__name__', str(event.emitted_by))
                running_breakdown[service_name] = running_breakdown.get(service_name, 0) + 1

        return {
            "queued_events": len(self._queued_events),
            "running_events": len(self._running_events),
            "futures": len(self._futures),
            "batch_queue": len(self._batch_queue),
            "executors": len(self._executors),
            "max_queued_events": self.MAX_QUEUED_EVENTS,
            "max_running_events": self.MAX_RUNNING_EVENTS,
            "max_futures": self.MAX_FUTURES,
            "max_batch_queue": self.MAX_BATCH_QUEUE,
            "queue_breakdown": queue_breakdown,
            "running_breakdown": running_breakdown
        }

    def cleanup_executors(self):
        """Clean up shutdown or idle executors to free resources."""
        current_time = time.time()
        executors_to_remove = []

        for executor_info in self._executors:
            executor = executor_info["_executor"]

            # Remove shutdown executors
            if executor._shutdown:
                executors_to_remove.append(executor_info)
                continue

            # Check for idle executors (no active threads for 10 minutes)
            created_at = executor_info.get("_created_at", current_time)
            if (current_time - created_at > 600 and  # 10 minutes old
                len(executor._threads) == 0):  # No active threads
                logger.debug(f"Shutting down idle executor for {executor_info['_name_prefix']}")
                executor.shutdown(wait=False)
                executors_to_remove.append(executor_info)

        # Remove cleaned up executors
        for executor_info in executors_to_remove:
            self._executors.remove(executor_info)

        if executors_to_remove:
            logger.debug(f"Cleaned up {len(executors_to_remove)} idle/shutdown executors")

    def get_executor_stats(self) -> Dict[str, Dict]:
        """Get statistics about all executors for monitoring."""
        stats = {}
        for executor_info in self._executors:
            service_name = executor_info["_name_prefix"]
            executor = executor_info["_executor"]

            stats[service_name] = {
                "max_workers": executor_info["_max_workers"],
                "active_threads": len(executor._threads),
                "shutdown": executor._shutdown,
                "created_at": executor_info.get("_created_at", 0),
                "uptime_minutes": (time.time() - executor_info.get("_created_at", time.time())) / 60
            }

        return stats

    def add_events_batch(self, events: List[Event]):
        """
        Add multiple events to the queue in a batch for better performance.

        Args:
            events: List of events to add
        """
        if not events:
            return

        # Pre-validate all events outside of mutex
        validated_events = []
        for event in events:
            if self._validate_event_for_queue(event):
                validated_events.append(event)

        if not validated_events:
            return

        # Add all validated events to queue in single mutex acquisition
        with self.mutex:
            for event in validated_events:
                heapq.heappush(self._queue, event)
                self._counter += 1

        logger.debug(f"Added batch of {len(validated_events)} events to queue")

    def _validate_event_for_queue(self, event: Event) -> bool:
        """
        Validate an event for queue addition without holding mutex.

        Args:
            event: Event to validate

        Returns:
            True if event should be queued
        """
        if not event.item_id:
            return True  # Content events don't need item validation

        try:
            with db.Session() as session:
                item = session.query(MediaItem).filter_by(id=event.item_id).options(
                    sqlalchemy.orm.load_only(MediaItem.id, MediaItem.last_state)
                ).one_or_none()

                if not item and not event.content_item:
                    logger.error(f"No item found from event: {event.log_message}")
                    return False

                if item and item.is_parent_blocked():
                    logger.debug(f"Not queuing {item.log_string if item.log_string else event.log_message}: Item is {item.last_state.name}")
                    return False

                return True

        except Exception as e:
            logger.error(f"Error validating event for queue: {e}")
            return False

    def _process_future(self, future, service):
        """
        Processes the result of a future once it is completed.

        Args:
            future (concurrent.futures.Future): The future to process.
            service (type): The service class associated with the future.
        """

        if future.cancelled():
            if hasattr(future, "event") and future.event:
                logger.debug(f"Future for {future.event.log_message} was cancelled.")
            else:
                logger.debug(f"Future for {future} was cancelled.")
            return  # Skip processing if the future was cancelled

        try:
            # Get the result to ensure any exceptions are raised
            future.result()
            if future in self._futures:
                self._futures.remove(future)
            websocket_manager.publish("event_update", self.get_event_updates())

            # Remove the completed event from running events
            if hasattr(future, 'event') and future.event:
                self.remove_event_from_running(future.event)
                logger.debug(f"Removed {future.event.log_message} from running events.")

            # Check if the future was cancelled
            if future.cancellation_event.is_set():
                logger.debug(f"Future was cancelled, discarding results...")
                return

            # NOTE: State transitions and next service dispatch are handled by
            # db_functions.run_thread_with_db_item, so we don't need to add events here
            # This prevents duplicate event creation and infinite loops

        except Exception as e:
            logger.error(f"Error in future for {future}: {e}")
            logger.exception(traceback.format_exc())
        service_name = getattr(service, '__name__', str(service))
        log_message = f"Service {service_name} executed"
        if hasattr(future, "event"):
            log_message += f" with {future.event.log_message}"
        logger.debug(log_message)

    def add_event_to_queue(self, event: Event, log_message=True):
        """
        Adds an event to the queue with optimized mutex usage and memory management.

        Args:
            event (Event): The event to add to the queue.
        """
        # Check memory limits before adding
        if not self._check_memory_limits():
            logger.warning(f"Memory limits exceeded, dropping event: {event.log_message}")
            perf_logger.increment_counter("events_dropped_memory_limit")
            return

        # Perform database operations outside of mutex to reduce contention
        if event.item_id:
            with db.Session() as session:
                try:
                    # Query just the columns we need, avoiding relationship loading entirely
                    item = session.query(MediaItem).filter_by(id=event.item_id).options(
                        sqlalchemy.orm.load_only(MediaItem.id, MediaItem.last_state)
                    ).one_or_none()
                except Exception as e:
                    logger.error(f"Error getting item from database: {e}")
                    return

                if not item and not event.content_item:
                    logger.error(f"No item found from event: {event.log_message}")
                    return

                if item and item.is_parent_blocked():
                    logger.debug(f"Not queuing {item.log_string if item.log_string else event.log_message}: Item is {item.last_state.name}")
                    return

        # Only hold mutex for the actual queue modification
        with self.mutex:
            # Double-check limit after acquiring mutex
            if len(self._queued_events) >= self.MAX_QUEUED_EVENTS:
                logger.warning(f"Queue full ({len(self._queued_events)}), dropping event: {event.log_message}")
                perf_logger.increment_counter("events_dropped_queue_full")
                return

            # Defensive check: ensure run_at is never None
            if event.run_at is None:
                logger.warning(f"Event {event.log_message} has None run_at, setting to current time")
                event.run_at = datetime.now()

            # Use heap for efficient priority queue
            self._counter += 1
            heapq.heappush(self._queued_events, (event.run_at, self._counter, event))

            # Log queue operation with current size
            log_queue_operation("Event added", len(self._queued_events), event.item_id)

        if log_message:
            logger.debug(f"Added {event.log_message} to the queue.")

        perf_logger.increment_counter("events_queued")

    def remove_event_from_queue(self, event: Event):
        """
        Removes an event from the queue (heap structure).

        Args:
            event (Event): The event to remove from the queue.
        """
        with self.mutex:
            # Find and remove the event from the heap
            for i, (run_at, counter, queued_event) in enumerate(self._queued_events):
                if queued_event == event:
                    # Replace with last element and heapify
                    self._queued_events[i] = self._queued_events[-1]
                    self._queued_events.pop()
                    if i < len(self._queued_events):
                        heapq.heapify(self._queued_events)
                    logger.debug(f"Removed {event.log_message} from the queue.")
                    return
            logger.warning(f"Event {event.log_message} not found in queue for removal.")

    def remove_event_from_running(self, event: Event):
        """
        Removes an event from the running events and tracks performance.

        Args:
            event (Event): The event to remove from the running events.
        """
        with self.mutex:
            if event in self._running_events:
                self._running_events.remove(event)

                # Performance tracking disabled to prevent hanging
                # event_key = f"{event.item_id or 'content'}_{getattr(event.emitted_by, '__name__', str(event.emitted_by))}"
                # start_time = self._event_start_times.pop(event_key, None)

                logger.debug(f"Removed {event.log_message} from running events.")

    def remove_id_from_queue(self, item_id: str):
        """
        Removes an item from the queue.

        Args:
            item_id (str): The event item ID to remove from the queue.
        """
        with self.mutex:
            # Find events to remove (need to extract from heap tuples)
            events_to_remove = []
            for run_at, counter, event in self._queued_events:
                if event.item_id == item_id:
                    events_to_remove.append(event)

        # Remove events outside of the iteration
        for event in events_to_remove:
            self.remove_event_from_queue(event)

    def add_event_to_running(self, event: Event):
        """
        Adds an event to the running events with memory limit checking.

        Args:
            event (Event): The event to add to the running events.
        """
        with self.mutex:
            # Check global running events limit (now much higher)
            if len(self._running_events) >= self.MAX_RUNNING_EVENTS:
                # Log service breakdown to understand what's slow
                service_breakdown = {}
                for e in self._running_events:
                    service_name = getattr(e.emitted_by, '__name__', str(e.emitted_by))
                    service_breakdown[service_name] = service_breakdown.get(service_name, 0) + 1

                logger.warning(f"High running events count ({len(self._running_events)}), service breakdown: {service_breakdown}")
                logger.error(f"Too many running events ({len(self._running_events)}), cannot add: {event.log_message}")
                return False

            # Check service-specific concurrency limits to prevent API rate limiting
            service_name = getattr(event.emitted_by, '__name__', str(event.emitted_by))
            if service_name in self.SERVICE_CONCURRENCY_LIMITS:
                # Count how many events of this service type are already running
                service_count = sum(1 for e in self._running_events
                                  if getattr(e.emitted_by, '__name__', str(e.emitted_by)) == service_name)

                if service_count >= self.SERVICE_CONCURRENCY_LIMITS[service_name]:
                    logger.debug(f"Service-specific limit reached for {service_name}: {service_count}/{self.SERVICE_CONCURRENCY_LIMITS[service_name]}")
                    return False

            self._running_events.append(event)

            # Performance tracking disabled to prevent hanging
            # event_key = f"{event.item_id or 'content'}_{getattr(event.emitted_by, '__name__', str(event.emitted_by))}"
            # self._event_start_times[event_key] = time.time()

            logger.debug(f"Added {event.log_message} to running events.")

            # Periodic logging disabled to prevent hanging
            # current_time = time.time()
            # if current_time - self._last_running_events_log > self._running_events_log_interval:
            #     self._log_running_events_status()
            #     self._last_running_events_log = current_time

            return True

    def _log_running_events_status(self):
        """Log current running events status with performance insights"""
        with self.mutex:
            if not self._running_events:
                return

            # Count events by service type and track long-running ones
            service_breakdown = {}
            long_running_events = []
            current_time = time.time()

            for event in self._running_events:
                service_name = getattr(event.emitted_by, '__name__', str(event.emitted_by))
                service_breakdown[service_name] = service_breakdown.get(service_name, 0) + 1

                # Check for long-running events
                event_key = f"{event.item_id or 'content'}_{service_name}"
                start_time = self._event_start_times.get(event_key)
                if start_time:
                    duration = current_time - start_time
                    if duration > self._slow_service_threshold:
                        long_running_events.append({
                            'service': service_name,
                            'item': event.item_id or 'content',
                            'duration': duration
                        })

            # Log if we have a significant number of running events
            total_running = len(self._running_events)
            if total_running > 50:  # Only log if we have many running events
                logger.info(f"📊 Running events status: {total_running} total - {service_breakdown}")

                # Log long-running events that might be bottlenecks
                if long_running_events:
                    logger.warning(f"🐌 Long-running events ({len(long_running_events)}):")
                    for event_info in long_running_events[:5]:  # Show top 5 slowest
                        logger.warning(f"   {event_info['service']}: {event_info['item']} ({event_info['duration']:.1f}s)")

    def remove_id_from_running(self, item_id: str):
        """
        Removes an item from the running events.

        Args:
            item (MediaItem): The event item to remove from the running events.
        """
        for event in self._running_events:
            if event.item_id == item_id:
                self.remove_event_from_running(event)

    def remove_id_from_queues(self, item_id: str):
        """
        Removes an item from both the queue and the running events.

        Args:
            item_id: The event item to remove from both the queue and the running events.
        """
        self.remove_id_from_queue(item_id)
        self.remove_id_from_running(item_id)

    def submit_job(self, service, program, event=None):
        """
        Submits a job to be executed by the service.

        Args:
            service (type): The service class to execute.
            program (Program): The program containing the service.
            item (Event, optional): The event item to process. Defaults to None.
        """
        service_name = getattr(service, '__name__', str(service))
        log_message = f"Submitting service {service_name} to be executed"
        # Content services dont provide an event.
        if event:
            log_message += f" with {event.log_message}"
        logger.debug(log_message)

        # Periodic cleanup of idle executors (every 5 minutes)
        current_time = time.time()
        if current_time - self._last_cleanup > 300:  # 5 minutes
            self.cleanup_executors()
            self._cleanup_completed_futures()  # Also cleanup futures
            self._last_cleanup = current_time

        # Check futures limit before adding
        if len(self._futures) >= self.MAX_FUTURES:
            self._cleanup_completed_futures()
            if len(self._futures) >= self.MAX_FUTURES:
                service_name = getattr(service, '__name__', str(service))
                logger.error(f"Too many futures ({len(self._futures)}), cannot submit job for {service_name}")
                return

        cancellation_event = threading.Event()
        executor = self._find_or_create_executor(service)

        # Handle different types of services/functions
        if isinstance(service, str):
            # Handle function-based events (like "RetryLibrary", "StateTransition", "ManualAPI")
            if service in ["RetryLibrary", "StateTransition", "UpdateOngoing", "ManualAPI"]:
                # These events should trigger state transitions directly without running a service
                # They use a dummy generator function that yields the item to trigger state processing
                def dummy_service(item):
                    yield item
                future = executor.submit(db_functions.run_thread_with_db_item, dummy_service, service, program, event, cancellation_event)
            else:
                logger.error(f"Unknown function-based service: {service}")
                return
        else:
            # Handle regular service classes
            if service not in program.all_services:
                logger.error(f"Service {getattr(service, '__name__', str(service))} not found in program.all_services")
                return
            future = executor.submit(db_functions.run_thread_with_db_item, program.all_services[service].run, service, program, event, cancellation_event)
        future.cancellation_event = cancellation_event
        if event:
            future.event = event
        self._futures.append(future)
        websocket_manager.publish("event_update", self.get_event_updates())
        future.add_done_callback(lambda f:self._process_future(f, service))

    def cancel_job(self, item_id: str, suppress_logs=False):
        """
        Cancels a job associated with the given item.

        Args:
            item_id (int): The event item whose job needs to be canceled.
            suppress_logs (bool): If True, suppresses debug logging for this operation.
        """
        with db.Session() as session:
            item_id, related_ids = db_functions.get_item_ids(session, item_id)
            ids_to_cancel = set([item_id] + related_ids)

            future_map = {}
            for future in self._futures:
                if hasattr(future, "event") and hasattr(future.event, "item_id"):
                    future_item_id = future.event.item_id
                    future_map.setdefault(future_item_id, []).append(future)

            for fid in ids_to_cancel:
                if fid in future_map:
                    for future in future_map[fid]:
                        self.remove_id_from_queues(fid)
                        if not future.done() and not future.cancelled():
                            try:
                                future.cancellation_event.set()
                                future.cancel()
                                logger.debug(f"Canceled job for Item ID {fid}")
                            except Exception as e:
                                if not suppress_logs:
                                    logger.error(f"Error cancelling future for {fid}: {str(e)}")

    def next(self) -> Event:
        """
        Get the next event in the queue with optimized heap operations.

        Raises:
            Empty: If the queue is empty.

        Returns:
            Event: The next event in the queue.
        """
        with self.mutex:
            if not self._queued_events:
                raise Empty

            # Peek at the earliest event without removing it
            run_at, counter, event = self._queued_events[0]

            # Defensive check: handle None run_at
            if run_at is None:
                logger.warning(f"Event {event.log_message} has None run_at in queue, fixing and returning immediately")
                event.run_at = datetime.now()
                heapq.heappop(self._queued_events)
                return event

            if datetime.now() >= run_at:
                # Remove and return the earliest event
                heapq.heappop(self._queued_events)
                return event

        # No events are ready, but provide info about when next event is due
        raise Empty

    def get_next_event_time(self) -> float:
        """
        Get the number of seconds until the next scheduled event is ready.

        Returns:
            float: Seconds until next event (0 if events are ready now, None if no events)
        """
        with self.mutex:
            if not self._queued_events:
                return None

            # Get the earliest event time
            run_at, _, _ = self._queued_events[0]
            if run_at is None:
                return 0  # Event should run immediately

            # Calculate seconds until event is ready
            now = datetime.now()
            if now >= run_at:
                return 0  # Event is ready now

            seconds_until = (run_at - now).total_seconds()
            return max(0, seconds_until)

    def _id_in_queue(self, _id: str) -> bool:
        """
        Checks if an item with the given ID is in the queue.

        Args:
            _id (str): The ID of the item to check.

        Returns:
            bool: True if the item is in the queue, False otherwise.
        """
        return any(event.item_id == _id for run_at, counter, event in self._queued_events)

    def _id_in_running_events(self, _id: str) -> bool:
        """
        Checks if an item with the given ID is in the running events.

        Args:
            _id (str): The ID of the item to check.

        Returns:
            bool: True if the item is in the running events, False otherwise.
        """
        return any(event.item_id == _id for event in self._running_events)

    def add_event(self, event: Event) -> bool:
        """
        Adds an event to the queue if it is not already present in the queue or running events.

        Args:
            event (Event): The event to add to the queue.

        Returns:
            bool: True if the event was added to the queue, False if it was already present.
        """
        # Check if the event's item is a show and its seasons or episodes are in the queue or running
        with db.Session() as session:
            item_id, related_ids = db_functions.get_item_ids(session, event.item_id)
        if item_id:
            if self._id_in_queue(item_id):
                logger.debug(f"Item ID {item_id} is already in the queue, skipping.")
                return False
            if self._id_in_running_events(item_id):
                logger.debug(f"Item ID {item_id} is already running, skipping.")
                return False
            for related_id in related_ids:
                if self._id_in_queue(related_id) or self._id_in_running_events(related_id):
                    logger.debug(f"Child of Item ID {item_id} is already in the queue or running, skipping.")
                    return False
        else:
            imdb_id = event.content_item.imdb_id
            if any(event.content_item and event.content_item.imdb_id == imdb_id for run_at, counter, event in self._queued_events):
                logger.debug(f"Content Item with IMDB ID {imdb_id} is already in queue, skipping.")
                return False
            if any(event.content_item and event.content_item.imdb_id == imdb_id for event in self._running_events):
                logger.debug(f"Content Item with IMDB ID {imdb_id} is already running, skipping.")
                return False

        self.add_event_to_queue(event)
        return True

    def add_item(self, item, service: str = "Manual") -> bool:
        """
        Adds an item to the queue as an event.

        Args:
            item (MediaItem): The item to add to the queue as an event.
        """
        # For now lets just support imdb_ids...
        if not db_functions.get_item_by_external_id(imdb_id=item.imdb_id):
            if self.add_event(Event(service, content_item=item)):
                logger.debug(f"Added item with IMDB ID {item.imdb_id} to the queue.")


    def get_event_updates(self) -> Dict[str, List[str]]:
        """
        Get the event updates for the SSE manager.

        Returns:
            Dict[str, List[str]]: A dictionary with the event types as keys and a list of item IDs as values.
        """
        events = [future.event for future in self._futures if hasattr(future, "event")]
        event_types = ["Scraping", "Downloader", "Symlinker", "Updater", "PostProcessing"]

        updates = {event_type: [] for event_type in event_types}
        for event in events:
            service_name = getattr(event.emitted_by, '__name__', str(event.emitted_by))
            table = updates.get(service_name, None)
            if table is not None:
                table.append(event.item_id)

        return updates