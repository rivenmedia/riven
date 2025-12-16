import json
import logging
import mimetypes
import os
import typing
import httpx
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Path, Request, Response, status, HTTPException
from fastapi.responses import StreamingResponse
from kink import di
from loguru import logger
from pydantic import BaseModel

from program.db.db import db_session
from program.managers.sse_manager import sse_manager
from program.media.item import MediaItem
from program.settings import settings_manager
from program.services.streaming.media_stream import PROXY_REQUIRED_PROVIDERS
from program.utils.async_client import AsyncClient
from program.utils.proxy_client import ProxyClient

router = APIRouter(
    responses={404: {"description": "Not found"}},
    prefix="/stream",
    tags=["stream"],
)


class SSELogHandler(logging.Handler):
    def emit(self, record: logging.LogRecord):
        log_entry = {
            "time": datetime.fromtimestamp(record.created).isoformat(),
            "level": record.levelname,
            "message": record.msg,
        }
        sse_manager.publish_event("logging", json.dumps(log_entry))


logger.add(SSELogHandler())


class EventTypesResponse(BaseModel):
    event_types: list[str]


@router.get(
    "/event_types",
    response_model=EventTypesResponse,
)
async def get_event_types():
    return EventTypesResponse(
        event_types=list(sse_manager.subscribers.keys()),
    )


@router.get("/{event_type}")
async def stream_events(
    event_type: Annotated[
        str,
        Path(
            description="The type of event to stream",
            min_length=1,
        ),
    ],
) -> StreamingResponse:
    return StreamingResponse(
        sse_manager.subscribe(event_type),
        media_type="text/event-stream",
    )


@router.get("/file/{item_id}")
async def stream_file(
    item_id: int,
    request: Request,
) -> StreamingResponse:
    """
    Stream a file directly from the provider.
    
    Args:
        item_id: The ID of the MediaItem to stream.
        request: The FastAPI request object.
    
    Returns:
        A StreamingResponse for the file content.
    """
    with db_session() as session:
        item = session.get(MediaItem, item_id)
        
        if not item:
            raise HTTPException(status_code=404, detail="Item not found")
            
        if not item.media_entry:
            raise HTTPException(status_code=404, detail="Item has no media file")

        url = item.media_entry.url
        
        if not url:
            raise HTTPException(status_code=404, detail="Item has no valid stream URL")

        provider = item.media_entry.provider
        filename = item.media_entry.original_filename

    use_proxy = (
        provider in PROXY_REQUIRED_PROVIDERS
        and settings_manager.settings.downloaders.proxy_url
    )

    if use_proxy:
        client = di[ProxyClient]
    else:
        client = di[AsyncClient]

    upstream_response = None
    try:
        forward_headers = {}
        if "range" in request.headers:
            forward_headers["Range"] = request.headers["range"]

        req = client.build_request("GET", url, headers=forward_headers)
        
        try:
            upstream_response = await client.send(req, stream=True)
        except Exception as e:
            logger.error(f"Failed to connect to upstream: {e}")
            raise HTTPException(status_code=502, detail="Upstream connection failed")

        if upstream_response.status_code >= 400:
            try:
                content = await upstream_response.aread()
                logger.error(f"Upstream returned error {upstream_response.status_code}: {content}")
            except Exception:
                pass
            
            await upstream_response.aclose()
            
            raise HTTPException(
                status_code=upstream_response.status_code, 
                detail=f"Upstream error: {upstream_response.status_code}"
            )

        response_headers = {}
        for key in ["content-type", "content-length", "content-range", "accept-ranges"]:
            if key in upstream_response.headers:
                response_headers[key] = upstream_response.headers[key]
        
        response_headers["content-disposition"] = f'inline; filename="{filename}"'

        async def stream_iterator():
            try:
                async for chunk in upstream_response.aiter_bytes():
                    yield chunk
            except Exception as e:
                logger.error(f"Error during streaming: {e}")
            finally:
                await upstream_response.aclose()

        return StreamingResponse(
            stream_iterator(),
            status_code=upstream_response.status_code,
            headers=response_headers,
            media_type=response_headers.get("content-type"),
        )
    except HTTPException:
        raise
    except Exception as e:
        if upstream_response is not None and not upstream_response.is_closed:
            await upstream_response.aclose()
        logger.exception(f"Unexpected error in stream_file: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
