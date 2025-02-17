import os
import threading
import traceback
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
        self._canceled_futures: list[Future] = []
        self._content_queue: list[Event] = []
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
        env_var_name = f"{service_name.upper()}_MAX_WORKERS"
        max_workers = int(os.environ.get(env_var_name, 1))
        for executor in self._executors:
            if executor["_name_prefix"] == service_name:
                logger.debug(f"Executor for {service_name} found.")
                return executor["_executor"]
        _executor = ThreadPoolExecutor(thread_name_prefix=service_name, max_workers=max_workers)
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

        if future.cancelled():
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

            self._queued_events.append(event)
            if log_message:
                logger.debug(f"Added {event.log_message} to the queue.")

    def remove_event_from_queue(self, event: Event):
        with self.mutex:
            self._queued_events.remove(event)
            logger.debug(f"Removed {event.log_message} from the queue.")

    def remove_event_from_running(self, event: Event):
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

    # For debugging purposes we can monitor the execution time of the service. (comment out above and uncomment below)
    # def submit_job(self, service, program, event=None):
    #     """
    #     Submits a job to be executed by the service.

    #     Args:
    #         service (type): The service class to execute.
    #         program (Program): The program containing the service.
    #         item (Event, optional): The event item to process. Defaults to None.
    #     """
    #     log_message = f"Submitting service {service.__name__} to be executed"
    #     if event:
    #         log_message += f" with {event.log_message}"
    #     logger.debug(log_message)

    #     cancellation_event = threading.Event()
    #     executor = self._find_or_create_executor(service)
        
    #     # Add start time to track execution duration
    #     start_time = datetime.now()
        
    #     def _monitor_execution(future):
    #         """Monitor execution time and log if taking too long"""
    #         while not future.done():
    #             execution_time = (datetime.now() - start_time).total_seconds()
    #             if execution_time > 180:  # 3 minutes
    #                 current_thread = None
    #                 for thread in threading.enumerate():
    #                     if thread.name.startswith(service.__name__) and not thread.name.endswith('_monitor'):
    #                         current_thread = thread
    #                         break
                            
    #                 if current_thread:
    #                     # Get stack frames for the worker thread
    #                     frames = sys._current_frames()
    #                     thread_frame = None
    #                     for thread_id, frame in frames.items():
    #                         if thread_id == current_thread.ident:
    #                             thread_frame = frame
    #                             break
                        
    #                     if thread_frame:
    #                         stack_trace = ''.join(traceback.format_stack(thread_frame))
    #                     else:
    #                         stack_trace = "Could not get stack trace for worker thread"
    #                 else:
    #                     stack_trace = "Could not find worker thread"
                    
    #                 logger.warning(
    #                     f"Service {service.__name__} execution taking longer than 3 minutes!\n"
    #                     f"Event: {event.log_message if event else 'No event'}\n"
    #                     f"Execution time: {execution_time:.1f} seconds\n"
    #                     f"Thread name: {current_thread.name if current_thread else 'Unknown'}\n"
    #                     f"Thread alive: {current_thread.is_alive() if current_thread else 'Unknown'}\n"
    #                     f"Stack trace:\n{stack_trace}"
    #                 )
                    
    #                 # Cancel the future and kill the thread
    #                 future.cancellation_event.set()
    #                 future.cancel()
    #                 if current_thread:
    #                     logger.warning(f"Killing thread {current_thread.name} due to timeout")
    #                     self._futures.remove(future)
    #                     if event:
    #                         self.remove_event_from_running(event)
    #                 return  # Exit the monitoring thread
                    
    #             time.sleep(60)  # Check every minute

    #     future = executor.submit(db_functions.run_thread_with_db_item, 
    #                         program.all_services[service].run, 
    #                         service, program, event, cancellation_event)
        
    #     # Start monitoring thread
    #     monitor_thread = threading.Thread(
    #         target=_monitor_execution, 
    #         args=(future,),
    #         name=f"{service.__name__}_monitor",
    #         daemon=True
    #     )
    #     monitor_thread.start()
        
    #     future.cancellation_event = cancellation_event
    #     if event:
    #         future.event = event
    #     self._futures.append(future)
    #     sse_manager.publish("event_update", self.get_event_updates())
    #     future.add_done_callback(lambda f: self._process_future(f, service))

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

            for future in self._futures:
                future_item_id = None
                future_related_ids = []

                if hasattr(future, "event") and hasattr(future.event, "item_id"):
                    future_item = future.event.item_id
                    future_item_id, future_related_ids = db_functions.get_item_ids(session, future_item)

                if future_item_id in ids_to_cancel or any(rid in ids_to_cancel for rid in future_related_ids):
                    self.remove_id_from_queues(future_item)
                    if not future.done() and not future.cancelled():
                        try:
                            future.cancellation_event.set()
                            future.cancel()
                            self._canceled_futures.append(future)
                        except Exception as e:
                            if not suppress_logs:
                                logger.error(f"Error cancelling future for {future_item.log_string}: {str(e)}")


        logger.debug(f"Canceled jobs for Item ID {item_id} and its children.")

    def next(self) -> Event:
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
            if any(event.content_item and event.content_item.imdb_id == imdb_id for event in self._queued_events):
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
            table = updates.get(event.emitted_by.__name__, None)
            if table is not None:
                table.append(event.item_id)

        return updates