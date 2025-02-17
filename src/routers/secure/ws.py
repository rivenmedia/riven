from fastapi import WebSocket, WebSocketDisconnect, APIRouter
import logging
from datetime import datetime
from program.managers.websocket_manager import manager
import json
from loguru import logger

class WebSocketLogHandler(logging.Handler):
    def emit(self, record: logging.LogRecord):
        log_entry = {
            "time": datetime.fromtimestamp(record.created).isoformat(),
            "level": record.levelname,
            "message": record.msg
        }
        manager.publish("logging", json.dumps(log_entry))

logger.add(WebSocketLogHandler())

router = APIRouter(
    prefix="/ws",
    responses={404: {"description": "Not found"}},
)


@router.websocket("/{topic}")
async def websocket_endpoint(websocket: WebSocket, topic: str):
    await manager.connect(websocket, topic)
    logger.info(f"Client connected to topic: {topic}")
    try:
        while True:
            data = await websocket.receive_text()
            try:
                parsed_data = json.loads(data)
                logger.debug(parsed_data)
            except json.JSONDecodeError:
                logger.error(f"Invalid JSON data received: {data}")
                continue

    except WebSocketDisconnect:
        logger.info(f"Client disconnected from topic: {topic}")
        await manager.disconnect(websocket, topic)