import trio
import trio_util
import pyfuse3
import errno
import httpx

from dataclasses import dataclass
from functools import cached_property
from contextlib import asynccontextmanager
from loguru import logger
from typing import Literal
from http import HTTPStatus
from kink import di
from collections.abc import AsyncGenerator, AsyncIterator
from ordered_set import OrderedSet

from program.settings.manager import settings_manager
from program.utils import benchmark

from .chunker import ChunkCacheNotifier, ChunkRange, Chunker
from .config import Config
from .exceptions import (
    CacheDataNotFoundException,
    ChunksTooSlowException,
    EmptyDataException,
    FatalMediaStreamException,
    ByteLengthMismatchException,
    RecoverableMediaStreamException,
)
from .file_metadata import FileMetadata
from .recent_reads import Read, RecentReads
from .session_statistics import SessionStatistics
from .stream_connection import (
    StreamConnection,
)


# Providers that require proxy connections for streaming
PROXY_REQUIRED_PROVIDERS = {"alldebrid"}


type ReadType = Literal[
    "header_scan",
    "footer_scan",
    "general_scan",
    "body_read",
    "footer_read",
    "cache_hit",
    "unknown",
]


@dataclass(frozen=True, init=True)
class ReadEvent:
    type: ReadType
    chunk_range: ChunkRange


