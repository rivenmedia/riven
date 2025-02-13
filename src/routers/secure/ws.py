from fastapi import WebSocket, WebSocketDisconnect
import logging
from pydantic import datetime
from program.managers.websocket_manager import manager
import json
from loguru import logger

from .default import router

class WebSocketLogHandler(logging.Handler):
    def emit(self, record: logging.LogRecord):
        log_entry = {
            "time": datetime.fromtimestamp(record.created).isoformat(),
            "level": record.levelname,
            "message": record.msg
        }
        manager.publish_event("logging", json.dumps(log_entry))

logger.add(WebSocket())


@router.websocket("/")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            parsed_data = json.loads(data)
            print(parsed_data)

    except WebSocketDisconnect:
        manager.disconnect(websocket)