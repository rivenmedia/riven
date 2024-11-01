import json
import logging
from datetime import datetime

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from loguru import logger
from pydantic import BaseModel

from program.managers.sse_manager import sse_manager

router = APIRouter(
    responses={404: {"description": "Not found"}},
    prefix="/stream",
    tags=["stream"],
)

class EventResponse(BaseModel):
    data: dict

class SSELogHandler(logging.Handler):
    def emit(self, record: logging.LogRecord):
        log_entry = {
            "time": datetime.fromtimestamp(record.created).isoformat(),
            "level": record.levelname,
            "message": record.msg
        }
        sse_manager.publish_event("logging", json.dumps(log_entry))

logger.add(SSELogHandler())

@router.get("/event_types")
async def get_event_types():
    return {"message": list(sse_manager.event_queues.keys())}

@router.get("/{event_type}")
async def stream_events(_: Request, event_type: str) -> EventResponse:
    return StreamingResponse(sse_manager.subscribe(event_type), media_type="text/event-stream")