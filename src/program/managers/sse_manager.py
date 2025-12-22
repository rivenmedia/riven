import asyncio
from typing import Any


class ServerSentEventManager:
    def __init__(self):
        # Store active subscriber queues by event type
        self.subscribers = dict[str, list[asyncio.Queue[Any]]]()
        self._loop: asyncio.AbstractEventLoop | None = None

    def _dispatch(self, event_type: str, data: Any):
        """Internal method to dispatch events on the event loop."""
        if not data:
            return

        # Only send to active subscribers
        if event_type not in self.subscribers:
            return

        # Send to all active subscribers for this event type
        dead_queues = list[asyncio.Queue[Any]]()

        for queue in self.subscribers[event_type]:
            try:
                queue.put_nowait(data)
            except asyncio.QueueFull:
                # Queue is full, mark for removal
                dead_queues.append(queue)

        # Clean up dead queues
        for dead_queue in dead_queues:
            if dead_queue in self.subscribers[event_type]:
                self.subscribers[event_type].remove(dead_queue)

    def publish_event(self, event_type: str, data: Any):
        """
        Publish an event to all active subscribers.
        Thread-safe: schedules the dispatch on the event loop if called from a thread.
        """
        if self._loop is None:
            return

        try:
            # If we're already in the loop, execute directly
            if asyncio.get_running_loop() == self._loop:
                self._dispatch(event_type, data)
                return
        except RuntimeError:
            # Not in a loop (e.g. called from a thread)
            pass

        # Schedule execution on the event loop
        self._loop.call_soon_threadsafe(self._dispatch, event_type, data)

    async def subscribe(self, event_type: str):
        """
        Subscribe to an event type.
        Creates a new queue for this subscriber and yields events as they arrive.
        """
        # Capture the running loop
        if self._loop is None:
            self._loop = asyncio.get_running_loop()

        # Create a queue for this subscriber
        queue = asyncio.Queue[Any](maxsize=100)

        # Register this subscriber
        if event_type not in self.subscribers:
            self.subscribers[event_type] = []

        self.subscribers[event_type].append(queue)

        try:
            while True:
                try:
                    # Wait for events with a timeout to send keepalive
                    data = await asyncio.wait_for(queue.get(), timeout=30.0)
                    yield f"data: {data}\n\n"
                except asyncio.TimeoutError:
                    # Send keepalive comment to prevent connection timeout
                    yield ": keepalive\n\n"
        finally:
            # Clean up when subscriber disconnects
            if event_type in self.subscribers and queue in self.subscribers[event_type]:
                self.subscribers[event_type].remove(queue)

                # Remove event type if no more subscribers
                if not self.subscribers[event_type]:
                    del self.subscribers[event_type]


sse_manager = ServerSentEventManager()
