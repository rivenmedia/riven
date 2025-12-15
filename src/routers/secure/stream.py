import json
import logging
import mimetypes
import os
import typing
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Path, Request, Response, status, HTTPException
from fastapi.responses import StreamingResponse
from loguru import logger
from pydantic import BaseModel

from program.db.db import db_session
from program.managers.sse_manager import sse_manager
from program.media.item import MediaItem
from program.settings import settings_manager

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

def range_stream_response(
    path: str,
    request: Request,
) -> StreamingResponse:
    """
    Returns a StreamingResponse that supports HTTP Range requests for a given file path.
    """
    chunk_size = settings_manager.settings.stream.chunk_size_mb * 1024 * 1024
    file_size = os.path.getsize(path)
    last_modified = datetime.fromtimestamp(os.path.getmtime(path)).strftime(
        "%a, %d %b %Y %H:%M:%S GMT"
    )
    etag = f"{os.path.getmtime(path)}-{file_size}"

    # Check headers
    range_header = request.headers.get("range")

    # Get filename from path
    filename = os.path.basename(path)

    headers = {
        "content-type": mimetypes.guess_type(path)[0] or "application/octet-stream",
        "content-disposition": f'inline; filename="{filename}"',
        "accept-ranges": "bytes",
        "connection": "keep-alive",
        "last-modified": last_modified,
        "etag": etag,
        "cache-control": "no-cache",
    }

    start = 0
    end = file_size - 1
    status_code = status.HTTP_200_OK

    if range_header:
        try:
            # Parse Range header: bytes=start-end
            unit, ranges = range_header.split("=")
            if unit.strip().lower() == "bytes":
                range_str = ranges.split(",")[0].strip()
                start_str, end_str = range_str.split("-")
                
                if start_str:
                    # Normal range: bytes=start-end or bytes=start-
                    start = int(start_str)
                    if end_str:
                        # Clamp end to file_size - 1
                        end = min(int(end_str), file_size - 1)
                    else:
                        # bytes=start- means from start to end of file
                        end = file_size - 1
                elif end_str:
                    # Suffix-range: bytes=-N means last N bytes
                    suffix_length = int(end_str)
                    start = max(0, file_size - suffix_length)
                    end = file_size - 1
                else:
                    # Both empty is invalid, fallback to full download
                    raise ValueError("Invalid range: both start and end are empty")
                
                # Validate range boundaries
                if start >= file_size or start > end:
                    # Requested range not satisfiable
                    return Response(
                        status_code=status.HTTP_416_REQUESTED_RANGE_NOT_SATISFIABLE,
                        headers={"content-range": f"bytes */{file_size}"},
                    )
                
                status_code = status.HTTP_206_PARTIAL_CONTENT
                headers["content-range"] = f"bytes {start}-{end}/{file_size}"
                headers["content-length"] = str(end - start + 1)
        except ValueError:
            # Invalid range header, fallback to full download
            pass

    if status_code == status.HTTP_200_OK:
        headers["content-length"] = str(file_size)

    def file_iterator(file_path: str, offset: int, length: int) -> typing.Generator[bytes, None, None]:
        try:
            with open(file_path, "rb") as f:
                f.seek(offset)
                remaining = length
                while remaining > 0:
                    read_size = min(chunk_size, remaining)
                    data = f.read(read_size)
                    if not data:
                        break
                    yield data
                    remaining -= len(data)
        except OSError:
            # Handle case where VFS is unmounted during shutdown
            return

    return StreamingResponse(
        file_iterator(path, start, end - start + 1),
        status_code=status_code,
        headers=headers,
    )


@router.get("/file/{item_id}")
async def stream_file(
    item_id: int,
    request: Request,
) -> StreamingResponse:
    """
    Stream a file directly from the VFS.
    
    Args:
        item_id: The ID of the MediaItem to stream.
        request: The FastAPI request object.
    
    Returns:
        A StreamingResponse for the file content.
    """
    with db_session() as session:
        # Fetch the item
        item = session.get(MediaItem, item_id)
        
        if not item:
            raise HTTPException(status_code=404, detail="Item not found")
            
        if not item.media_entry:
             raise HTTPException(status_code=404, detail="Item has no media file")

        # Get VFS paths
        vfs_paths = item.media_entry.get_all_vfs_paths()
        
        if not vfs_paths:
            raise HTTPException(status_code=404, detail="Item not found in VFS")
            
        # Construct absolute path to the first VFS entry
        mount_path = settings_manager.settings.filesystem.mount_path
        file_path = os.path.join(mount_path, vfs_paths[0].lstrip("/"))

    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Media file not found on disk")

    return range_stream_response(file_path, request)
