from contextlib import contextmanager
from dataclasses import dataclass
from enum import Enum
import json
import traceback
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import TYPE_CHECKING
from kink import di
import trio

import sqlalchemy.orm
from loguru import logger
from pydantic import BaseModel

from program.db import db_functions
from program.db.db import db_session
from program.managers.sse_manager import sse_manager
from program.media.item import MediaItem
from program.types import Event
from program.utils.nursery import Nursery
from program.core.runner import Runner

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


class EventType(Enum):
    Completed = 0
    PartiallyCompleted = 1
    Symlinked = 2
    Downloaded = 3
    Scraped = 4


@dataclass
class Task:
    event: Event
    cancel_scope: trio.CancelScope


class EventManager:
    """
    Manages the execution of services and the handling of events.
    """

    def __init__(self):
        self._executors = list[ServiceExecutor]()
        self.tasks = dict[int, Task]()
        self.send_channel, self.receive_channel = trio.open_memory_channel[Event](
            max_buffer_size=float("inf")
        )
        self._queued_events = set[Event]()
        self._running_events = set[Event]()
        self.mutex = trio.Lock()

    async def _process_future(
        self,
        event: Event | None,
        result: int | tuple[int, datetime],
        service: Runner,
    ):
        """
        Processes the result of a future once it is completed.

        Args:
            future (concurrent.futures.Future): The future to process.
            service (type): The service class associated with the future.
        """

        item_id = None

        try:
            if isinstance(result, tuple):
                item_id, timestamp = result
            else:
                item_id, timestamp = result, datetime.now()

            sse_manager.publish_event(
                "event_update", json.dumps(self.get_event_updates())
            )

            if item_id:
                await self.add_event(
                    Event(
                        emitted_by=service,
                        item_id=item_id,
                        run_at=timestamp,
                    )
                )
        except Exception as e:
            logger.error(f"Error in future for item {item_id}: {e}")
            logger.exception(traceback.format_exc())

            # TODO(spoked): Here we should remove it from the running events so it can be retried, right?
            # self.remove_event_from_queue(future.event)

        log_message = f"Service {service.__class__.__name__} executed"

        if event:
            log_message += f" with {event.log_message}"

        logger.debug(log_message)

    async def add_event_to_queue(self, event: Event, log_message: bool = True):
        """
        Adds an event to the queue.

        Args:
            event (Event): The event to add to the queue.
        """

        async with self.mutex:
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
                        if item.is_parent_blocked():
                            logger.debug(
                                f"Not queuing {item.log_string}: Item is {item.last_state}"
                            )
                            return

                        # Cache the item state in the event for efficient priority sorting
                        if item.last_state:
                            event.item_state = item.last_state

            self._queued_events.add(event)

            await self.send_channel.send(event)

            if log_message:
                logger.debug(f"Added {event.log_message} to the queue.")

    async def remove_event_from_queue(self, event: Event):
        """
        Removes an event from the queue.

        Args:
            event (Event): The event to remove from the queue.
        """

        async with self.mutex:
            # self.queued_events.remove(event)

            logger.debug(f"Removed {event.log_message} from the queue.")

    async def remove_event_from_running(self, event: Event):
        """
        Removes an event from the running events.

        Args:
            event (Event): The event to remove from the running events.
        """

        async with self.mutex:
            if event in self._running_events:
                self._running_events.remove(event)
                logger.debug(f"Removed {event.log_message} from running events.")

    async def remove_id_from_queue(self, item_id: int):
        """
        Removes an item from the queue.

        Args:
            item (MediaItem): The event item to remove from the queue.
        """

        pass

        # for event in self.queued_events:
        #     if event.item_id == item_id:
        #         await self.remove_event_from_queue(event)

    async def add_event_to_running(self, event: Event):
        """
        Adds an event to the running events.

        Args:
            event (Event): The event to add to the running events.
        """

        async with self.mutex:
            self._running_events.add(event)
            logger.debug(f"Added {event.log_message} to running events.")

    async def remove_id_from_running(self, item_id: int):
        """
        Removes an item from the running events.

        Args:
            item (MediaItem): The event item to remove from the running events.
        """

        for event in self._running_events:
            if event.item_id == item_id:
                await self.remove_event_from_running(event)

    async def remove_id_from_queues(self, item_id: int):
        """
        Removes an item from both the queue and the running events.

        Args:
            item_id: The event item to remove from both the queue and the running events.
        """

        await self.remove_id_from_queue(item_id)
        await self.remove_id_from_running(item_id)

    async def submit_job(
        self,
        service: Runner,
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

        log_message = f"Submitting service {service.__class__.__name__} to be executed"

        # Content services dont provide an event.
        if event:
            log_message += f" with {event.log_message}"

        logger.debug(log_message)

        assert program.services

        @contextmanager
        def task_context(scope: trio.CancelScope):
            task_key = None

            try:
                if event:
                    task = Task(event=event, cancel_scope=scope)

                    if task_key := event.content_item and event.content_item.id:
                        self.tasks[task_key] = task
                    elif task_key := event.item_id:
                        self.tasks[task_key] = task

                yield
            finally:
                if task_key:
                    del self.tasks[task_key]

        async def run_task(event: Event | None, service: Runner):
            with trio.CancelScope() as scope:
                with task_context(scope):
                    try:
                        result = await db_functions.run_thread_with_db_item(
                            fn=service.run,
                            service=service,
                            program=program,
                            event=event,
                        )

                        if not result:
                            logger.warning(f"No result found")

                            return

                        await self._process_future(
                            event=event,
                            result=result,
                            service=service,
                        )
                    except Exception as e:
                        logger.exception(
                            f"Error executing service {service.__class__.__name__}: {e}"
                        )
                        return

            if scope.cancelled_caught:
                if event:
                    logger.debug(f"Task {event.item_id} was cancelled.")
                else:
                    logger.debug(f"Task was cancelled")

        di[Nursery].nursery.start_soon(
            run_task,
            event,
            service,
        )

        sse_manager.publish_event(
            "event_update",
            json.dumps(self.get_event_updates()),
        )

    async def cancel_job(self, item_id: int, suppress_logs: bool = False):
        """
        Cancels a job associated with the given item.

        Args:
            item_id (int): The event item whose job needs to be canceled.
            suppress_logs (bool): If True, suppresses debug logging for this operation.
        """

        with db_session() as session:
            item_id, related_ids = db_functions.get_item_ids(session, item_id)
            ids_to_cancel = set([item_id] + related_ids)

            for id in ids_to_cancel:
                if id in self.tasks:
                    task = self.tasks[id]

                    await self.remove_id_from_queues(id)

                    if not task.cancel_scope.cancel_called:
                        try:
                            task.cancel_scope.cancel()

                            logger.debug(f"Canceled job for Item ID {id}")
                        except Exception as e:
                            if not suppress_logs:
                                logger.error(
                                    f"Error cancelling future for {id}: {str(e)}"
                                )

                await self.remove_id_from_queues(id)

    def _id_in_queue(self, id: int) -> bool:
        """
        Checks if an item with the given ID is in the queue.

        Args:
            id (int): The ID of the item to check.

        Returns:
            bool: True if the item is in the queue, False otherwise.
        """

        return any(event.item_id == id for event in self._queued_events)

    def _id_in_running_events(self, id: int) -> bool:
        """
        Checks if an item with the given ID is in the running events.

        Args:
            id (int): The ID of the item to check.

        Returns:
            bool: True if the item is in the running events, False otherwise.
        """

        return any(event.item_id == id for event in self._running_events)

    async def add_event(self, event: Event) -> bool:
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
                logger.debug(f"Item ID {item_id} is already in the queue, skipping.")
                return False

            if self._id_in_running_events(item_id):
                logger.debug(f"Item ID {item_id} is already running, skipping.")
                return False

            for related_id in related_ids:
                if self._id_in_queue(related_id) or self._id_in_running_events(
                    related_id
                ):
                    logger.debug(
                        f"Child of Item ID {item_id} is already in the queue or running, skipping."
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
                logger.debug(
                    f"Content Item with {content_item.log_string} is already queued or running, skipping."
                )

                return False

        await self.add_event_to_queue(event)

        return True

    async def add_item(
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
            if await self.add_event(
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

        events = [task.event for task in self.tasks.values() if task.event]
        event_types = [
            "Scraping",
            "Downloader",
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

    def item_exists_in_queue(self, item: MediaItem, queue: set[Event]) -> bool:
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
