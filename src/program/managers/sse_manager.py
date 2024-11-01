import asyncio
from typing import Any, Dict


class ServerSentEventManager:
    def __init__(self):
        self.event_queues: Dict[str, asyncio.Queue] = {}

    def publish_event(self, event_type: str, data: Any):
        if not data:
            return
        if event_type not in self.event_queues:
            self.event_queues[event_type] = asyncio.Queue()
        self.event_queues[event_type].put_nowait(data)

    async def subscribe(self, event_type: str):
        if event_type not in self.event_queues:
            self.event_queues[event_type] = asyncio.Queue()

        while True:
            try:
                data = await asyncio.wait_for(self.event_queues[event_type].get(), timeout=1.0)
                yield f"{data}\n"
            except asyncio.TimeoutError:
                pass

sse_manager = ServerSentEventManager()