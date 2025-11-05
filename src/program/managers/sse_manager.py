import asyncio
from typing import Any, Dict, List


class ServerSentEventManager:
    def __init__(self):
        # Store active subscriber queues by event type
        self.subscribers: Dict[str, List[asyncio.Queue]] = {}

    def publish_event(self, event_type: str, data: Any):
        """
        Publish an event to all active subscribers.
        Events are sent only to currently connected clients and are not pooled.
        """
        if not data:
            return

        # Only send to active subscribers, don't create queue if none exist
        if event_type not in self.subscribers:
            return

        # Send to all active subscribers for this event type
        dead_queues = []
        for queue in self.subscribers[event_type]:
            try:
                queue.put_nowait(data)
            except asyncio.QueueFull:
                # Queue is full, mark for removal
                dead_queues.append(queue)

        # Clean up dead queues
        for dead_queue in dead_queues:
            self.subscribers[event_type].remove(dead_queue)

    async def subscribe(self, event_type: str):
        """
        Subscribe to an event type.
        Creates a new queue for this subscriber and yields events as they arrive.
        """
        # Create a queue for this subscriber
        queue = asyncio.Queue(maxsize=100)

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
