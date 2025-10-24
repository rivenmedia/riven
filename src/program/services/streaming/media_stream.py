from dataclasses import dataclass
from functools import cached_property
import threading
import trio
import pyfuse3
import errno
import httpx

from contextlib import asynccontextmanager
from loguru import logger
from typing import TYPE_CHECKING, TypedDict
from http import HTTPStatus
from kink import di
from collections.abc import AsyncIterator

from src.program.services.streaming.chunk_range import ChunkRange
from src.program.services.streaming.exceptions import (
    ByteLengthMismatchException,
    EmptyDataError,
    RawByteLengthMismatchException,
    ReadPositionMismatchException,
)

if TYPE_CHECKING:
    from src.program.services.filesystem.vfs.rivenvfs import RivenVFS


@dataclass
class Config(TypedDict):
    """Configuration for the media stream."""

    # Reads don't always come in exactly sequentially;
    # they may be interleaved with other reads (e.g. 1 -> 3 -> 2 -> 4).
    #
    # This allows for some tolerance during the calculations.
    sequential_read_tolerance: int

    # Kernel block size; the byte length the OS reads/writes at a time.
    block_size: int

    # Max and min chunk sizes for adaptive chunk sizing.
    max_chunk_size: int
    min_chunk_size: int

    # Target playback duration for each chunk in seconds.
    target_chunk_duration_seconds: int

    # Number of skipped chunks required to trigger a seek
    seek_chunk_tolerance: int


@dataclass
class Connection:
    """Metadata about the current streaming connection."""

    current_read_position: int
    is_connected: bool
    is_closed: bool
    is_killed: bool
    response: httpx.Response | None
    lock: trio.Lock = trio.Lock()

    async def reset(self) -> None:
        if self.response:
            await self.response.aclose()

        self.current_read_position = 0
        self.is_connected = False
        self.is_closed = False
        self.is_killed = False
        self.response = None


@dataclass
class Prefetcher:
    """Configuration for prefetching behaviour."""

    chunks_to_fetch: int
    lookahead_chunks: int
    sequential_chunks_required: int
    lock: threading.Lock = threading.Lock()

    def is_prefetch_enabled(self) -> bool:
        return self.chunks_to_fetch > 0 and self.lookahead_chunks > 0


@dataclass
class SessionStatistics(TypedDict):
    """Statistics about the current streaming session."""

    bytes_transferred: int
    total_session_connections: int


@dataclass
class FileMetadata(TypedDict):
    """Metadata about the file being streamed."""

    bitrate: int | None
    duration: float | None
    original_filename: str
    file_size: int
    path: str


