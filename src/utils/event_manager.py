import asyncio
import concurrent.futures
from queue import Empty
import os
from threading import Lock
import time
import traceback
from subliminal import Episode, Movie
from program.db.db_functions import _run_thread_with_db_item
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
            self._futures.remove(future)
            item = next(future.result(), None)
            if item:
                self.remove_item_from_running(item)
                self.add_event(Event(emitted_by=service, item=item))
        except Exception as e:
            logger.error(f"Error in future for {future}: {e}")
            logger.exception(traceback.format_exc())
        log_message = f"Service {service.__name__} executed"
        if hasattr(future, "item"):
            log_message += f" with item: {future.item.log_string}"
        logger.debug(log_message)

    def add_event_to_queue(self, event):
        """
        Adds an event to the queue.

        Args:
            event (Event): The event to add to the queue.
        """
        with self.mutex:
            self._queued_events.append(event)
            ws_manager.send_event_update(self._running_events, self._queued_events)
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
                    ws_manager.send_event_update(self._running_events, self._queued_events)
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
            ws_manager.send_event_update(self._running_events, self._queued_events)
            logger.debug(f"Added {event.item.log_string} to the running events.")

    def remove_item_from_running(self, item):
        """
        Removes an item from the running events.

        Args:
            item (MediaItem): The event item to remove from the running events.
        """
        with self.mutex:
            for event in self._running_events:
                if event.item.imdb_id == item.imdb_id:
                    self._running_events.remove(event)
                    ws_manager.send_event_update(self._running_events, self._queued_events)
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

    def submit_job(self, service, program, item=None):
        """
        Submits a job to be executed by the service.

        Args:
            service (type): The service class to execute.
            program (Program): The program containing the service.
            item (Event, optional): The event item to process. Defaults to None.
        """
        log_message = f"Submitting service {service.__name__} to be executed"
        if item:
            log_message += f" with item: {item.log_string}"
        logger.debug(log_message)
        
        executor = self._find_or_create_executor(service)
        future = executor.submit(_run_thread_with_db_item, program.all_services[service].run, service, program, item)
        if item:
            future.item = item
        self._futures.append(future)
        future.add_done_callback(lambda f:self._process_future(f, service))

    def cancel_job(self, item):
        """
        Cancels a job associated with the given item.

        Args:
            item (MediaItem): The event item whose job needs to be canceled.
        """
        future = next((future for future in self._futures if hasattr(future, 'item') and future.item == item), None)
        if future and not future.done() and not future.cancelled():
            self.remove_item_from_queues(item)
            future.cancel()
            if future.cancelled():

                logger.debug(f"Cancelled future for {item.log_string}.")
            else:
                logger.debug(f"Could not cancel future for {item.log_string}.")
    
    def next(self, timeout=None):
        """
        Get the next event in the queue with an optional timeout.

        Args:
            timeout (float, optional): The maximum time to wait for an event. Defaults to None.

        Raises:
            Empty: If the queue is empty after the timeout period.

        Returns:
            Event: The next event in the queue.
        """
        start_time = time.time()
        while True:
            if self._queued_events:
                event = self._queued_events.pop(0)
                ws_manager.send_event_update(self._running_events, self._queued_events)
                return event
            if timeout is not None and (time.time() - start_time) >= timeout:
                raise Empty
            time.sleep(0.01)

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
    
    def add_event(self, event):
        """
        Adds an event to the queue if it is not already present in the queue or running events.

        Args:
            event (Event): The event to add to the queue.

        Returns:
            bool: True if the event was added to the queue, False if it was already present.
        """
        # Check if the event's item is already in the queue
        if any(event.item.imdb_id and qi.item.imdb_id == event.item.imdb_id for qi in self._queued_events):
            logger.debug(f"Item {event.item.log_string} is already in the queue, skipping.")
            return False
        # Check if the event's item is already running
        elif any(event.item.imdb_id and ri.item.imdb_id == event.item.imdb_id for ri in self._running_events):
            logger.debug(f"Item {event.item.log_string} is already running, skipping.")
            return False
        # Check if the event's item is a show and its seasons or episodes are in the queue or running
        elif event.item.type == "show":
            for s in event.item.seasons:
                if self._id_in_queue(s._id) or self._id_in_running_events(s._id):
                    logger.debug(f"A season for {event.item.log_string} is already in the queue or running, skipping.")
                    return False
                for e in s.episodes:
                    if self._id_in_queue(e._id) or self._id_in_running_events(e._id):
                        logger.debug(f"An episode {event.item.log_string} is already in the queue or running, skipping.")
                        return False
        # Check if the event's item is a season and its episodes are in the queue or running
        elif event.item.type == "season":
            for e in event.item.episodes:
                if self._id_in_queue(e._id) or self._id_in_running_events(e._id):
                    logger.debug(f"An episode {event.item.log_string} is already in the queue or running, skipping.")
                    return False
        # Check if the event's item's parent or parent's parent is in the queue or running
        elif hasattr(event.item, "parent"):
            parent = event.item.parent
            if self._id_in_queue(parent._id) or self._id_in_running_events(parent._id):
                logger.debug(f"Parent {parent.log_string} is already in the queue or running, skipping.")
                return False
            elif hasattr(parent, "parent") and (self._id_in_queue(parent.parent._id) or self._id_in_running_events(parent.parent._id)):
                logger.debug(f"Parent's parent {parent.parent.log_string} is already in the queue or running, skipping.")
                return False

        # Log the addition of the event to the queue
        if not isinstance(event.item, (Show, Movie, Episode, Season)):
            logger.debug(f"Added {event.item.log_string} to the queue")
        else:
            logger.debug(f"Re-added {event.item.log_string} to the queue")
        self.add_event_to_queue(event)
        return True
    
    def add_item(self, item):
        """
        Adds an item to the queue as an event.

        Args:
            item (MediaItem): The item to add to the queue as an event.
        """
        self.add_event(Event("Manual", item))