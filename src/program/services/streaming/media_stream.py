import trio
import trio_util
import pyfuse3
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
from program.utils.async_client import AsyncClient
from program.utils.proxy_client import ProxyClient

from .chunker import Chunk, ChunkCacheNotifier, ChunkRange, Chunker
from .config import Config
from .exceptions import (
    CacheDataNotFoundException,
    ChunksTooSlowException,
    EmptyDataException,
    FatalMediaStreamException,
    ByteLengthMismatchException,
    RecoverableMediaStreamException,
    DebridServiceClosedConnectionException,
    DebridServiceException,
    DebridServiceForbiddenException,
    DebridServiceRangeNotSatisfiableException,
    DebridServiceUnableToConnectException,
    DebridServiceRateLimitedException,
    DebridServiceRefusedRangeRequestException,
    MediaStreamKilledException,
    DebridServiceLinkUnavailable,
)
from .file_metadata import FileMetadata
from .recent_reads import Read, RecentReads
from .session_statistics import SessionStatistics
from .stream_connection import StreamConnection


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


class MediaStream:
    """
    Represents an active streaming session for a file.

    This class manages the streaming of media content, including handling
    connections, fetching data, and managing playback.
    """

    def __init__(
        self,
        *,
        fh: pyfuse3.FileHandleT,
        file_size: int,
        path: str,
        original_filename: str,
        nursery: trio.Nursery,
        provider: str,
        initial_url: str,
    ) -> None:
        fs = settings_manager.settings.filesystem

        self.fh = fh
        self.nursery = nursery
        self.provider = provider
        self.recent_reads: RecentReads = RecentReads()
        self.is_streaming: trio_util.AsyncBool = trio_util.AsyncBool(False)
        self.is_killed: trio_util.AsyncBool = trio_util.AsyncBool(False)
        self._stream_error: trio_util.AsyncValue[Exception | None] = (
            trio_util.AsyncValue(None)
        )

        # Store initial URL to avoid redundant unrestrict calls
        self.target_url: trio_util.AsyncValue[str] = trio_util.AsyncValue(initial_url)

        self.config = Config()

        self.session_statistics = SessionStatistics()

        self.file_metadata = FileMetadata(
            file_size=file_size,
            path=path,
            original_filename=original_filename,
        )

        self.chunker = Chunker(
            cache_key=self.file_metadata.original_filename,
            chunk_size=self.config.chunk_size,
            header_size=self.config.header_size,
            footer_size=self.footer_size,
            file_size=file_size,
        )

        logger.log(
            "STREAM",
            self._build_log_message(
                f"Initialized stream with chunk size {self.config.chunk_size / (1024 * 1024):.2f} MB. "
                f"file_size={self.file_metadata.file_size} bytes",
            ),
        )

        # Validate cache size
        # Cache needs to hold 10 chunks (10MiB) to avoid thrashing with concurrent reads
        min_cache_mb = (self.config.chunk_size * 10) // (1024 * 1024)

        if fs.cache_max_size_mb < min_cache_mb:
            logger.warning(
                f"Cache size ({fs.cache_max_size_mb}MB) is too small. "
                f"Minimum recommended: {min_cache_mb}MB. "
                "Cache thrashing may occur with concurrent reads, causing poor performance."
            )

        # Use proxy client if provider requires it
        if (
            provider in PROXY_REQUIRED_PROVIDERS
            and settings_manager.settings.downloaders.proxy_url
        ):
            self.async_client = di[ProxyClient]
        else:
            self.async_client = di[AsyncClient]

    @cached_property
    def footer_size(self) -> int:
        """An optimal footer size for scanning based on file size."""

        # Use a percentage-based approach for requesting the footer
        # using the file size to determine an appropriate range.

        min_footer_size = 1024 * 16  # Minimum footer size of 16KB
        max_footer_size = 10 * 1024 * 1024  # Maximum footer size of 10MB
        footer_percentage = 0.002  # 0.2% of file size

        percentage_size = int(self.file_metadata.file_size * footer_percentage)

        raw_footer_size = min(max(percentage_size, min_footer_size), max_footer_size)
        aligned_footer_size = (
            -(raw_footer_size // -self.config.block_size) * self.config.block_size
        )

        return aligned_footer_size

    @property
    def is_timed_out(self) -> bool:
        timeout_seconds = 60

        if not self.recent_reads.current_read.value:
            return False

        return (
            trio.current_time() - self.recent_reads.current_read.value.timestamp
            > timeout_seconds
        )

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

            logger.log(
                "STREAM",
                self._build_log_message("Stream lifecycle ended"),
            )

    @asynccontextmanager
    async def manage_connection(
        self,
        *,
        position: int,
    ) -> AsyncIterator[StreamConnection]:
        """Context manager to handle connection lifecycle."""

        try:
            async with self.connect(position=position) as connection:
                yield connection
        except (
            EmptyDataException,
            DebridServiceRateLimitedException,
            DebridServiceRefusedRangeRequestException,
            DebridServiceClosedConnectionException,
        ) as e:
            logger.exception(
                self._build_log_message(
                    f"{e.__class__.__name__} occurred whilst managing stream connection: {e}"
                )
            )

            raise RecoverableMediaStreamException(e) from e
        except (
            DebridServiceUnableToConnectException,
            DebridServiceForbiddenException,
            DebridServiceRangeNotSatisfiableException,
        ) as e:
            logger.exception(
                self._build_log_message(
                    f"{e.__class__.__name__} occurred whilst managing stream connection: {e}"
                )
            )

            raise FatalMediaStreamException(e) from e

    async def run(
        self,
        position: int,
        *,
        task_status=trio.TASK_STATUS_IGNORED,
    ) -> None:
        has_started = False

        async with self.stream_lifecycle():
            async with trio_util.move_on_when(lambda: self.is_killed.wait_value(True)):
                attempt_count = 0
                max_attempts = 4

                seek_range: ChunkRange | None = None

                while True:
                    try:
                        async with self.manage_connection(
                            position=position
                        ) as connection:
                            if not has_started:
                                task_status.started()
                                has_started = True

                            # Reset attempt count on successful connection
                            attempt_count = 0

                            async with trio_util.move_on_when(
                                lambda connection=connection: trio_util.wait_any(
                                    # Reconnect the stream if a seek is requested
                                    lambda: connection.seek_required.wait_value(True),
                                    # Reconnect the stream if the target URL has been updated
                                    # by another request (e.g. a scan that refreshed the URL).
                                    lambda: self.target_url.wait_value(
                                        lambda url: (
                                            url != connection.response.request.url
                                        )
                                    ),
                                )
                            ):

                                async def _process_chunks(
                                    chunks: OrderedSet[Chunk],
                                ) -> None:
                                    if len(chunks) == 0:
                                        logger.log(
                                            "STREAM",
                                            self._build_log_message(
                                                "Received no chunks to process; skipping."
                                            ),
                                        )

                                        return

                                    logger.log(
                                        "STREAM",
                                        self._build_log_message(
                                            f"Received chunks to process: {chunks}"
                                        ),
                                    )

                                    chunk_range_label = (
                                        f"{chunks[0].index}"
                                        if len(chunks) == 1
                                        else f"{chunks[0].index}-{chunks[-1].index}"
                                    )

                                    start_read_position = (
                                        connection.current_read_position
                                    )

                                    with benchmark(
                                        log=lambda duration, conn=connection, start=start_read_position: logger.log(
                                            "STREAM",
                                            self._build_log_message(
                                                f"Stream fetched {start}-{conn.current_read_position} "
                                                f"({conn.current_read_position - start} bytes) "
                                                f"in {duration}s."
                                            ),
                                        )
                                    ):
                                        for chunk in chunks:
                                            chunk_label = f"[{chunk.start}-{chunk.end}]"

                                            with benchmark(
                                                log=lambda duration, c=chunk: logger.log(
                                                    "STREAM",
                                                    self._build_log_message(
                                                        f"Fetching {c} took {duration}s"
                                                    ),
                                                )
                                            ):
                                                data = await anext(connection.reader)

                                            if data == b"":
                                                raise EmptyDataException(
                                                    range=(chunk.start, chunk.end)
                                                )

                                            with benchmark(
                                                log=lambda duration, label=chunk_label, range_label=chunk_range_label: logger.log(
                                                    "STREAM",
                                                    self._build_log_message(
                                                        f"Processing chunk(s) #{range_label} {label} took {duration}s"
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

                                if seek_range:
                                    await _process_chunks(seek_range.uncached_chunks)
                                    seek_range = None

                                async for (
                                    read
                                ) in self.recent_reads.current_read.eventual_values(
                                    lambda v: (
                                        v is not None and v.read_type == "body_read"
                                    )
                                ):
                                    if not read:
                                        raise ValueError(
                                            self._build_log_message("No read available")
                                        )

                                    uncached_chunks = read.chunk_range.uncached_chunks

                                    if len(uncached_chunks) == 0:
                                        continue

                                    logger.log(
                                        "STREAM",
                                        self._build_log_message(
                                            f"Received read event: {read} with uncached_chunks {uncached_chunks}"
                                        ),
                                    )

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
                                                f"for {self.file_metadata.path}. "
                                                f"Seeking to new start position {uncached_chunks[0].start}/{self.file_metadata.file_size}."
                                            ),
                                        )

                                        connection.seek(chunk_range=read.chunk_range)

                                        break

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
                                                f"Request chunk start {uncached_chunks[0].start} "
                                                f"is after current read position {connection.current_read_position} "
                                                f"for {self.file_metadata.path}. "
                                                f"Seeking to new start position {uncached_chunks[0].start}/{self.file_metadata.file_size}."
                                            ),
                                        )

                                        connection.seek(chunk_range=read.chunk_range)

                                        break

                                    await _process_chunks(uncached_chunks)

                            position = connection.current_read_position
                            seek_range = connection.seek_range
                    except RecoverableMediaStreamException as e:
                        logger.warning(
                            self._build_log_message(
                                f"Recoverable error from stream: {e.original_exception}. Attempting to reconnect..."
                            )
                        )

                        should_retry = await self._retry_with_backoff(
                            attempt_count,
                            max_attempts,
                            [0.2, 0.5, 1.0],
                        )

                        if should_retry:
                            attempt_count += 1

                            continue
                        else:
                            self._stream_error.value = e.original_exception

                            break
                    except FatalMediaStreamException as e:
                        logger.exception(
                            self._build_log_message(
                                f"Fatal error from stream: {e.original_exception}. Terminating."
                            )
                        )

                        self._stream_error.value = e.original_exception

                        break
                    except Exception as e:
                        # Safely catch any other unexpected exceptions to avoid crashing the FUSE mount
                        logger.exception(
                            self._build_log_message(
                                f"Unexpected error from stream: {e}"
                            )
                        )

                        self._stream_error.value = e

                        break

    @asynccontextmanager
    async def connect(self, *, position: int) -> AsyncGenerator[StreamConnection]:
        """Establish a streaming connection starting at the given byte offset, aligned to the closest chunk."""

        chunk_range = self.chunker.get_chunk_range(position=position)

        chunk_aligned_start = (
            chunk_range.uncached_chunks[0].start
            if len(chunk_range.uncached_chunks) > 0
            else max(self.config.header_size, chunk_range.first_chunk.start)
        )

        async with self.establish_connection(start=chunk_aligned_start) as response:
            stream_connection = StreamConnection(
                response=response,
                start_position=chunk_aligned_start,
                current_read_position=chunk_aligned_start,
                reader=response.aiter_raw(chunk_size=self.config.chunk_size),
            )

            logger.log(
                "STREAM",
                self._build_log_message(
                    f"{response.http_version} stream connection established "
                    f"from byte {chunk_aligned_start} / {self.file_metadata.file_size}."
                ),
            )

            yield stream_connection

    async def close(self) -> None:
        """Immediately terminate the active stream."""

        # First wait for the stream to stop, then close the client
        if self.is_streaming.value:
            # If the file was streaming,
            # clear all chunk cache emitters to free up memory.
            di[ChunkCacheNotifier].clear_emitters(
                cache_key=self.file_metadata.original_filename
            )

            # Wait for the stream loop to close
            try:
                with trio.fail_after(5):
                    self.is_killed.value = True
                    await self.is_streaming.wait_value(False)
            except trio.TooSlowError:
                logger.warning(
                    self._build_log_message("Stream didn't stop within 5 seconds")
                )

        logger.log(
            "STREAM",
            self._build_log_message(
                f"Ended stream for {self.file_metadata.path} fh={self.fh} "
                f"after transferring {self.session_statistics.bytes_transferred / (1024 * 1024):.2f}MB "
                f"in {self.session_statistics.total_session_connections} connections."
            ),
        )

    async def scan(self, read_position: int, size: int) -> bytes:
        """Fetch a one-off range of data for scanning purposes."""

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
        so this ends up being more efficient than making multiple small requests.
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

        # Handle the read request whilst monitoring for stream kill signals, and errors.
        # This allows us to gracefully handle stream termination and propagate errors,
        # even during the middle of a read operation.
        async with trio_util.move_on_when(
            lambda: trio_util.wait_any(
                lambda: self.is_killed.wait_value(True),
                lambda: self._stream_error.wait_value(lambda v: v is not None),
            )
        ):
            yield

        if self.is_killed.value:
            raise MediaStreamKilledException

        if self._stream_error.value:
            raise self._stream_error.value from None

    @asynccontextmanager
    async def read_lifecycle(self, chunk_range: ChunkRange) -> AsyncIterator[ReadType]:
        """Context manager for managing read lifecycle."""

        try:
            read_type = await self._detect_read_type(
                chunk_range=chunk_range,
            )

            # Start the stream and wait for a connection before progressing with a body read.
            # This MUST be done before assigning a value to current_read,
            # or else the stream will not receive the value.
            if read_type == "body_read" and not self.is_streaming.value:
                with trio.fail_after(10):
                    await self.nursery.start(self.run, chunk_range.position)

            self.recent_reads.current_read.value = Read(
                chunk_range=chunk_range,
                read_type=read_type,
            )

            yield read_type
        finally:
            self.recent_reads.previous_read.value = self.recent_reads.current_read.value

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
                    case "footer_scan" | "footer_read":
                        # Note: if the read type is footer_read, the footer cache chunk
                        # has likely expired and the player is nearing EOF.
                        # In this case, we will re-download the entire footer and serve the rest from cache.
                        #
                        # This can happen if the user's cache size is small,
                        # or during heavy scans with lots of competing streams.
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

        logger.log(
            "STREAM",
            self._build_log_message(f"Found cache, attempting to read {start}-{end}"),
        )

        cached_data = await self._read_cache(
            start=start,
            end=end,
        )

        if cached_data:
            logger.log(
                "STREAM",
                self._build_log_message(
                    f"Found data {start}-{end} ({len(cached_data)} bytes) from cache"
                ),
            )

            return cached_data

        raise CacheDataNotFoundException(range=chunk_range.request_range)

    @asynccontextmanager
    async def establish_connection(
        self,
        start: int,
        *,
        end: int | None = None,
    ) -> AsyncGenerator[httpx.Response]:
        """Establish a streaming connection starting at the given byte offset."""

        if settings_manager.settings.enable_network_tracing:

            async def trace_log(event_name, info):
                logger.log(
                    "NETWORK",
                    self._build_log_message(f"{event_name} - {info}"),
                )

            extensions = {"trace": trace_log}
        else:
            extensions = None

        headers = httpx.Headers(
            {
                "Accept-Encoding": "identity",
                "Connection": "keep-alive",
                "Range": f"bytes={start}-{end or ''}",
            }
        )

        max_attempts = 4
        backoffs = [0.2, 0.5, 1.0]

        for attempt in range(max_attempts):
            try:
                async with self.async_client.stream(
                    method="GET",
                    url=self.target_url.value,
                    headers=headers,
                    extensions=extensions,
                ) as stream:
                    content_length = stream.headers.get("Content-Length")

                    if end is not None:
                        range_bytes = end - start + 1
                    else:
                        range_bytes = self.file_metadata.file_size - start

                    if (
                        stream.status_code == HTTPStatus.OK
                        and content_length is not None
                        and int(content_length) > range_bytes
                    ):
                        # Server appears to be ignoring the range request and returning full content.
                        # This is incompatible with our stream, as it will start at the incorrect position.
                        logger.warning(
                            self._build_log_message(
                                "Server returned full content instead of range."
                            )
                        )

                        if await self._retry_with_backoff(
                            attempt,
                            max_attempts,
                            backoffs,
                        ):
                            continue

                        raise DebridServiceRefusedRangeRequestException(
                            provider=self.provider
                        )

                    self.session_statistics.total_session_connections += 1

                    yield stream

                    return
            except httpx.HTTPStatusError as e:
                status_code = e.response.status_code

                logger.warning(
                    self._build_log_message(f"HTTP error {status_code}: {e}")
                )

                if status_code == HTTPStatus.FORBIDDEN:
                    # Forbidden - could be rate limiting or auth issue, don't refresh URL
                    logger.warning(
                        self._build_log_message(
                            f"HTTP 403 Forbidden - attempt {attempt + 1}"
                        ),
                    )

                    if await self._retry_with_backoff(
                        attempt,
                        max_attempts,
                        backoffs,
                    ):
                        continue

                    raise DebridServiceForbiddenException(provider=self.provider) from e
                elif status_code in (HTTPStatus.NOT_FOUND, HTTPStatus.GONE):
                    # File can't be found at this URL; try refreshing the URL once
                    if attempt == 0:
                        fresh_url = await trio.to_thread.run_sync(
                            self._refresh_download_url
                        )

                        if fresh_url:
                            logger.warning(
                                self._build_log_message(
                                    f"URL refresh after HTTP {status_code}"
                                )
                            )

                            if await self._retry_with_backoff(
                                attempt,
                                max_attempts,
                                backoffs,
                            ):
                                continue

                    raise DebridServiceUnableToConnectException(
                        provider=self.provider
                    ) from e
                elif status_code == HTTPStatus.RANGE_NOT_SATISFIABLE:
                    # Requested range not satisfiable; handled as EOF
                    raise DebridServiceRangeNotSatisfiableException(
                        provider=self.provider
                    ) from e
                elif status_code == HTTPStatus.TOO_MANY_REQUESTS:
                    # Rate limited - back off exponentially, don't refresh URL
                    logger.warning(
                        self._build_log_message(
                            f"HTTP 429 Rate Limited - attempt {attempt + 1}"
                        )
                    )

                    if await self._retry_with_backoff(
                        attempt,
                        max_attempts,
                        backoffs,
                    ):
                        continue

                    raise DebridServiceRateLimitedException(
                        provider=self.provider
                    ) from e
                else:
                    # Other unexpected status codes
                    logger.warning(
                        self._build_log_message(f"Unexpected HTTP {status_code}")
                    )

                    raise DebridServiceException(
                        "Unexpected error connecting to stream",
                        provider=self.provider,
                    ) from e
            except (
                httpx.ConnectError,
                httpx.InvalidURL,
            ) as e:
                logger.warning(
                    f"Encountered {e.__class__.__name__}: {e} (attempt {attempt + 1}/{max_attempts})"
                )

                if attempt == 0:
                    # On first exception, try refreshing the URL in case it's a connectivity issue
                    fresh_url = await trio.to_thread.run_sync(
                        self._refresh_download_url
                    )

                    if fresh_url:
                        logger.warning(
                            self._build_log_message("URL refresh after timeout")
                        )

                if await self._retry_with_backoff(
                    attempt,
                    max_attempts,
                    backoffs,
                ):
                    continue

                raise DebridServiceUnableToConnectException(
                    provider=self.provider
                ) from e
            except (httpx.RemoteProtocolError, httpx.TimeoutException) as e:
                # This can happen if the server closes the connection prematurely
                logger.warning(
                    self._build_log_message(
                        f"{e.__class__.__name__} error (attempt {attempt + 1}/{max_attempts}): {e}"
                    ),
                )

                if isinstance(e, httpx.PoolTimeout):
                    # Pool timeout indicates all connections are in use
                    logger.warning(
                        self._build_log_message(
                            f"All connections are in use: {self.async_client._transport._pool}"  # type: ignore
                        )
                    )

                if await self._retry_with_backoff(
                    attempt,
                    max_attempts,
                    backoffs,
                ):
                    continue

                raise DebridServiceClosedConnectionException(
                    provider=self.provider
                ) from e
            except DebridServiceLinkUnavailable:
                raise
            except Exception as e:
                logger.exception(
                    self._build_log_message("Unexpected error connecting to stream")
                )

                raise DebridServiceException(
                    "Unexpected error connecting to stream",
                    provider=self.provider,
                ) from e

        raise DebridServiceException(
            "Unexpected error connecting to stream",
            provider=self.provider,
        )

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

        file_size = self.file_metadata.file_size

        if (
            (self.recent_reads.last_read_end or 0)
            < start - self.config.sequential_read_tolerance
        ) and file_size - self.footer_size <= start <= file_size:
            return "footer_scan"

        if self.recent_reads.last_read_end and (
            (
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

        if start < self.file_metadata.file_size - self.footer_size:
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

        async with self.establish_connection(
            start=start,
            end=start + size - 1,
        ) as response:
            data = await response.aread()

            self.session_statistics.bytes_transferred += len(data)

            verified_data = self._verify_scan_integrity((start, start + size), data)

            if should_cache:
                await self._cache_chunk(
                    start=start,
                    data=verified_data[:size],
                )

            return verified_data

    async def _wait_until_chunks_ready(
        self,
        *,
        chunk_range: ChunkRange,
    ) -> None:
        """Wait until all the given chunks are cached."""

        try:
            with trio.fail_after(self.config.chunk_wait_timeout_seconds):
                await trio_util.wait_all(
                    *[
                        (lambda chunk=chunk: chunk.is_cached.wait_value(True))
                        for chunk in chunk_range.chunks
                    ]
                )
        except* trio.TooSlowError:
            if len(chunk_range.uncached_chunks) > 0:
                raise ChunksTooSlowException(
                    threshold=self.config.chunk_wait_timeout_seconds,
                    chunks=chunk_range.uncached_chunks,
                ) from None

    def _check_cache(self, *, start: int, end: int) -> bool:
        """Check if the given byte range is fully cached."""

        from .cache import Cache

        return di[Cache].has(
            cache_key=self.file_metadata.original_filename,
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
            cache_key=self.file_metadata.original_filename,
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
            cache_key=self.file_metadata.original_filename,
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
            original_filename=self.file_metadata.original_filename,
            for_http=True,
            force_resolve=True,
        )

        if entry_info:
            fresh_url = entry_info.get("url")

            if fresh_url and fresh_url != self.target_url.value:
                logger.log(
                    "STREAM",
                    self._build_log_message(
                        f"Refreshed URL for {self.file_metadata.original_filename}"
                    ),
                )

                self.target_url.value = fresh_url

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
        return (
            f"{message} [fh: {self.fh} | file={self.file_metadata.path.split('/')[-1]}]"
        )
