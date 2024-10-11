import concurrent.futures
import os
import traceback
from datetime import datetime
from queue import Empty
from threading import Lock

from loguru import logger
from sqlalchemy import select
from pydantic import BaseModel
from sqlalchemy.orm.exc import StaleDataError
from concurrent.futures import CancelledError

from utils.memory_limiter import check_memory_limit, wait_for_memory
import utils.websockets.manager as ws_manager
from program.db.db import db
from program.db.db_functions import _get_item_ids, _run_thread_with_db_item
from program.media.item import MediaItem, Season, Show
from program.types import Event

class EventUpdate(BaseModel):
    item_id: int
    imdb_id: str
    title: str
    type: str
    emitted_by: str
    run_at: str
    last_state: str

class EventManager:
    """
    Manages the execution of services and the handling of events.
    """
    def __init__(self):
        self._executors: list[concurrent.futures.ThreadPoolExecutor] = []
        self._futures = []
        self._queued_events = []
        self._running_events = []
        self._remove_id_queue = []
        self.mutex = Lock()

    def _find_or_create_executor(self, service_cls) -> concurrent.futures.ThreadPoolExecutor:
        """
        Finds or creates a ThreadPoolExecutor for the given service class.

        Args:
            service_cls (type): The service class for which to find or create an executor.

        Returns:
            concurrent.futures.ThreadPoolExecutor: The executor for the service class.
        """
        service_name = service_cls.__name__
        env_var_name = f"{service_name.upper()}_MAX_WORKERS"
        max_workers = int(os.environ.get(env_var_name, 1))
        for executor in self._executors:
            if executor["_name_prefix"] == service_name:
                logger.debug(f"Executor for {service_name} found.")
                return executor["_executor"]
        else:
            _executor = concurrent.futures.ThreadPoolExecutor(thread_name_prefix=service_name, max_workers=max_workers)
            self._executors.append({ "_name_prefix": service_name, "_executor": _executor })
            logger.debug(f"Created executor for {service_name} with {max_workers} max workers.")
            return _executor

    def _process_future(self, future, service):
        """
        Processes the result of a future once it is completed.

        Args:
            future (concurrent.futures.Future): The future to process.
            service (type): The service class associated with the future.
        """
        try:
            result = next(future.result(), None)
            if future in self._futures:
                self._futures.remove(future)
            ws_manager.send_event_update([future.event for future in self._futures if hasattr(future, "event")])
            if isinstance(result, tuple):
                item, timestamp = result
            else:
                item, timestamp = result, datetime.now()
            if item:
                self.remove_item_from_running(item)
                if item._id in self._remove_id_queue:
                    # Item was removed while running
                    logger.debug(f"Item {item.log_string} is in the removed queue, discarding result.")
                    self._remove_id_queue.remove(item._id)
                    self.remove_item_from_queue(item)
                    return
                self.add_event(Event(emitted_by=service, item=item, run_at=timestamp))
        except RuntimeError as e:
            if "cannot schedule new futures after" in str(e):
                exit(0)
            logger.error(f"Runtime error in future for {future}: {e}")
            logger.exception(traceback.format_exc())
        except (StaleDataError, CancelledError):
            # Expected behavior when cancelling tasks or when the item was removed
            return
        except Exception as e:
            logger.error(f"Error in future for {future}: {e}")
            logger.exception(traceback.format_exc())
        log_message = f"Service {service.__name__} executed"
        if hasattr(future, "event") and hasattr(future.event, "item"):
            log_message += f" with item: {future.event.item.log_string}"
        logger.debug(log_message)

    def add_event_to_queue(self, event):
        """
        Adds an event to the queue.

        Args:
            event (Event): The event to add to the queue.
        """
        with self.mutex:
            self._queued_events.append(event)
            logger.debug(f"Added {event.item.log_string} to the queue.")

    def remove_item_from_queue(self, item):
        """
        Removes an item from the queue.

        Args:
            item (MediaItem): The event item to remove from the queue.
        """
        with self.mutex:
            for event in self._queued_events:
                if event.item.imdb_id == item.imdb_id:
                    self._queued_events.remove(event)
                    logger.debug(f"Removed {item.log_string} from the queue.")
                    return

    def add_event_to_running(self, event):
        """
        Adds an event to the running events.

        Args:
            event (Event): The event to add to the running events.
        """
        with self.mutex:
            self._running_events.append(event)
        logger.debug(f"Added {event.item.log_string} to the running events.")

    def remove_item_from_running(self, item):
        """
        Removes an item from the running events.

        Args:
            item (MediaItem): The event item to remove from the running events.
        """
        with self.mutex:
            for event in self._running_events:
                if event.item._id == item._id or (event.item.type == "mediaitem" and event.item.imdb_id == item.imdb_id):
                    self._running_events.remove(event)
                    logger.debug(f"Removed {item.log_string} from the running events.")
                    return

    def remove_item_from_queues(self, item):
        """
        Removes an item from both the queue and the running events.

        Args:
            item (MediaItem): The event item to remove from both the queue and the running events.
        """
        self.remove_item_from_queue(item)
        self.remove_item_from_running(item)

    def submit_job(self, service, program, event=None):
        """
        Submits a job to be executed by the service.

        Args:
            service (type): The service class to execute.
            program (Program): The program containing the service.
            item (Event, optional): The event item to process. Defaults to None.
        """
        if not check_memory_limit():
            logger.warning("Memory usage exceeded limit. Job not submitted.")
            return
        
        log_message = f"Submitting service {service.__name__} to be executed"
        item = None
        if event and event.item:
            item = event.item
            log_message += f" with item: {event.item.log_string}"
        logger.debug(log_message)

        executor = self._find_or_create_executor(service)
        future = executor.submit(_run_thread_with_db_item, program.all_services[service].run, service, program, item)
        if event:
            future.event = event
        self._futures.append(future)
        ws_manager.send_event_update([future.event for future in self._futures if hasattr(future, "event")])
        future.add_done_callback(lambda f:self._process_future(f, service))

    def cancel_job(self, item, suppress_logs=False):
        """
        Cancels a job associated with the given item.

        Args:
            item (MediaItem): The event item whose job needs to be canceled.
            suppress_logs (bool): If True, suppresses debug logging for this operation.
        """
        with db.Session() as session:
            item_id, related_ids = _get_item_ids(session, item)
            ids_to_cancel = set([item_id] + related_ids)

            futures_to_remove = []
            for future in self._futures:
                future_item_id = None
                future_related_ids = []
                
                if hasattr(future, 'event') and hasattr(future.event, 'item'):
                    future_item = future.event.item
                    future_item_id, future_related_ids = _get_item_ids(session, future_item)

                if future_item_id in ids_to_cancel or any(rid in ids_to_cancel for rid in future_related_ids):
                    self.remove_item_from_queues(future_item)
                    futures_to_remove.append(future)
                    if not future.done() and not future.cancelled():
                        try:
                            future.cancel()
                        except Exception as e:
                            if not suppress_logs:
                                logger.error(f"Error cancelling future for {future_item.log_string}: {str(e)}")

            for future in futures_to_remove:
                self._futures.remove(future)

        # Clear from queued and running events
        with self.mutex:
            self._remove_id_queue.append(item._id)
            self._queued_events = [event for event in self._queued_events if event.item._id != item._id and event.item.imdb_id != item.imdb_id]
            self._running_events = [event for event in self._running_events if event.item._id != item._id and event.item.imdb_id != item.imdb_id]
            self._futures = [future for future in self._futures if not hasattr(future, 'event') or future.event.item._id != item._id and future.event.item.imdb_id != item.imdb_id]

        logger.debug(f"Canceled jobs for item {item.log_string} and its children.")

    def cancel_job_by_id(self, item_id, suppress_logs=False):
        """
        Cancels a job associated with the given media item ID.

        Args:
            item_id (int): The ID of the media item whose job needs to be canceled.
            suppress_logs (bool): If True, suppresses debug logging for this operation.
        """
        with db.Session() as session:
            # Fetch only the necessary fields
            item = session.execute(
                select(MediaItem).where(MediaItem._id == item_id)
            ).unique().scalar_one_or_none()
            
            if not item:
                if not suppress_logs:
                    logger.error(f"No item found with ID {item_id}")
                return

            # Use the existing cancel_job logic with just the ID
            self.cancel_job(item, suppress_logs)

    def next(self):
        """
        Get the next event in the queue with an optional timeout.

        Raises:
            Empty: If the queue is empty.

        Returns:
            Event: The next event in the queue.
        """
        while True:
            if self._queued_events:
                with self.mutex:
                    self._queued_events.sort(key=lambda event: event.run_at)
                    if datetime.now() >= self._queued_events[0].run_at:
                        event = self._queued_events.pop(0)
                        return event
            raise Empty

    def _id_in_queue(self, _id):
        """
        Checks if an item with the given ID is in the queue.

        Args:
            _id (str): The ID of the item to check.

        Returns:
            bool: True if the item is in the queue, False otherwise.
        """
        return any(event.item._id == _id for event in self._queued_events)

    def _id_in_running_events(self, _id):
        """
        Checks if an item with the given ID is in the running events.

        Args:
            _id (str): The ID of the item to check.

        Returns:
            bool: True if the item is in the running events, False otherwise.
        """
        return any(event.item._id == _id for event in self._running_events)

    def _imdb_id_in_queue(self, imdb_id):
        """
        Checks if an item with the given IMDb ID is in the queue.

        Args:
            imdb_id (str): The IMDb ID of the item to check.

        Returns:
            bool: True if the item is in the queue, False otherwise.
        """
        return any(event.item.imdb_id == imdb_id for event in self._queued_events)

    def _imdb_id_in_running_events(self, imdb_id):
        """
        Checks if an item with the given IMDb ID is in the running events.

        Args:
            imdb_id (str): The IMDb ID of the item to check.

        Returns:
            bool: True if the item is in the running events, False otherwise.
        """
        return any(event.item.imdb_id == imdb_id for event in self._running_events)

    def add_event(self, event):
        """
        Adds an event to the queue if it is not already present in the queue or running events.

        Args:
            event (Event): The event to add to the queue.

        Returns:
            bool: True if the event was added to the queue, False if it was already present.
        """
        if not check_memory_limit():
            logger.warning("Memory usage exceeded limit. Event not added.")
            return False

        # Check if the event's item is a show and its seasons or episodes are in the queue or running
        with db.Session() as session:
            item_id, related_ids = _get_item_ids(session, event.item)
        if item_id:
            if self._id_in_queue(item_id):
                logger.debug(f"Item {event.item.log_string} is already in the queue, skipping.")
                return False
            if self._id_in_running_events(item_id):
                logger.debug(f"Item {event.item.log_string} is already running, skipping.")
                return False
            for related_id in related_ids:
                if self._id_in_queue(related_id) or self._id_in_running_events(related_id):
                    logger.debug(f"Child of {event.item.log_string} is already in the queue or running, skipping.")
                    return False
        else:
            # Items that are not in the database
            if self._imdb_id_in_queue(event.item.imdb_id):
                logger.debug(f"Item {event.item.log_string} is already in the queue, skipping.")
                return False
            elif self._imdb_id_in_running_events(event.item.imdb_id):
                logger.debug(f"Item {event.item.log_string} is already running, skipping.")
                return False

        # Log the addition of the event to the queue
        if not event.item.type in ["show", "movie", "season", "episode"]:
            logger.debug(f"Added {event.item.log_string} to the queue")
        else:
            logger.debug(f"Re-added {event.item.log_string} to the queue")
        self.add_event_to_queue(event)
        return True

    def add_item(self, item, service="Manual"):
        """
        Adds an item to the queue as an event.

        Args:
            item (MediaItem): The item to add to the queue as an event.
        """
        self.add_event(Event(service, item))

    def get_event_updates(self) -> dict[str, list[EventUpdate]]:
        """
        Returns a formatted list of event updates.

        Returns:
            list: The list of formatted event updates.
        """
        events = [future.event for future in self._futures if hasattr(future, "event")]
        event_types = ["Scraping", "Downloader", "Symlinker", "Updater", "PostProcessing"]
        return {
            event_type.lower(): [
                EventUpdate.model_validate(
                {
                    "item_id": event.item._id,
                    "imdb_id": event.item.imdb_id,
                    "title": event.item.log_string,
                    "type": event.item.type,
                    "emitted_by": event.emitted_by if isinstance(event.emitted_by, str) else event.emitted_by.__name__,
                    "run_at": event.run_at.isoformat(),
                    "last_state": event.item.last_state.name if event.item.last_state else "N/A"
                })
                for event in events if event.emitted_by == event_type
            ]
            for event_type in event_types
        }