class MediaStream:
    """
    Represents an active streaming session for a file.

    This class manages the streaming of media content, including handling
    connections, fetching data, and managing playback.
    """

    target_url: str

    def __init__(
        self,
        *,
        fh: pyfuse3.FileHandleT,
        file_size: int,
        path: str,
        original_filename: str,
        provider: str | None = None,
        initial_url: str | None = None,
    ) -> None:
        fs = settings_manager.settings.filesystem

        self.fh = fh
        self.recent_reads: RecentReads = RecentReads()
        self.connection: StreamConnection | None = None
        self.is_streaming: trio_util.AsyncBool = trio_util.AsyncBool(False)
        self.is_killed: trio_util.AsyncBool = trio_util.AsyncBool(False)
        self._stream_error: trio_util.AsyncValue[Exception | None] = (
            trio_util.AsyncValue(None)
        )

        # Store initial URL if provided to avoid redundant unrestrict calls
        if initial_url:
            self.target_url = initial_url

        self.config = Config(
            sequential_read_tolerance_blocks=10,
            target_chunk_duration_seconds=2,
            seek_chunk_tolerance=5,
            scan_tolerance_blocks=25,
            default_bitrate=10 * 1000 * 1000,  # 10 Mbps
        )

        self.session_statistics = SessionStatistics()

        self.file_metadata = FileMetadata(
            file_size=file_size,
            path=path,
            original_filename=original_filename,
        )

        self.chunker = Chunker(
            cache_key=self.file_metadata["original_filename"],
            chunk_size=self.config.chunk_size,
            header_size=self.config.header_size,
            footer_size=self.footer_size,
            file_size=file_size,
        )

        logger.log(
            "STREAM",
            self._build_log_message(
                f"Initialized stream with chunk size {self.config.chunk_size / (1024 * 1024):.2f} MB. "
                f"file_size={self.file_metadata['file_size']} bytes",
            ),
        )

        # Validate cache size
        # Cache needs to hold 10 chunks (10MiB) to avoid thrashing with concurrent reads
        min_cache_mb = (self.config.chunk_size * 10) // (1024 * 1024)

        if fs.cache_max_size_mb < min_cache_mb:
            logger.warning(
                self._build_log_message(
                    f"Cache size ({fs.cache_max_size_mb}MB) is too small. "
                    f"Minimum recommended: {min_cache_mb}MB. "
                    f"Cache thrashing may occur with concurrent reads, causing poor performance."
                )
            )

        # Use proxy client if provider requires it
        if (
            provider in PROXY_REQUIRED_PROVIDERS
            and settings_manager.settings.downloaders.proxy_url
        ):
            self.async_client = di["ProxyClient"]
        else:
            self.async_client = di[httpx.AsyncClient]

    @cached_property
    def footer_size(self) -> int:
        """An optimal footer size for scanning based on file size."""

        # Use a percentage-based approach for requesting the footer
        # using the file size to determine an appropriate range.

        min_footer_size = 1024 * 16  # Minimum footer size of 16KB
        max_footer_size = 10 * 1024 * 1024  # Maximum footer size of 10MB
        footer_percentage = 0.002  # 0.2% of file size

        percentage_size = int(self.file_metadata["file_size"] * footer_percentage)

        raw_footer_size = min(max(percentage_size, min_footer_size), max_footer_size)
        aligned_footer_size = (
            -(raw_footer_size // -self.config.block_size) * self.config.block_size
        )

        return aligned_footer_size

    @asynccontextmanager
    async def stream_lifecycle(self) -> AsyncGenerator[None]:
        """Context manager for managing stream lifecycle."""

        try:
            self.is_streaming.value = True

            logger.log(
                "STREAM",
                self._build_log_message("Starting stream lifecycle"),
            )

            yield
        finally:
            self.is_streaming.value = False

            logger.log("STREAM", self._build_log_message("Stream lifecycle ended"))

    @asynccontextmanager
    async def manage_connection(
        self,
        *,
        position: int,
    ) -> AsyncIterator[StreamConnection]:
        """Context manager to handle connection lifecycle."""

        try:
            connection = await self.connect(position=position)

            self.connection = connection

            yield connection
        except httpx.HTTPStatusError as e:
            status_code = e.response.status_code

            logger.exception(
                self._build_log_message(
                    f"HTTPStatusError {status_code} occurred whilst managing stream connection: {e}"
                )
            )

            # If we got to this point, the connection was unable to be established,
            # even after preflight checks and exponential backoff retries.
            # This is a fatal error; the stream cannot be read.
            raise FatalMediaStreamException(e) from e
        except (
            httpx.ReadError,
            httpx.RemoteProtocolError,
            httpx.StreamClosed,
            httpx.ConnectError,
        ) as e:
            logger.exception(
                self._build_log_message(
                    f"{e.__class__.__name__} error occurred whilst managing stream connection: {e}"
                )
            )

            # If no connection exists, it means we failed to establish one.
            # This is a fatal error; the stream cannot be read.
            if not self.connection:
                raise FatalMediaStreamException(e) from e

            # Otherwise, it's a recoverable error; we can attempt to reconnect.
            raise RecoverableMediaStreamException(e) from e
        except httpx.ReadTimeout as e:
            logger.exception(
                self._build_log_message(f"Stream operation timed out whilst reading")
            )

            # Reading from the stream timed out. This is likely a recoverable error;
            # we can attempt to reconnect.
            raise RecoverableMediaStreamException(e) from e
        except httpx.PoolTimeout as e:
            logger.exception(
                self._build_log_message(
                    f"Stream operation timed out whilst acquiring a connection"
                )
            )

            # This is likely a fatal error; we couldn't get a connection from the pool.
            raise FatalMediaStreamException(e) from e
        except StopAsyncIteration as e:
            logger.debug(self._build_log_message("Stream exhausted"))

            # This indicates the stream iterator has hit the end (likely EOF).
            # This is a fatal error; the stream cannot be read further.
            raise FatalMediaStreamException(e) from e
        except Exception as e:
            logger.error(
                self._build_log_message(
                    f"{e.__class__.__name__} occurred while managing stream connection: {e}"
                )
            )

            raise FatalMediaStreamException(e) from e
        finally:
            await self.close()

    async def run(self) -> None:
        async with self.stream_lifecycle():
            async with trio_util.move_on_when(
                lambda: self.is_killed.wait_value(True),
            ):
                position = self.config.header_size

                attempt_count = 0
                max_attempts = 4

                while True:
                    try:
                        async with self.manage_connection(
                            position=position
                        ) as connection:
                            # Reset attempt count on successful connection
                            attempt_count = 0

                            async with trio_util.move_on_when(
                                lambda connection=connection: trio_util.wait_any(
                                    lambda: connection.seek_required.wait_value(True),
                                )
                            ):
                                async for (
                                    read
                                ) in self.recent_reads.current_read.eventual_values(
                                    lambda v: v is not None
                                    and v.read_type == "body_read"
                                ):
                                    if not read:
                                        # This shouldn't happen; only needed for type checking
                                        logger.debug(
                                            self._build_log_message(
                                                "No read available, continuing"
                                            )
                                        )

                                        raise ValueError(
                                            self._build_log_message("No read available")
                                        )

                                    logger.debug(f"received read: {read}")

                                    uncached_chunks = OrderedSet(
                                        [
                                            chunk
                                            for chunk in read.chunk_range.chunks
                                            if not chunk.is_cached.value
                                        ]
                                    )

                                    logger.debug(f"uncached_chunks: {uncached_chunks}")

                                    if len(uncached_chunks) == 0:
                                        continue

                                    request_start, _ = read.chunk_range.request_range

                                    if (
                                        self.config.header_size
                                        < uncached_chunks[0].start
                                        < connection.start_position
                                    ):
                                        # Backward seek detection:
                                        #
                                        # If the requested start is before the start of the stream, we will always need to seek.
                                        # This is because streams can only read forwards, so a new connection must be made.

                                        logger.log(
                                            "STREAM",
                                            self._build_log_message(
                                                f"Requested start {request_start} "
                                                f"is before current read position {connection.current_read_position} "
                                                f"for {self.file_metadata['path']}. "
                                                f"Seeking to new start position {uncached_chunks[0].start}/{self.file_metadata['file_size']}."
                                            ),
                                        )

                                        connection.seek(
                                            position=uncached_chunks[0].start
                                        )

                                    if (
                                        connection.current_read_position
                                        < uncached_chunks[0].start
                                    ):
                                        # Forward seek detection:
                                        #
                                        # If the requested start is after the current read position, we need to seek forward.
                                        # This is because streams cannot skip chunks of data, so a new connection must be made,
                                        # to avoid requesting data that will be discarded and using unnecessary bandwidth.

                                        logger.log(
                                            "STREAM",
                                            self._build_log_message(
                                                f"Requested start {request_start} "
                                                f"is after current read position {connection.current_read_position} "
                                                f"for {self.file_metadata['path']}. "
                                                f"Seeking to new start position {uncached_chunks[0].start}/{self.file_metadata['file_size']}."
                                            ),
                                        )

                                        connection.seek(
                                            position=uncached_chunks[0].start
                                        )

                                    start_read_position = (
                                        connection.current_read_position
                                    )

                                    with benchmark(
                                        log=lambda duration, connection=connection: logger.log(
                                            "STREAM",
                                            self._build_log_message(
                                                f"Stream fetched {start_read_position}-{connection.current_read_position} "
                                                f"({connection.current_read_position - start_read_position} bytes) "
                                                f"in {duration}s."
                                            ),
                                        )
                                    ):
                                        for chunk in uncached_chunks:
                                            logger.debug(f"processing chunk: {chunk}")

                                            chunk_label = f"[{chunk.start}-{chunk.end}]"

                                            with benchmark(
                                                log=lambda duration: logger.log(
                                                    "STREAM",
                                                    self._build_log_message(
                                                        f"Fetching bytes {chunk_label} took {duration}s"
                                                    ),
                                                )
                                            ):
                                                data = await anext(connection.reader)

                                            with benchmark(
                                                log=lambda duration: logger.log(
                                                    "STREAM",
                                                    self._build_log_message(
                                                        f"Processing bytes {chunk_label} took {duration}s"
                                                    ),
                                                )
                                            ):
                                                connection.increment_sequential_chunks()

                                                await self._cache_chunk(
                                                    start=chunk.start,
                                                    data=data,
                                                )

                                                chunk.emit_cache_signal()

                                                connection.current_read_position += len(
                                                    data
                                                )

                                                self.session_statistics.bytes_transferred += len(
                                                    data
                                                )

                            position = connection.current_read_position
                    except RecoverableMediaStreamException as e:
                        logger.warning(
                            self._build_log_message(
                                f"Recoverable error in stream loop: {e.original_exception}. Attempting to reconnect..."
                            )
                        )

                        should_retry = await self._retry_with_backoff(
                            attempt=attempt_count,
                            max_attempts=max_attempts,
                            backoffs=[0.2, 0.5, 1.0],
                        )

                        if should_retry:
                            attempt_count += 1

                            continue
                        else:
                            self._stream_error.value = e.original_exception

                            break
                    except FatalMediaStreamException as e:
                        logger.error(
                            self._build_log_message(
                                f"Fatal error in stream loop: {e.original_exception}. Terminating stream."
                            )
                        )

                        self._stream_error.value = e.original_exception

                        break
                    except Exception as e:
                        logger.debug(f"Unexpected error in stream loop: {e}")

                        self._stream_error.value = e

                        break

    async def connect(self, *, position: int) -> StreamConnection:
        """Establish a streaming connection starting at the given byte offset, aligned to the closest chunk."""

        chunk_aligned_start = max(
            self.config.header_size,
            self.chunker.get_chunk_range(position=position).first_chunk.start,
        )

        response = await self._prepare_response(start=chunk_aligned_start)

        stream_connection = StreamConnection(
            response=response,
            start_position=chunk_aligned_start,
            current_read_position=chunk_aligned_start,
            reader=response.aiter_bytes(chunk_size=self.config.chunk_size),
        )

        logger.log(
            "STREAM",
            self._build_log_message(
                f"{response.http_version} stream connection established "
                f"from byte {chunk_aligned_start} / {self.file_metadata['file_size']}."
            ),
        )

        return stream_connection

    async def close(self) -> None:
        """Close the active stream."""

        if not self.connection:
            return

        await self.connection.close()

        self.connection = None

        logger.log(
            "STREAM",
            self._build_log_message(
                f"Ended stream for {self.file_metadata['path']} fh={self.fh} "
                f"after transferring {self.session_statistics.bytes_transferred / (1024 * 1024):.2f}MB "
                f"in {self.session_statistics.total_session_connections} connections."
            ),
        )

    async def kill(self) -> None:
        """Immediately terminate the active stream."""

        # First wait for the stream to stop, then close the client
        if self.is_streaming.value:
            # If the file was streaming,
            # clear all chunk cache emitters to free up memory.
            di[ChunkCacheNotifier].clear_emitters(
                cache_key=self.file_metadata["original_filename"]
            )

            # Wait for the stream loop to close
            try:
                with trio.fail_after(5):
                    self.is_killed.value = True
                    await self.is_streaming.wait_value(False)
            except trio.TooSlowError:
                logger.warning(
                    self._build_log_message(
                        "Stream didn't stop within 5 seconds, forcing close"
                    )
                )

    async def scan(self, read_position: int, size: int) -> bytes:
        """Fetch extra, ephemeral data for scanning purposes."""

        data = await self._fetch_discrete_byte_range(
            start=read_position,
            size=size,
            should_cache=False,
        )

        return data[:size]

    async def scan_header(self, read_position: int, size: int) -> bytes:
        """Scans the start of the media file for header data."""

        data = await self._fetch_discrete_byte_range(
            start=self.chunker.header_chunk.start,
            size=self.chunker.header_chunk.size,
        )

        self.chunker.header_chunk.emit_cache_signal()

        return data[read_position : read_position + size]

    async def scan_footer(self, read_position: int, size: int) -> bytes:
        """
        Scans the end of the media file for footer data.

        This "over-fetches" for the individual request,
        but multiple footer requests tend to be made to retrieve more data later,
        so this is more efficient than making multiple small requests.
        """

        footer_chunk = self.chunker.footer_chunk

        data = await self._fetch_discrete_byte_range(
            start=footer_chunk.start,
            size=footer_chunk.size,
        )

        self.chunker.footer_chunk.emit_cache_signal()

        slice_offset = read_position - footer_chunk.start

        return data[slice_offset : slice_offset + size]

    @asynccontextmanager
    async def capture_stream_errors(self) -> AsyncIterator[None]:
        """Context manager to capture and log stream errors."""

        try:
            yield
        finally:
            if self._stream_error.value:
                raise self._stream_error.value from None

    @asynccontextmanager
    async def read_lifecycle(self, chunk_range: ChunkRange) -> AsyncIterator[ReadType]:
        """Context manager for managing read lifecycle."""

        read_type: ReadType | None = None

        try:
            request_start, request_end = chunk_range.request_range
            request_size = chunk_range.size

            logger.log(
                "STREAM",
                self._build_log_message(
                    "Read request: "
                    f"request_start={request_start} "
                    f"request_end={request_end} "
                    f"size={request_size}"
                ),
            )

            read_type = await self._detect_read_type(
                chunk_range=chunk_range,
            )

            self.recent_reads.current_read.value = Read(
                chunk_range=chunk_range,
                read_type=read_type,
            )

            yield read_type
        finally:
            self.recent_reads.previous_read.value = Read(
                chunk_range=chunk_range,
                read_type=read_type or "unknown",
            )

            try:
                current_read_position = (
                    self.connection.current_read_position if self.connection else None
                )
            except AttributeError:
                current_read_position = None

            try:
                sequential_chunk_fetches = (
                    self.connection.sequential_chunks_fetched
                    if self.connection
                    else None
                )
            except AttributeError:
                sequential_chunk_fetches = None

            logger.log(
                "STREAM",
                self._build_log_message(
                    f"sequential_chunk_fetches={sequential_chunk_fetches} "
                    f"current_read_position={current_read_position} "
                    f"last_read_end={self.recent_reads.last_read_end} "
                ),
            )

    async def read(
        self,
        *,
        request_start: int,
        request_end: int,
        request_size: int,
    ) -> bytes:
        """Handles incoming read requests from the VFS."""

        read_range = self.chunker.get_chunk_range(
            position=request_start,
            size=request_size,
        )

        async with self.capture_stream_errors():
            async with self.read_lifecycle(chunk_range=read_range) as read_type:
                logger.log(
                    "STREAM",
                    self._build_log_message(
                        f"Performing {read_type} for [{request_start}-{request_end}]"
                    ),
                )

                match read_type:
                    case "cache_hit":
                        return await self._read_cache(
                            start=request_start,
                            end=request_end,
                        )
                    case "header_scan":
                        return await self.scan_header(
                            read_position=request_start,
                            size=request_size,
                        )
                    case "footer_scan":
                        return await self.scan_footer(
                            read_position=request_start,
                            size=request_size,
                        )
                    case "general_scan":
                        return await self.scan(
                            read_position=request_start,
                            size=request_size,
                        )
                    case "body_read":
                        return await self.read_bytes(chunk_range=read_range)
                    case "footer_read":
                        raise RuntimeError(
                            "Tried to read footer but should have been cached"
                        )
                    case _:
                        # This should never happen due to prior validation
                        raise RuntimeError("Unknown read type")

    async def read_bytes(
        self,
        chunk_range: ChunkRange,
    ) -> bytes:
        """Read a specific number of bytes from the stream."""

        start, end = chunk_range.request_range

        await self._wait_until_chunks_ready(chunk_range=chunk_range)

        cached_data = await self._read_cache(
            start=start,
            end=end,
        )

        if cached_data:
            logger.log(
                "STREAM",
                self._build_log_message(
                    f"Found data {start}-{end} ({len(cached_data)} bytes) from cache."
                ),
            )

            return cached_data

        raise CacheDataNotFoundException(range=chunk_range.request_range)

    async def _detect_read_type(
        self,
        *,
        chunk_range: ChunkRange,
    ) -> ReadType:
        start, end = chunk_range.request_range
        size = chunk_range.size

        # First, attempt to detect if the requested range is already cached.
        # This uses a lightweight check, that just checks for existence,
        # rather than reading the actual data.
        is_request_fully_cached = await trio.to_thread.run_sync(
            lambda: self._check_cache(
                start=chunk_range.first_chunk.start,  # Align to start of chunk for cache check
                end=end,
            )
        )

        if is_request_fully_cached:
            return "cache_hit"

        if start < end <= self.config.header_size:
            return "header_scan"

        file_size = self.file_metadata["file_size"]

        if (
            (self.recent_reads.last_read_end or 0)
            < start - self.config.sequential_read_tolerance
        ) and file_size - self.footer_size <= start <= file_size:
            return "footer_scan"

        if (
            self.recent_reads.last_read_end
            and (
                # This behaviour is seen during scanning
                # and captures large jumps in read position
                # generally observed when the player is reading the footer
                # for cues or metadata after initial playback start.
                #
                # Scans typically read less than a single block.
                abs(self.recent_reads.last_read_end - start)
                > self.config.scan_tolerance
                and start != self.config.header_size
                and size < self.config.block_size
            )
            or (
                # This behaviour is seen when seeking.
                # Playback has already begun, so the header has been served
                # for this file, but the scan happens on a new file handle
                # and is the first request to be made.
                start > self.config.header_size
                and self.recent_reads.last_read_end == 0
            )
        ):
            return "general_scan"

        if start < self.file_metadata["file_size"] - self.footer_size:
            return "body_read"

        return "footer_read"

    async def _fetch_discrete_byte_range(
        self,
        start: int,
        size: int,
        should_cache: bool = True,
    ) -> bytes:
        """
        Fetch a discrete range of data outside of the main stream.

        Used for fetching the header, footer, and one-off scans.
        """

        if start < 0:
            raise ValueError("Start must be non-negative")

        if size <= 0:
            raise ValueError("Size must be positive")

        response = await self._prepare_response(
            start,
            end=start + size - 1,
        )

        data = b""

        async for chunk in response.aiter_bytes(
            chunk_size=min(size, self.config.chunk_size)
        ):
            data += chunk

            if len(data) >= size:
                break

        self.session_statistics.bytes_transferred += len(data)

        verified_data = self._verify_scan_integrity((start, start + size), data)

        if should_cache:
            await self._cache_chunk(
                start=start,
                data=verified_data[:size],
            )

        return verified_data

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

        from program.services.filesystem.vfs import VFSDatabase

        max_preflight_attempts = 4
        backoffs = [0.2, 0.5, 1.0]

        # Only fetch URL from DB if not already provided during initialization
        if not hasattr(self, "target_url") or not self.target_url:
            # Get entry info from DB
            # Only unrestrict if there's no unrestricted URL already (force_resolve=False)
            # Let the refresh logic handle re-unrestricting on failures
            entry_info = await trio.to_thread.run_sync(
                lambda: di[VFSDatabase].get_entry_by_original_filename(
                    self.file_metadata["original_filename"],
                    True,  # for_http (use unrestricted URL if available)
                    False,  # force_resolve (don't unrestrict if already have unrestricted URL)
                )
            )

            if not entry_info:
                logger.error(
                    self._build_log_message(
                        f"No entry info for {self.file_metadata['original_filename']}"
                    )
                )

                raise pyfuse3.FUSEError(errno.ENOENT)

            self.target_url = entry_info["url"]

        if not self.target_url:
            logger.error(
                self._build_log_message(
                    f"No URL for {self.file_metadata['original_filename']}"
                )
            )

            raise pyfuse3.FUSEError(errno.ENOENT)

        for preflight_attempt in range(max_preflight_attempts):
            try:
                async with self.async_client.stream(
                    method="GET",
                    url=self.target_url,
                    headers=headers,
                    follow_redirects=True,
                ) as preflight_response:
                    preflight_response.raise_for_status()

                    preflight_status_code = preflight_response.status_code

                    if preflight_status_code == HTTPStatus.PARTIAL_CONTENT:
                        # Preflight passed, proceed to actual request
                        return
                    elif preflight_status_code == HTTPStatus.OK:
                        # Server refused range request. Serving this request would return the full media file,
                        # which eats downloader bandwidth usage unnecessarily. Wait and retry.
                        logger.warning(
                            self._build_log_message(
                                f"Server doesn't support range requests yet."
                            )
                        )

                        if await self._retry_with_backoff(
                            preflight_attempt, max_preflight_attempts, backoffs
                        ):
                            continue

                        # Unable to get range support after retries
                        raise pyfuse3.FUSEError(errno.EIO)
            except httpx.RemoteProtocolError as e:
                logger.debug(
                    self._build_log_message(
                        f"HTTP protocol error (attempt {preflight_attempt + 1}/{max_preflight_attempts}): {e}"
                    )
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
                    self._build_log_message(
                        f"Preflight HTTP error {preflight_status_code}: {e}"
                    )
                )

                if preflight_status_code in (HTTPStatus.NOT_FOUND, HTTPStatus.GONE):
                    # File can't be found at this URL; try refreshing the URL once
                    if preflight_attempt == 0:
                        fresh_url = await trio.to_thread.run_sync(
                            self._refresh_download_url
                        )

                        if fresh_url:
                            logger.warning(
                                self._build_log_message(
                                    f"URL refresh after HTTP {preflight_status_code}"
                                )
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
                        self._build_log_message(
                            f"Unexpected preflight HTTP {preflight_status_code}"
                        )
                    )
                    raise pyfuse3.FUSEError(errno.EIO) from e
            except (httpx.TimeoutException, httpx.ConnectError, httpx.InvalidURL) as e:
                logger.debug(
                    self._build_log_message(
                        f"HTTP request failed (attempt {preflight_attempt + 1}/{max_preflight_attempts}): {e}"
                    )
                )

                if preflight_attempt == 0:
                    # On first exception, try refreshing the URL in case it's a connectivity issue
                    fresh_url = await trio.to_thread.run_sync(
                        self._refresh_download_url
                    )

                    if fresh_url:
                        logger.warning(
                            self._build_log_message("URL refresh after timeout")
                        )

                if await self._retry_with_backoff(
                    preflight_attempt, max_preflight_attempts, backoffs
                ):
                    continue

                raise pyfuse3.FUSEError(errno.EIO) from e
            except pyfuse3.FUSEError:
                raise
            except Exception as e:
                logger.exception(
                    self._build_log_message(
                        f"Unexpected error during preflight checks: {e}"
                    )
                )

                if await self._retry_with_backoff(
                    preflight_attempt,
                    max_preflight_attempts,
                    backoffs,
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
            logger.error(self._build_log_message(f"Preflight checks failed: {e}"))

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
                        self._build_log_message(
                            f"Server returned full content instead of range."
                        )
                    )
                    raise pyfuse3.FUSEError(errno.EIO)

                self.session_statistics.total_session_connections += 1

                return response
            except httpx.HTTPStatusError as e:
                status_code = e.response.status_code

                if status_code == HTTPStatus.FORBIDDEN:
                    # Forbidden - could be rate limiting or auth issue, don't refresh URL
                    logger.debug(
                        self._build_log_message(
                            f"HTTP 403 Forbidden - attempt {attempt + 1}"
                        )
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
                        self._build_log_message(
                            f"HTTP 429 Rate Limited - attempt {attempt + 1}"
                        )
                    )

                    if await self._retry_with_backoff(attempt, max_attempts, backoffs):
                        continue

                    raise pyfuse3.FUSEError(errno.EAGAIN) from e
                else:
                    # Other unexpected status codes
                    logger.warning(
                        self._build_log_message(f"Unexpected HTTP {status_code}")
                    )
                    raise pyfuse3.FUSEError(errno.EIO) from e
            except (
                httpx.TimeoutException,
                httpx.ConnectError,
                httpx.InvalidURL,
            ) as e:
                logger.debug(
                    self._build_log_message(
                        f"HTTP request failed (attempt {attempt + 1}/{max_attempts}): {e}"
                    )
                )

                if attempt == 0:
                    # On first exception, try refreshing the URL in case it's a connectivity issue
                    fresh_url = await trio.to_thread.run_sync(
                        self._refresh_download_url
                    )

                    if fresh_url:
                        logger.warning(
                            self._build_log_message(f"URL refresh after timeout")
                        )

                if await self._retry_with_backoff(attempt, max_attempts, backoffs):
                    continue

                raise pyfuse3.FUSEError(errno.EIO) from e
            except httpx.RemoteProtocolError as e:
                # This can happen if the server closes the connection prematurely
                logger.debug(
                    self._build_log_message(
                        f"HTTP protocol error (attempt {attempt + 1}/{max_attempts}): {e}"
                    )
                )

                if await self._retry_with_backoff(attempt, max_attempts, backoffs):
                    continue

                raise pyfuse3.FUSEError(errno.EIO) from e
            except pyfuse3.FUSEError:
                raise
            except Exception:
                logger.exception(
                    self._build_log_message(f"Unexpected error connecting to stream")
                )
                raise pyfuse3.FUSEError(errno.EIO) from None

        raise pyfuse3.FUSEError(errno.EIO)

    async def _wait_until_chunks_ready(
        self,
        *,
        chunk_range: ChunkRange,
    ) -> None:
        """Wait until all the given chunks are cached."""

        start, end = chunk_range.request_range

        try:
            with trio.fail_after(self.config.chunk_wait_timeout_seconds):
                await trio_util.wait_all(
                    *[
                        lambda: chunk.is_cached.wait_value(True)
                        for chunk in chunk_range.chunks
                    ]
                )

            logger.log(
                "STREAM",
                self._build_log_message(
                    f"Found cache, attempting to read {start}-{end}"
                ),
            )
        except* trio.TooSlowError:
            raise ChunksTooSlowException(
                threshold=self.config.chunk_wait_timeout_seconds,
                chunk_range=chunk_range,
            ) from None

    def _check_cache(self, *, start: int, end: int) -> bool:
        """Check if the given byte range is fully cached."""

        from .cache import Cache

        return di[Cache].has(
            cache_key=self.file_metadata["original_filename"],
            start=start,
            end=end,
        )

    async def _read_cache(
        self,
        *,
        start: int,
        end: int,
    ) -> bytes:
        """Fetch the given byte range from the cache, if it exists."""

        from .cache import Cache

        return await di[Cache].get(
            cache_key=self.file_metadata["original_filename"],
            start=start,
            end=end,
        )

    async def _cache_chunk(
        self,
        *,
        start: int,
        data: bytes,
    ) -> None:
        """Cache the given chunk of data."""

        from .cache import Cache

        await di[Cache].put(
            cache_key=self.file_metadata["original_filename"],
            start=start,
            data=data,
        )

    def _refresh_download_url(self) -> bool:
        """
        Refresh download URL by unrestricting from provider.

        Updates the database with the fresh URL.

        Returns:
            True if successfully refreshed, False otherwise
        """

        from program.services.filesystem.vfs import VFSDatabase

        # Query database by original_filename and force unrestrict
        entry_info = di[VFSDatabase].get_entry_by_original_filename(
            original_filename=self.file_metadata["original_filename"],
            for_http=True,
            force_resolve=True,
        )

        if entry_info:
            fresh_url = entry_info.get("url")

            if fresh_url and fresh_url != self.target_url:
                logger.debug(
                    self._build_log_message(
                        f"Refreshed URL for {self.file_metadata['original_filename']}"
                    )
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
    ) -> bytes:
        """
        Verify the integrity of the data read from the stream for scanning purposes.

        Args:
            range: The byte range that was requested
            data: The data read from the stream
        """

        if data == b"":
            raise EmptyDataException(range=range)

        start, end = range
        expected_length = end - start
        actual_length = len(data)

        if actual_length < expected_length:
            raise ByteLengthMismatchException(
                expected_length=expected_length,
                actual_length=actual_length,
                range=range,
            )

        return data

    def _build_log_message(self, message: str) -> str:
        return f"{message} [fh: {self.fh} file={self.file_metadata['path'].split('/')[-1]}]"
