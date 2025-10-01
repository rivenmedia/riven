import threading
import traceback
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime
from queue import Empty
from threading import Lock
from typing import Dict, List, Optional

import sqlalchemy.orm
from loguru import logger
from pydantic import BaseModel

from program.db import db_functions
from program.db.db import db
from program.managers.websocket_manager import manager as websocket_manager
from program.media.item import MediaItem
from program.types import Event


class EventUpdate(BaseModel):
    item_id: int
    emitted_by: str
    run_at: str


class EventManager:
    """
    Manages the execution of services and the handling of events.
    """
    def __init__(self):
        self._executors: list[ThreadPoolExecutor] = []
        self._futures: list[Future] = []
        self._queued_events: list[Event] = []
        self._running_events: list[Event] = []
        self.mutex = Lock()

    def _find_or_create_executor(self, service_cls) -> ThreadPoolExecutor:
        """
        Finds or creates a ThreadPoolExecutor for the given service class.

        Args:
            service_cls (type): The service class for which to find or create an executor.

        Returns:
            concurrent.futures.ThreadPoolExecutor: The executor for the service class.
        """
        service_name = service_cls.__name__
        for executor in self._executors:
            if executor["_name_prefix"] == service_name:
                logger.debug(f"Executor for {service_name} found.")
                return executor["_executor"]
        _executor = ThreadPoolExecutor(thread_name_prefix=service_name, max_workers=1)
        self._executors.append({ "_name_prefix": service_name, "_executor": _executor })
        logger.debug(f"Created executor for {service_name}")
        return _executor

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
            result = future.result()
            if future in self._futures:
                self._futures.remove(future)
            websocket_manager.publish("event_update", self.get_event_updates())
            if isinstance(result, tuple):
                item_id, timestamp = result
            else:
                item_id, timestamp = result, datetime.now()
            if item_id:
                self.remove_event_from_running(future.event)
                logger.debug(f"Removed {future.event.log_message} from running events.")
                if future.cancellation_event.is_set():
                    logger.debug(f"Future with Item ID: {item_id} was cancelled discarding results...")
                    return
                self.add_event(Event(emitted_by=service, item_id=item_id, run_at=timestamp))
        except Exception as e:
            logger.error(f"Error in future for {future}: {e}")
            logger.exception(traceback.format_exc())
            # TODO(spoked): Here we should remove it from the running events so it can be retried, right?
            # self.remove_event_from_queue(future.event)
        log_message = f"Service {service.__name__} executed"
        if hasattr(future, "event"):
            log_message += f" with {future.event.log_message}"
        logger.debug(log_message)

    def add_event_to_queue(self, event: Event, log_message=True):
        """
        Adds an event to the queue.

        Args:
            event (Event): The event to add to the queue.
        """
        with self.mutex:
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

                    if item.is_parent_blocked():
                        logger.debug(f"Not queuing {item.log_string if item.log_string else event.log_message}: Item is {item.last_state.name}")
                        return

                    # Cache the item state in the event for efficient priority sorting
                    if item and item.last_state:
                        event.item_state = item.last_state.name

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

    def remove_id_from_queue(self, item_id: str):
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
        log_message = f"Submitting service {service.__name__} to be executed"
        # Content services dont provide an event.
        if event:
            log_message += f" with {event.log_message}"
        logger.debug(log_message)

        cancellation_event = threading.Event()
        executor = self._find_or_create_executor(service)
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
            
            for fid in ids_to_cancel:
                self.remove_id_from_queues(fid)

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
                    ready_events = [event for event in self._queued_events if event.run_at <= now]

                    if not ready_events:
                        raise Empty

                    # Define state priority (lower number = higher priority)
                    state_priority = {
                        "Completed": 0,
                        "PartiallyCompleted": 1,
                        "Symlinked": 2,
                        "Downloaded": 3,
                        "Scraped": 4,
                        "Indexed": 5,
                    }

                    def get_event_priority(event: Event) -> tuple:
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

    def _id_in_queue(self, _id: str) -> bool:
        """
        Checks if an item with the given ID is in the queue.

        Args:
            _id (str): The ID of the item to check.

        Returns:
            bool: True if the item is in the queue, False otherwise.
        """
        return any(event.item_id == _id for event in self._queued_events)

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

        - If the event has a DB-backed item_id, we keep your existing parent/child
        dedupe logic based on item_id + related ids.
        - If the event is content-only (no item_id), we now dedupe using *all* known ids
        (tmdb/tvdb/imdb) against both queued and running events with a single-pass check.

        Returns:
            True if queued; False if deduped away.
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
            # Content-only
            ci: Optional[MediaItem] = getattr(event, "content_item", None)
            if ci is None:
                logger.debug("Event has neither item_id nor content_item; skipping.")
                return False

            # Single-pass checks: queued and running
            if self.item_exists_in_queue(ci, self._queued_events) or self.item_exists_in_queue(ci, self._running_events):
                logger.debug(f"Content Item with {ci.log_string} is already queued or running, skipping.")
                return False

        self.add_event_to_queue(event)
        return True

    def add_item(self, item, service: str = "Manual") -> bool:
        """
        Adds an item to the queue as an event.

        Args:
            item (MediaItem): The item to add to the queue as an event.
        """
        if not db_functions.item_exists_by_any_id(item.id, item.tvdb_id, item.tmdb_id, item.imdb_id):
            if self.add_event(Event(service, content_item=item)):
                logger.debug(f"Added item with {item.log_string} to the queue.")
                return True
        return False

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
            table = updates.get(event.emitted_by.__name__, None)
            if table is not None:
                table.append(event.item_id)

        return updates

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
        item_id: Optional[str] = getattr(item, "id", None)
        tmdb_id: Optional[str] = getattr(item, "tmdb_id", None)
        tvdb_id: Optional[str] = getattr(item, "tvdb_id", None)
        imdb_id: Optional[str] = getattr(item, "imdb_id", None)

        if not (item_id or tmdb_id or tvdb_id or imdb_id):
            return False

        for ev in queue:
            if item_id is not None and getattr(ev, "item_id", None) == item_id:
                return True

            ci = getattr(ev, "content_item", None)
            if ci is None:
                continue

            if tmdb_id is not None and getattr(ci, "tmdb_id", None) == tmdb_id:
                return True
            if tvdb_id is not None and getattr(ci, "tvdb_id", None) == tvdb_id:
                return True
            if imdb_id is not None and getattr(ci, "imdb_id", None) == imdb_id:
                return True

        return False