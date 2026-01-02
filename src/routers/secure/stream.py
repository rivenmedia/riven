import asyncio
import json
import logging
from datetime import datetime
import mimetypes
from typing import Annotated
import math
import subprocess

import httpx

from fastapi import APIRouter, HTTPException, Path, Query, Request, Response
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

        return url, item.media_entry.provider or "", item.media_entry.original_filename


def _get_client(provider: str) -> httpx.AsyncClient:
    """Get the appropriate HTTP client based on provider requirements."""
    use_proxy = (
        provider in PROXY_REQUIRED_PROVIDERS
        and settings_manager.settings.downloaders.proxy_url
    )
    return di[ProxyClient] if use_proxy else di[AsyncClient]


def _build_forward_headers(request: Request) -> dict[str, str]:
    """Build headers to forward to upstream."""
    headers: dict[str, str] = {}
    if "range" in request.headers:
        headers["Range"] = request.headers["range"]
    return headers


def _extract_response_headers(upstream_response: httpx.Response, filename: str) -> dict[str, str]:
    """Extract relevant headers from upstream response."""
    headers: dict[str, str] = {}
    for key in ["content-type", "content-length", "content-range", "accept-ranges"]:
        if key in upstream_response.headers:
            headers[key] = upstream_response.headers[key]
    headers["content-disposition"] = f'inline; filename="{filename}"'
    return headers


async def _handle_upstream_error(upstream_response: httpx.Response) -> None:
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

    upstream_response: httpx.Response | None = None
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

        # Force correct MIME type based on extension.
        # Firefox fails on application/octet-stream, which many providers send.
        guessed_type, _ = mimetypes.guess_type(filename)
        if guessed_type:
            response_headers["content-type"] = guessed_type

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

def _get_video_duration(path: str) -> float:
    try:
        result = subprocess.run(
            [
                "ffprobe", 
                "-v", "error", 
                "-show_entries", "format=duration", 
                "-of", "default=noprint_wrappers=1:nokey=1", 
                path
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT
        )
        return float(result.stdout)
    except Exception:
        return 0.0

# ... imports ...
from fastapi import Query

# 1. Playlist: Defaults are now None (Original Quality)
@router.get("/hls/{item_id}/index.m3u8")
async def get_hls_playlist(
    item_id: int,
    # Default to None = Keep Original
    pix_fmt: str | None = None,
    video_profile: str | None = Query(None, alias="profile"),
    level: str | None = None,
    resolution: str | None = None
):
    url, provider, filename = _get_media_info(item_id)
    duration = _get_video_duration(url)
    
    segment_duration = 12
    if duration == 0: num_segments = 10 
    else: num_segments = math.ceil(duration / segment_duration)

    # Build query params ONLY if they exist
    params = []
    if pix_fmt: params.append(f"pix_fmt={pix_fmt}")
    if video_profile: params.append(f"profile={video_profile}")
    if level: params.append(f"level={level}")
    if resolution: params.append(f"resolution={resolution}")
    
    query_string = f"?{'&'.join(params)}" if params else ""

    m3u8_lines = [
        "#EXTM3U",
        "#EXT-X-VERSION:3",
        "#EXT-X-TARGETDURATION:7",
        "#EXT-X-MEDIA-SEQUENCE:0",
        "#EXT-X-PLAYLIST-TYPE:VOD",
    ]

    for i in range(num_segments):
        m3u8_lines.append("#EXT-X-DISCONTINUITY")
        m3u8_lines.append(f"#EXTINF:{segment_duration:.6f},")
        # Segments will inherit the params (or lack thereof)
        m3u8_lines.append(f"segment/{i}.ts{query_string}")

    m3u8_lines.append("#EXT-X-ENDLIST")
    
    return Response(content="\n".join(m3u8_lines), media_type="application/vnd.apple.mpegurl")


# 2. Segment: Defaults are None, apply flags only if requested
@router.get("/hls/{item_id}/segment/{seq}.ts")
async def get_hls_segment(
    item_id: int, 
    seq: int,
    pix_fmt: str | None = None,
    video_profile: str | None = Query(None, alias="profile"),
    level: str | None = None,
    resolution: str | None = None
):
    url, _, _ = _get_media_info(item_id)
    
    segment_duration = 12
    start_time = seq * segment_duration

# Define vf_filter safely to avoid "UnboundLocalError"
    vf_filter = ""
    if resolution:
        if "x" in resolution:
            width, height = resolution.split("x")
            vf_filter = f'-vf "scale={width}:{height}"'
        else:
            vf_filter = f'-vf "scale=-2:{resolution}"'

    # --- FIX 2: Simplified FFmpeg Command ---
    # Removed: -output_ts_offset (It caused the crash)
    # Added: -muxdelay 0 (Reduces latency/overhead)
    cmd = (
        f'ffmpeg -analyzeduration 0 -probesize 5000000 ' 
        f'-ss {start_time} -t {segment_duration} -i "{url}" '
        f'{vf_filter} '
        '-c:v libx264 -preset ultrafast -crf 23 '
        # Apply strict formatting only if requested
        f'{f"-pix_fmt {pix_fmt}" if pix_fmt else ""} '
        f'{f"-profile:v {video_profile}" if video_profile else ""} '
        f'{f"-level {level}" if level else ""} '
        '-c:a aac -b:a 128k '
        '-muxdelay 0 '  # Important for small chunks
        '-f mpegts -'
    )
    
    # Debugging: Uncomment this line to see the exact command in your terminal
    # logger.info(f"FFmpeg CMD: {cmd}")
    
    process = await asyncio.create_subprocess_shell(
        cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE # OR DEVNULL
    )

    async def stream_output():
        if not process.stdout or not process.stderr:
            return
        while True:
            chunk = await process.stdout.read(32 * 1024)
            if not chunk:
                # If no data, check for errors
                if process.returncode and process.returncode != 0:
                     err = await process.stderr.read()
                     logger.error(f"FFmpeg Error: {err.decode()}")
                break
            yield chunk        
        await process.wait()

    return StreamingResponse(stream_output(), media_type="video/mp2t")