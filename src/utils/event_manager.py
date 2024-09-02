import asyncio
import concurrent.futures
from datetime import datetime
from queue import Empty
import os
from threading import Lock
import time
import traceback
from subliminal import Episode, Movie

from program.db.db import db
from program.db.db_functions import _run_thread_with_db_item, _get_item_ids
from loguru import logger
import utils.websockets.manager as ws_manager

from program.media.item import Season, Show
from program.types import Event
class EventManager:
    """
    Manages the execution of services and the handling of events.
    """
    def __init__(self):
        self._executors: list[concurrent.futures.ThreadPoolExecutor] = []
        self._futures = []
        self._queued_events = []
        self._running_events = []
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
            self._futures.remove(future)
            ws_manager.send_event_update([future.event for future in self._futures if hasattr(future, "event")])
            if isinstance(result, tuple):
                item, timestamp = result
            else:
                item, timestamp = result, datetime.now()
            if item:
                self.remove_item_from_running(item)
                self.add_event(Event(emitted_by=service, item=item, run_at=timestamp))
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
                if event.item._id == item._id or event.item.type == "mediaitem" and event.item.imdb_id == item.imdb_id:
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

    def cancel_job(self, item):
        """
        Cancels a job associated with the given item.

        Args:
            item (MediaItem): The event item whose job needs to be canceled.
        """
        with db.Session() as session:
            for future in self._futures:
                future_item = future.event.item if hasattr(future.event, 'item') else None
                item_id, related_ids = _get_item_ids(session, future_item)
                if item_id in [item._id] + related_ids:
                    self.remove_item_from_queues(item)
                    self._futures.remove(future)
                    if not future.done() or not future.cancelled():
                        future.cancel()
        #     future = next(future for future in self._futures if hasattr(future.event, 'item') and future.event.item._id == item_id, None)
        # future: concurrent.futures.Future = next((future for future in self._futures if hasattr(future.event, 'item') and future.event.item == item), None)
        # if future:
        #     self.remove_item_from_queues(item)
        #     self._futures.remove(future)
        #     future = None
        #     if not future.done() or not future.cancelled():
        #         future.cancel()

    def next(self):
        """
        Get the next event in the queue with an optional timeout.

        Raises:
            Empty: If the queue is empty.

        Returns:
            Event: The next event in the queue.
        """
        start_time = time.time()
        while True:
            if self._queued_events:
                with self.mutex:
                    self._queued_events.sort(key=lambda event: event.run_at, reverse=True)
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
        if not isinstance(event.item, (Show, Movie, Episode, Season)):
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