class MediaStream:
    """
    Represents an active streaming session for a file.

    This class manages the streaming of media content, including handling
    connections, fetching data, and managing playback.
    """

    response: httpx.Response | None
    iterator: AsyncIterator[bytes]
    target_url: str

    def __init__(
        self,
        *,
        vfs: "RivenVFS",
        fh: pyfuse3.FileHandleT,
        file_size: int,
        path: str,
        original_filename: str,
        bitrate: int | None = None,
        duration: float | None = None,
        header_size: int | None = None,
    ) -> None:
        self.config = Config(
            block_size=1024 * 128,  # 128 kB TODO: try to determine this from stream/OS
            max_chunk_size=10 * 1024 * 1024,  # 5 MiB
            min_chunk_size=256 * 1024,  # 256 kB
            sequential_read_tolerance=1024 * 128 * 10,  # 10 128kB blocks
            target_chunk_duration_seconds=2,
            seek_chunk_tolerance=2,
        )

        self.session_statistics = SessionStatistics(
            bytes_transferred=0,
            total_session_connections=0,
        )

        self.connection = Connection(
            current_read_position=0,
            is_closed=False,
            is_connected=False,
            is_killed=False,
            response=None,
        )

        self.prefetcher = Prefetcher(
            chunks_to_fetch=5,
            lookahead_chunks=2,
            sequential_chunks_required=3,
        )

        self.file_metadata = FileMetadata(
            bitrate=bitrate,
            duration=duration,
            file_size=file_size,
            path=path,
            original_filename=original_filename,
        )

        self.lock = trio.Lock()
        self.vfs = vfs
        self.fh = fh

        self._sequential_chunk_fetches = 0
        self._last_read_end = 0
        self._header_size = header_size

        logger.trace(
            f"Initialized stream for {self.file_metadata['path']} "
            f"with chunk size {self.chunk_size / (1024 * 1024):.2f} MB "
            f"[{self.chunk_size // (1024 * 128)} blocks]. "
            f"bitrate={self.file_metadata['bitrate']}, "
            f"duration={self.file_metadata['duration']}, "
            f"file_size={self.file_metadata['file_size']} bytes"
        )

        try:
            self.async_client = di[httpx.AsyncClient]
        except KeyError:
            raise RuntimeError(
                "httpx.AsyncClient not found in dependency injector"
            ) from None

    @property
    def is_prefetch_enabled(self) -> bool:
        """Whether prefetching is enabled based on recent chunk access patterns."""

        # Determines whether the prefetch lock is available. If it isn't,
        # we don't want to start another prefetch operation.
        is_lock_available = not self.prefetcher.lock.locked()

        # Determine if we've had enough sequential chunk fetches to trigger prefetching.
        # This helps to avoid scans from triggering unnecessary prefetches.
        is_sequential_chunk_fetcher = (
            self._sequential_chunk_fetches >= self.prefetcher.sequential_chunks_required
        )

        # Determine if the current read position is within the prefetch lookahead range.
        is_within_prefetch_lookahead = (
            self.connection.current_read_position - self._last_read_end
        ) // self.chunk_size <= self.prefetcher.lookahead_chunks

        return (
            is_lock_available
            and is_sequential_chunk_fetcher
            and is_within_prefetch_lookahead
        )

    @property
    def header_size(self) -> int:
        if not self._header_size:
            logger.error(
                f"Attempting to access header_size before it is set for {self.file_metadata['path']}"
            )

            raise AttributeError("header_size not set") from None

        return self._header_size

    @property
    def scan_tolerance(self) -> int:
        """Tolerance for detecting scan reads. Any read that jumps more than this value is considered a scan."""

        return 1024 * 128 * 25  # 25 128kB blocks

    @cached_property
    def chunk_size(self) -> int:
        """An optimal chunk size based on the file's bitrate."""

        target_chunk_duration_seconds = self.config["target_chunk_duration_seconds"]

        bitrate = self.file_metadata["bitrate"]

        if bitrate:
            bytes_per_second = bitrate // 8  # Convert bits to bytes
            calculated_chunk_size = (
                (bytes_per_second // 1024) * 1024 * target_chunk_duration_seconds
            )

            # Clamp chunk size between 256kB and 5MiB
            min_chunk_size = self.config["min_chunk_size"]
            max_chunk_size = self.config["max_chunk_size"]

            clamped_chunk_size = max(
                min(calculated_chunk_size, max_chunk_size),
                min_chunk_size,
            )

            # Align chunk size to nearest 128kB boundary, rounded up.
            # This attempts to avoid cross-chunk reads that require expensive cache lookups.
            block_size = 1024 * 128
            aligned_chunk_size = -(clamped_chunk_size // -block_size) * block_size

            return aligned_chunk_size
        else:
            # Fallback to default chunk size if bitrate not available
            return 1024 * 1024  # 1MiB default chunk size

    @cached_property
    def footer_size(self) -> int:
        """An optimal footer size for scanning based on file size."""

        # Use a percentage-based approach for requesting the footer
        # using the file size to determine an appropriate range.

        min_footer_size = 1024 * 16  # Minimum footer size of 16KB
        max_footer_size = self.chunk_size * 2  # Maximum footer size of 2 chunks
        footer_percentage = 0.002  # 0.2% of file size

        percentage_size = int(self.file_metadata["file_size"] * footer_percentage)

        return min(max(percentage_size, min_footer_size), max_footer_size)

    @asynccontextmanager
    async def manage_connection(self) -> AsyncIterator[None]:
        """Context manager to handle stream connection lifecycle."""

        try:
            yield
        except httpx.RemoteProtocolError as e:
            logger.warning(
                f"HTTP protocol error occurred while managing stream connection for {self.file_metadata['path']}: "
                f"{e}. "
                f"Likely timed out; attempting to reconnect..."
            )

            await self.connect(self.connection.current_read_position)

            if not self.connection.is_connected:
                logger.error(
                    f"Failed to reconnect stream connection for {self.file_metadata['path']}"
                )

                raise pyfuse3.FUSEError(errno.EIO) from e
        except Exception as e:
            logger.error(
                f"{e.__class__.__name__} occurred while managing stream connection for {self.file_metadata['path']}: {e}"
            )
            raise

    async def connect(self, position: int) -> None:
        """Establish a streaming connection starting at the given byte offset, aligned to the closest chunk."""

        self.connection.response = await self._prepare_response(start=position)
        self.connection.is_connected = True
        self.connection.current_read_position = position

        self.iterator = self.connection.response.aiter_bytes(chunk_size=self.chunk_size)

        logger.trace(
            f"{self.connection.response.http_version} stream connection established for {self.file_metadata['path']} "
            f"from byte {position} / {self.file_metadata['file_size']}."
        )

    async def seek(self, position: int) -> None:
        """Seek to a specific byte position in the stream."""

        await self.close()
        await self.connect(position=position)

    async def scan_header(self, read_position: int, size: int) -> bytes:
        """Scan the first N bytes of the media stream, and set the header size, to be used in future chunk calculations."""

        # Header size isn't known until the first fetch has happened
        self._header_size = size

        data = await self._fetch_discrete_byte_range(
            start=0,
            size=size,
        )

        return data[read_position : read_position + size]

    async def scan_footer(self, read_position: int, size: int) -> bytes:
        """
        Scans the end of the media file for footer data.

        This "overfetches" for the individual request,
        but multiple footer requests tend to be made to retrieve more data later,
        so this is more efficient than making multiple small requests.
        """

        file_size = self.file_metadata["file_size"]
        footer_start = file_size - self.footer_size

        data = await self._fetch_discrete_byte_range(
            start=footer_start,
            size=file_size - footer_start,
        )

        slice_offset = read_position - footer_start

        return data[slice_offset : slice_offset + size]

    async def scan(self, read_position: int, size: int) -> bytes:
        """Fetch extra data for scanning purposes."""

        data = await self._fetch_discrete_byte_range(
            start=read_position,
            size=size,
            should_cache=False,
        )

        return data[:size]

    def detect_scan_type(self) -> None:
        pass

    async def read(
        self,
        *,
        request_start: int,
        request_end: int,
        request_size: int,
    ) -> bytes:
        """Handles incoming read requests from the VFS."""

        async with self.manage_connection():
            async with self.lock:
                logger.trace(
                    f"Read request: path={self.file_metadata['path']} "
                    f"fh={self.fh} "
                    f"request_start={request_start} "
                    f"request_end={request_end} "
                    f"size={request_size}"
                )

                # Try cache first for the exact request (cache handles chunk lookup and slicing)
                # Use cache_key to share cache between all paths pointing to same file
                cached_bytes = await trio.to_thread.run_sync(
                    lambda: self.vfs.cache.get(
                        cache_key=self.file_metadata["original_filename"],
                        start=request_start,
                        end=request_end,
                    )
                )

                if cached_bytes:
                    returned_data = cached_bytes

                    self._last_read_end = request_end
                else:
                    is_header_scan = self._last_read_end == 0 and request_start == 0

                    file_size = self.file_metadata["file_size"]

                    is_footer_scan = (
                        self._last_read_end
                        < request_start - self.config["sequential_read_tolerance"]
                    ) and file_size - self.footer_size <= request_start <= file_size

                    is_general_scan = (
                        not is_header_scan
                        and not is_footer_scan
                        and (
                            (
                                # This behaviour is seen during scanning
                                # and captures large jumps in read position
                                # generally observed when the player is reading the footer
                                # for cues or metadata after initial playback start.
                                #
                                # Scans typically read less than a single block (128 kB).
                                abs(self._last_read_end - request_start)
                                > self.scan_tolerance
                                and request_start != self.header_size
                                and request_size < 1024 * 128
                            )
                            or (
                                # This behaviour is seen when seeking.
                                # Playback has already begun, so the header has been served
                                # for this file, but the scan happens on a new file handle
                                # and is the first request to be made.
                                self.header_size
                                and self._last_read_end == 0
                            )
                        )
                    )

                    logger.trace(
                        f"is_header_scan={is_header_scan}, "
                        f"is_footer_scan={is_footer_scan}, "
                        f"is_general_scan={is_general_scan}"
                    )

                    if is_header_scan:
                        logger.trace("Performing header scan read")

                        returned_data = await self.scan_header(
                            read_position=request_start,
                            size=self.header_size,
                        )
                    elif is_footer_scan:
                        logger.trace("Performing footer scan read")

                        returned_data = await self.scan_footer(
                            read_position=request_start,
                            size=request_size,
                        )
                    elif is_general_scan:
                        logger.trace("Performing general scan read")

                        returned_data = await self.scan(
                            read_position=request_start,
                            size=request_size,
                        )
                    else:
                        logger.trace(f"Performing normal read")
                        self._last_read_end = request_end

                        returned_data = await self.read_bytes(
                            start=request_start,
                            end=request_end,
                        )

                logger.trace(
                    f"seq_fetches={self._sequential_chunk_fetches} "
                    f"current_read_position={self.connection.current_read_position} "
                    f"last_read_end={self._last_read_end} "
                    f"bytediff={self.connection.current_read_position - self._last_read_end} "
                    f"chunkdiff={(self.connection.current_read_position - self._last_read_end) // self.chunk_size}"
                )

                if self.is_prefetch_enabled:
                    logger.trace(f"Starting prefetch for {self.file_metadata['path']}")

                    trio.lowlevel.spawn_system_task(self.prefetch, 5)

                return returned_data

    async def read_bytes(self, start: int, end: int) -> bytes:
        """Read a specific number of bytes from the stream."""

        async with self.connection.lock:
            # Chunk boundaries for the request
            request_chunk_range = self._get_chunk_range(
                position=start,
                size=end - start + 1,
            )

            # Check the entire requested range for cached data again inside the lock,
            # since other reads may have populated the cache since we last checked.
            cached_data = await trio.to_thread.run_sync(
                lambda: self.vfs.cache.get(
                    cache_key=self.file_metadata["original_filename"],
                    start=start,
                    end=end,
                )
            )

            if cached_data:
                logger.debug(
                    f"Cache hit for {self.file_metadata['path']} {(start, end)} [fh {self.fh}]"
                )

                return cached_data

            # A cross-chunk request is when the start and end positions span multiple chunks.
            # Usually this means the left chunk will be cached, and the right chunk will be streamed.
            # However, in some cases (e.g. seeks), the previous chunk may not be cached.
            # When a stream is connected, it is automatically aligned to the nearest chunk start.
            if request_chunk_range.is_cross_chunk_request:
                # Check to see if a previous request contains cached bytes
                cached_data = await trio.to_thread.run_sync(
                    lambda: self.vfs.cache.get(
                        cache_key=self.file_metadata["original_filename"],
                        start=start,
                        end=request_chunk_range.first_chunk["end"],
                    )
                )

                if cached_data:
                    request_chunk_range.cached_bytes_size = len(cached_data)

                    logger.trace(
                        f"Cached bytes length: {len(cached_data)} for {self.file_metadata['path']} [fh {self.fh}]"
                    )
            else:
                cached_data = b""

            if not self.connection.is_connected:
                await self.connect(position=request_chunk_range.first_chunk["start"])

            if (
                start + request_chunk_range.cached_bytes_size
                < self.connection.current_read_position
            ):
                logger.trace(
                    f"Requested start {start} "
                    f"is before current read position {self.connection.current_read_position} "
                    f"for {self.file_metadata['path']}. "
                    f"Seeking to new start position {request_chunk_range.first_chunk['start']}/{self.file_metadata['file_size']}."
                )

                # Always seek backwards if the requested start is before the current read position.
                # Streams can only read forwards, so a new connection must be made.
                await self.seek(position=request_chunk_range.first_chunk["start"])

            read_position_chunk_range = self._get_chunk_range(
                position=self.connection.current_read_position
            )

            # Check if requested start is after current read position,
            # and if it exceeds the seek tolerance, move the stream to the new start.
            if start > self.connection.current_read_position:
                chunk_difference = read_position_chunk_range.calculate_chunk_difference(
                    request_chunk_range
                )

                if chunk_difference >= self.config["seek_chunk_tolerance"]:
                    logger.trace(
                        f"Requested start {start} "
                        f"is after current read position {self.connection.current_read_position} "
                        f"for {self.file_metadata['path']}. "
                        f"Seeking to new start position {request_chunk_range.first_chunk['start']}/{self.file_metadata['file_size']}."
                    )

                    await self.seek(position=request_chunk_range.first_chunk["start"])

                    # Update the read position chunk range after the seek
                    read_position_chunk_range = self._get_chunk_range(
                        position=self.connection.current_read_position
                    )

            data = b""

            # Get the chunk-aligned start for caching based on the stream's current read position
            cache_chunk_start = read_position_chunk_range.first_chunk["start"]

            logger.trace(
                f"request_chunk_range={request_chunk_range} for {self.file_metadata['path']} [fh {self.fh}]"
            )

            if (
                self.connection.current_read_position
                == request_chunk_range.first_chunk["start"]
            ):
                self._sequential_chunk_fetches += 1
            else:
                self._sequential_chunk_fetches = 0

            async for chunk in self.iterator:
                data += chunk

                self.connection.current_read_position += len(chunk)
                self.session_statistics["bytes_transferred"] += len(chunk)

                if (
                    self.connection.current_read_position
                    >= request_chunk_range.last_chunk["end"] + 1
                ):
                    break

            await self._cache_chunk(cache_chunk_start, data)

            stitched_data = cached_data + data

            # Verify the data that was fetched matches what should be returned
            self._verify_read_integrity(
                chunk_range=request_chunk_range,
                data=stitched_data,
            )

            return stitched_data[request_chunk_range.chunk_slice]

    async def prefetch(self, chunks_to_fetch: int) -> None:
        with self.prefetcher.lock:
            for _ in range(chunks_to_fetch):
                async with self.manage_connection():
                    chunk_range = self._get_chunk_range(
                        self.connection.current_read_position
                    )

                    await self.read_bytes(
                        chunk_range.first_chunk["start"],
                        chunk_range.last_chunk["end"],
                    )

                    logger.trace(
                        f"Prefetched chunk range: {chunk_range} for {self.file_metadata['path']}"
                    )

    async def close(self) -> None:
        """Close the active stream."""

        await self.connection.reset()

        logger.debug(
            f"Ended stream for {self.file_metadata['path']} fh={self.fh} "
            f"after transferring {self.session_statistics['bytes_transferred'] / (1024 * 1024):.2f}MB "
            f"in {self.session_statistics['total_session_connections']} connections."
        )

    async def _fetch_discrete_byte_range(
        self,
        start: int,
        size: int,
        should_cache: bool = True,
    ) -> bytes:
        """Fetch a discrete range of data outside of the main stream. Used for fetching the header/footer."""

        if start < 0:
            raise ValueError("Start must be non-negative")

        if size <= 0:
            raise ValueError("Size must be positive")

        response = await self._prepare_response(
            start,
            end=start + size - 1,
        )

        data = b""

        async for chunk in response.aiter_bytes(chunk_size=min(size, self.chunk_size)):
            data += chunk

            if len(data) >= size:
                break

        self.session_statistics["bytes_transferred"] += len(data)

        self._verify_scan_integrity((start, start + size), data)

        if should_cache:
            await self._cache_chunk(start, data[:size])

        return data

    async def _attempt_range_preflight_checks(
        self,
        headers: httpx.Headers,
    ) -> None:
        """
        Attempts to verify that the server will honour range requests by requesting the HEAD of the media URL.

        Sometimes, the request will return a 200 OK with the full content instead of a 206 Partial Content,
        even when the server *does* support range requests.

        This wastes bandwidth, and is undesirable for streaming large media files.

        Returns:
            The effective URL that was successfully used (may differ from input if refreshed).
        """

        max_preflight_attempts = 4
        backoffs = [0.2, 0.5, 1.0]

        # Get entry info from DB
        # Only unrestrict if there's no unrestricted URL already (force_resolve=False)
        # Let the refresh logic handle re-unrestricting on failures
        entry_info = await trio.to_thread.run_sync(
            lambda: self.vfs.db.get_entry_by_original_filename(
                self.file_metadata["original_filename"],
                True,  # for_http (use unrestricted URL if available)
                False,  # force_resolve (don't unrestrict if already have unrestricted URL)
            )
        )

        if not entry_info:
            logger.error(f"No entry info for {self.file_metadata['original_filename']}")
            raise pyfuse3.FUSEError(errno.ENOENT)

        self.target_url = entry_info["url"]

        if not self.target_url:
            logger.error(f"No URL for {self.file_metadata['original_filename']}")
            raise pyfuse3.FUSEError(errno.ENOENT)

        for preflight_attempt in range(max_preflight_attempts):
            try:
                preflight_response = await self.async_client.head(
                    url=self.target_url,
                    headers=headers,
                    follow_redirects=True,
                )
                preflight_response.raise_for_status()

                preflight_status_code = preflight_response.status_code

                if preflight_status_code == HTTPStatus.PARTIAL_CONTENT:
                    # Preflight passed, proceed to actual request
                    return
                elif preflight_status_code == HTTPStatus.OK:
                    # Server refused range request. Serving this request would return the full media file,
                    # which eats downloader bandwidth usage unnecessarily. Wait and retry.
                    logger.warning(
                        f"Server doesn't support range requests yet: path={self.file_metadata['path']}"
                    )

                    if await self._retry_with_backoff(
                        preflight_attempt, max_preflight_attempts, backoffs
                    ):
                        continue

                    # Unable to get range support after retries
                    raise pyfuse3.FUSEError(errno.EIO)
            except httpx.RemoteProtocolError as e:
                logger.debug(
                    f"HTTP protocol error (attempt {preflight_attempt + 1}/{max_preflight_attempts}): path={self.file_metadata['path']} error={type(e).__name__}"
                )

                if await self._retry_with_backoff(
                    preflight_attempt,
                    max_preflight_attempts,
                    backoffs,
                ):
                    continue

                raise pyfuse3.FUSEError(errno.EIO) from e
            except httpx.HTTPStatusError as e:
                preflight_status_code = e.response.status_code

                logger.debug(
                    f"Preflight HTTP error {preflight_status_code}: path={self.file_metadata['path']}"
                )

                if preflight_status_code in (HTTPStatus.NOT_FOUND, HTTPStatus.GONE):
                    # File can't be found at this URL; try refreshing the URL once
                    if preflight_attempt == 0:
                        fresh_url = await trio.to_thread.run_sync(
                            self._refresh_download_url
                        )

                        if fresh_url:
                            logger.warning(
                                f"URL refresh after HTTP {preflight_status_code}: path={self.file_metadata['path']}"
                            )

                            if await self._retry_with_backoff(
                                preflight_attempt, max_preflight_attempts, backoffs
                            ):
                                continue
                    # No fresh URL or still erroring after refresh
                    raise pyfuse3.FUSEError(errno.ENOENT) from e
                else:
                    # Other unexpected status codes
                    logger.warning(
                        f"Unexpected preflight HTTP {preflight_status_code}: path={self.file_metadata['path']}"
                    )
                    raise pyfuse3.FUSEError(errno.EIO) from e
            except (httpx.TimeoutException, httpx.ConnectError, httpx.InvalidURL) as e:
                logger.debug(
                    f"HTTP request failed (attempt {preflight_attempt + 1}/{max_preflight_attempts}): path={self.file_metadata['path']} error={type(e).__name__}"
                )

                if preflight_attempt == 0:
                    # On first exception, try refreshing the URL in case it's a connectivity issue
                    fresh_url = await trio.to_thread.run_sync(
                        self._refresh_download_url
                    )

                    if fresh_url:
                        logger.warning(
                            f"URL refresh after timeout: path={self.file_metadata['path']}"
                        )

                if await self._retry_with_backoff(
                    preflight_attempt, max_preflight_attempts, backoffs
                ):
                    continue

                raise pyfuse3.FUSEError(errno.EIO) from e
            except pyfuse3.FUSEError:
                raise
            except Exception:
                logger.exception(
                    f"Unexpected error during preflight checks for {self.file_metadata['path']}"
                )

                if await self._retry_with_backoff(
                    preflight_attempt, max_preflight_attempts, backoffs
                ):
                    continue

                raise pyfuse3.FUSEError(errno.EIO) from None
        raise pyfuse3.FUSEError(errno.EIO)

    async def _prepare_response(
        self,
        start: int,
        *,
        end: int | None = None,
    ) -> httpx.Response:
        """Establish a streaming connection starting at the given byte offset."""

        headers = httpx.Headers(
            {
                "Accept-Encoding": "identity",
                "Connection": "keep-alive",
                "Range": f"bytes={start}-{end or ''}",
            }
        )

        try:
            await self._attempt_range_preflight_checks(headers)
        except Exception as e:
            logger.error(
                f"Preflight checks failed for {self.file_metadata['path']}: {e}"
            )
            raise

        max_attempts = 4
        backoffs = [0.2, 0.5, 1.0]

        for attempt in range(max_attempts):
            try:
                request = httpx.Request("GET", url=self.target_url, headers=headers)
                response = await self.async_client.send(request, stream=True)

                response.raise_for_status()

                content_length = response.headers.get("Content-Length")
                range_bytes = self.file_metadata["file_size"] - start

                if (
                    response.status_code == HTTPStatus.OK
                    and content_length is not None
                    and int(content_length) > range_bytes
                ):
                    # Server appears to be ignoring range request and returning full content
                    # This shouldn't happen due to preflight, treat as error
                    logger.warning(
                        f"Server returned full content instead of range: path={self.file_metadata['path']}"
                    )
                    raise pyfuse3.FUSEError(errno.EIO)

                self.session_statistics["total_session_connections"] += 1

                return response
            except httpx.HTTPStatusError as e:
                status_code = e.response.status_code

                if status_code == HTTPStatus.FORBIDDEN:
                    # Forbidden - could be rate limiting or auth issue, don't refresh URL
                    logger.debug(
                        f"HTTP 403 Forbidden: path={self.file_metadata['path']} attempt={attempt + 1}"
                    )

                    if await self._retry_with_backoff(attempt, max_attempts, backoffs):
                        continue

                    raise pyfuse3.FUSEError(errno.EACCES) from e
                elif status_code in (HTTPStatus.NOT_FOUND, HTTPStatus.GONE):
                    # Preflight catches initial not found errors and attempts to refresh the URL
                    # if it still happens after a real request, don't refresh again and bail out
                    raise pyfuse3.FUSEError(errno.ENOENT) from e
                elif status_code == HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE:
                    # Requested range not satisfiable; treat as EOF
                    raise pyfuse3.FUSEError(errno.EINVAL) from e
                elif status_code == HTTPStatus.TOO_MANY_REQUESTS:
                    # Rate limited - back off exponentially, don't refresh URL
                    logger.warning(
                        f"HTTP 429 Rate Limited: path={self.file_metadata['path']} attempt={attempt + 1}"
                    )

                    if await self._retry_with_backoff(attempt, max_attempts, backoffs):
                        continue

                    raise pyfuse3.FUSEError(errno.EAGAIN) from e
                else:
                    # Other unexpected status codes
                    logger.warning(
                        f"Unexpected HTTP {status_code}: path={self.file_metadata['path']}"
                    )
                    raise pyfuse3.FUSEError(errno.EIO) from e
            except (
                httpx.TimeoutException,
                httpx.ConnectError,
                httpx.InvalidURL,
            ) as e:
                logger.debug(
                    f"HTTP request failed (attempt {attempt + 1}/{max_attempts}): path={self.file_metadata['path']} error={type(e).__name__}"
                )

                if attempt == 0:
                    # On first exception, try refreshing the URL in case it's a connectivity issue
                    fresh_url = await trio.to_thread.run_sync(
                        self._refresh_download_url
                    )

                    if fresh_url:
                        logger.warning(
                            f"URL refresh after timeout: path={self.file_metadata['path']}"
                        )

                if await self._retry_with_backoff(attempt, max_attempts, backoffs):
                    continue

                raise pyfuse3.FUSEError(errno.EIO) from e
            except httpx.RemoteProtocolError as e:
                # This can happen if the server closes the connection prematurely
                logger.debug(
                    f"HTTP protocol error (attempt {attempt + 1}/{max_attempts}): path={self.file_metadata['path']} error={type(e).__name__}"
                )

                if await self._retry_with_backoff(attempt, max_attempts, backoffs):
                    continue

                raise pyfuse3.FUSEError(errno.EIO) from e
            except pyfuse3.FUSEError:
                raise
            except Exception:
                logger.exception(
                    f"Unexpected error fetching data block for {self.file_metadata['path']}"
                )
                raise pyfuse3.FUSEError(errno.EIO) from None

        raise pyfuse3.FUSEError(errno.EIO)

    def _get_chunk_range(
        self,
        position: int,
        size: int = 1,
    ) -> ChunkRange:
        """Get the range of bytes required to fulfill a read at the given position and for the given size, aligned to chunk boundaries."""

        return ChunkRange(
            position=position,
            chunk_size=self.chunk_size,
            header_size=self.header_size,
            size=size,
        )

    async def _cache_chunk(self, start: int, data: bytes) -> None:
        await trio.to_thread.run_sync(
            lambda: self.vfs.cache.put(
                self.file_metadata["original_filename"],
                start,
                data,
            )
        )

    def _refresh_download_url(self) -> bool:
        """
        Refresh download URL by unrestricting from provider.

        Updates the database with the fresh URL.

        Returns:
            True if successfully refreshed, False otherwise
        """
        # Query database by original_filename and force unrestrict
        entry_info = self.vfs.db.get_entry_by_original_filename(
            original_filename=self.file_metadata["original_filename"],
            for_http=True,
            force_resolve=True,
        )

        if entry_info:
            fresh_url = entry_info.get("url")

            if fresh_url and fresh_url != self.target_url:
                logger.debug(
                    f"Refreshed URL for {self.file_metadata['original_filename']}"
                )

                self.target_url = fresh_url

                return True

        return False

    async def _retry_with_backoff(
        self,
        attempt: int,
        max_attempts: int,
        backoffs: list[float],
    ) -> bool:
        """
        Common retry logic

        Returns:
            True if should retry, False if max attempts reached
        """
        if attempt < max_attempts - 1:
            await trio.sleep(backoffs[min(attempt, len(backoffs) - 1)])
            return True

        return False

    def _verify_scan_integrity(
        self,
        range: tuple[int, int],
        data: bytes,
    ) -> None:
        """
        Verify the integrity of the data read from the stream for scanning purposes.

        Args:
            range: The byte range that was requested
            data: The data read from the stream
        """

        if data == b"":
            raise EmptyDataError(range=range)

        start, end = range
        expected_length = end - start

        if len(data) < expected_length:
            raise RawByteLengthMismatchException(
                expected_length=expected_length,
                actual_length=len(data),
                range=range,
            )

    def _verify_read_integrity(self, chunk_range: ChunkRange, data: bytes) -> None:
        """
        Verify the integrity of the data read from the stream against the requested chunk range.

        Args:
            chunk_range: The ChunkRange object representing the requested range
            data: The data read from the stream
        """

        expected_raw_length = chunk_range.bytes_required + chunk_range.cached_bytes_size

        if expected_raw_length != len(data):
            raise RawByteLengthMismatchException(
                expected_length=expected_raw_length,
                actual_length=len(data),
                range=chunk_range.request_range,
            )

        last_chunk_end = chunk_range.last_chunk["end"]

        if self.connection.current_read_position != last_chunk_end + 1:
            raise ReadPositionMismatchException(
                expected_position=last_chunk_end + 1,
                actual_position=self.connection.current_read_position,
            )

        sliced_data = data[chunk_range.chunk_slice]
        sliced_data_length = len(sliced_data)

        if sliced_data_length == 0:
            raise EmptyDataError(range=chunk_range.request_range)

        if sliced_data_length != chunk_range.size:
            raise ByteLengthMismatchException(
                expected_length=chunk_range.size,
                actual_length=sliced_data_length,
                range=chunk_range.request_range,
                slice_range=chunk_range.chunk_slice,
            )
