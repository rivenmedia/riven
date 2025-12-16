import json
import logging
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, Request
from fastapi.responses import StreamingResponse
from kink import di
from loguru import logger
from pydantic import BaseModel

from program.db.db import db_session
from program.managers.sse_manager import sse_manager
from program.media.item import MediaItem
from program.services.streaming.media_stream import PROXY_REQUIRED_PROVIDERS
from program.settings import settings_manager
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


def _get_media_info(item_id: int) -> tuple[str, str, str]:
    """
    Retrieve media information for the given item ID.

    Returns:
        Tuple of (url, provider, filename).

    Raises:
        HTTPException: If item not found or has no valid media.
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

        return url, item.media_entry.provider, item.media_entry.original_filename


def _get_client(provider: str) -> AsyncClient:
    """Get the appropriate HTTP client based on provider requirements."""
    use_proxy = (
        provider in PROXY_REQUIRED_PROVIDERS
        and settings_manager.settings.downloaders.proxy_url
    )
    return di[ProxyClient] if use_proxy else di[AsyncClient]


def _build_forward_headers(request: Request) -> dict[str, str]:
    """Build headers to forward to upstream."""
    headers = {}
    if "range" in request.headers:
        headers["Range"] = request.headers["range"]
    return headers


def _extract_response_headers(upstream_response, filename: str) -> dict[str, str]:
    """Extract relevant headers from upstream response."""
    headers = {}
    for key in ["content-type", "content-length", "content-range", "accept-ranges"]:
        if key in upstream_response.headers:
            headers[key] = upstream_response.headers[key]
    headers["content-disposition"] = f'inline; filename="{filename}"'
    return headers


async def _handle_upstream_error(upstream_response) -> None:
    """Log and close failed upstream response."""
    try:
        content = await upstream_response.aread()
        logger.error(
            f"Upstream returned error {upstream_response.status_code}: {content}"
        )
    except Exception as e:
        logger.debug(f"Could not read upstream error content: {e}")

    await upstream_response.aclose()

    raise HTTPException(
        status_code=upstream_response.status_code,
        detail=f"Upstream error: {upstream_response.status_code}",
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
    url, provider, filename = _get_media_info(item_id)
    client = _get_client(provider)
    forward_headers = _build_forward_headers(request)

    upstream_response = None
    try:
        req = client.build_request("GET", url, headers=forward_headers)

        try:
            upstream_response = await client.send(req, stream=True)
        except Exception as e:
            logger.error(f"Failed to connect to upstream: {e}")
            raise HTTPException(status_code=502, detail="Upstream connection failed")

        if upstream_response.status_code >= 400:
            await _handle_upstream_error(upstream_response)

        response_headers = _extract_response_headers(upstream_response, filename)

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
