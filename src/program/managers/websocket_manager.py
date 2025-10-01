import asyncio
from datetime import datetime
from typing import Any, Dict, List

from fastapi import WebSocket, WebSocketDisconnect


class ConnectionManager:
    def __init__(self):
        # Store active connections by topic
        self.active_connections: Dict[str, List[WebSocket]] = {}
        # Message queue for each topic
        self.message_queues: Dict[str, asyncio.Queue] = {}
        # Background tasks
        self.background_tasks: List[asyncio.Task] = []

    async def connect(self, websocket: WebSocket, topic: str):
        await websocket.accept()
        if topic not in self.active_connections:
            self.active_connections[topic] = []
        self.active_connections[topic].append(websocket)
        
        if topic not in self.message_queues:
            self.message_queues[topic] = asyncio.Queue()
            # Start broadcast task for this topic
            task = asyncio.create_task(self._broadcast_messages(topic))
            self.background_tasks.append(task)

    async def disconnect(self, websocket: WebSocket, topic: str):
        if topic in self.active_connections:
            if websocket in self.active_connections[topic]:
                self.active_connections[topic].remove(websocket)
            
            # Clean up if no more connections for this topic
            if not self.active_connections[topic]:
                del self.active_connections[topic]
                # Cancel broadcast task for this topic
                for task in self.background_tasks:
                    if task.get_name() == f"broadcast_{topic}":
                        task.cancel()
                        self.background_tasks.remove(task)
                        break

    def publish(self, topic: str, message: Any):
        """Publish a message to a specific topic"""
        if topic not in self.message_queues:
            return # There are no connections for this topic
            #self.message_queues[topic] = asyncio.Queue()
        
        # Format the message with timestamp
        formatted_message = {
            "timestamp": datetime.utcnow().isoformat(),
            "data": message
        }
        
        try:
            self.message_queues[topic].put_nowait(formatted_message)
        except asyncio.QueueFull:
            print(f"Message queue full for topic {topic}")

    async def _broadcast_messages(self, topic: str):
        """Background task to broadcast messages for a specific topic"""
        try:
            while True:
                if topic in self.message_queues:
                    message = await self.message_queues[topic].get()
                    
                    if topic in self.active_connections:
                        dead_connections = []
                        for connection in self.active_connections[topic]:
                            try:
                                await connection.send_json(message)
                            except WebSocketDisconnect:
                                dead_connections.append(connection)
                            except Exception as e:
                                print(f"Error sending message: {e}")
                                dead_connections.append(connection)
                        
                        # Clean up dead connections
                        for dead in dead_connections:
                            await self.disconnect(dead, topic)
        except asyncio.CancelledError:
            # Handle task cancellation
            pass
        except Exception as e:
            print(f"Broadcast task error for topic {topic}: {e}")

# Create a global instance
manager = ConnectionManager()