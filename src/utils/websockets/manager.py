import asyncio
import json
from fastapi import WebSocket
from loguru import logger


active_connections = []

async def connect(websocket: WebSocket):
    await websocket.accept()
    existing_connection = next((connection for connection in active_connections if connection.app == websocket.app), None)
    if not existing_connection:
        logger.debug("Frontend connected!")
        active_connections.append(websocket)
    if websocket.app.program.initialized:
        status = "running"
    else:
        status = "paused"
    await websocket.send_json({"type": "health", "status": status})

def disconnect(websocket: WebSocket):
    logger.debug("Frontend disconnected!")
    existing_connection = next((connection for connection in active_connections if connection.app == websocket.app), None)
    active_connections.remove(existing_connection)
    
async def _send_json(message: json, websocket: WebSocket):
    await websocket.send_json(message)

def send_event_update(running, queued):
    message = {"running": [{"emitted_by":event.emitted_by, "item":event.item._id} for event in running], "queued": [{"emitted_by":event.emitted_by, "item":event.item._id} for event in queued]}
    broadcast({"type": "event_update", "message": message})

def send_health_update(status: str):
    broadcast({"type": "health", "status": status})

def send_log_message(message: str):
    broadcast({"type": "log", "message": message})

def send_item_update(item: json):
    broadcast({"type": "item_update", "item": item})

def broadcast(message: json):
    for connection in active_connections:
        event_loop = None
        try:
            event_loop = asyncio.get_event_loop()
        except RuntimeError:
            pass
        try:
            if event_loop and event_loop.is_running():
                asyncio.create_task(_send_json(message, connection))
            else:
                asyncio.run(_send_json(message, connection))
        except Exception:
            pass
