import trio
import trio_util
import pyfuse3
import errno
import httpx

from dataclasses import dataclass
from functools import cached_property
from contextlib import asynccontextmanager, contextmanager
from loguru import logger
from typing import TYPE_CHECKING, Literal
from http import HTTPStatus
from kink import di
from collections.abc import AsyncGenerator, AsyncIterator, Generator, Iterator
from time import time
from ordered_set import OrderedSet

from src.program.services.streaming.chunker import Chunk, ChunkRange, Chunker
from src.program.services.streaming.config import Config
from src.program.services.streaming.exceptions import (
    CacheDataNotFoundException,
    ChunksTooSlowException,
    EmptyDataError,
    RawByteLengthMismatchException,
)
from src.program.settings.manager import settings_manager
from src.program.services.streaming.file_metadata import FileMetadata
from src.program.services.streaming.recent_reads import RecentReads
from src.program.services.streaming.session_statistics import SessionStatistics
from src.program.services.streaming.stream_connection import (
    ConnectionKilledException,
    FileConsumedException,
    SeekRequiredException,
    StreamConnection,
)

if TYPE_CHECKING:
    from src.program.services.filesystem.vfs.rivenvfs import RivenVFS


type ReadType = Literal[
    "header_scan",
    "footer_scan",
    "general_scan",
    "body_read",
    "footer_read",
    "seek",
    "cache_hit",
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
        vfs: "RivenVFS",
        fh: pyfuse3.FileHandleT,
        file_size: int,
        path: str,
        original_filename: str,
        bitrate: int | None = None,
        duration: float | None = None,
    ) -> None:
        fs = settings_manager.settings.filesystem
        streaming_config = settings_manager.settings.streaming

        self.fh = fh
        self.read_lock = trio.Lock()
        self.vfs = vfs
        self.recent_reads: RecentReads = RecentReads()
        self.connection: StreamConnection | None = None
        self.is_streaming: bool = False
        self.requested_chunks = trio_util.AsyncValue[OrderedSet[Chunk]](OrderedSet([]))
        self.latest_chunk_range = trio_util.AsyncValue[ChunkRange | None](None)
        self.cached_chunks: dict[int, trio_util.AsyncBool] = {}
        self.cancel_scope: trio.CancelScope | None = None

        self.stream_start_event = trio.Event()

        self.config = Config(
            max_chunk_size=1 * 1024 * 1024,  # 1 MiB
            min_chunk_size=256 * 1024,  # 256 kB
            sequential_read_tolerance_blocks=10,
            target_chunk_duration_seconds=2,
            seek_chunk_tolerance=5,
            scan_tolerance_blocks=25,
            default_bitrate=10 * 1000 * 1000,  # 10 Mbps
        )

        self.session_statistics = SessionStatistics()

        self.file_metadata = FileMetadata(
            bitrate=bitrate,
            duration=duration,
            file_size=file_size,
            path=path,
            original_filename=original_filename,
        )

        self.chunker = Chunker(
            chunk_size=self.chunk_size,
            header_size=self.config.header_size,
            footer_size=self.footer_size,
            file_size=file_size,
        )

        logger.log(
            "STREAM",
            self._build_log_message(
                f"Initialized stream with chunk size {self.chunk_size / (1024 * 1024):.2f} MB. "
                f"bitrate={self.file_metadata['bitrate']}, "
                f"duration={self.file_metadata['duration']}, "
                f"file_size={self.file_metadata['file_size']} bytes",
            ),
        )

        # Validate cache size vs buffer_seconds
        # Cache needs to hold: 1x chunk (1MB) + (buffer_seconds * bitrate MB/s)
        min_cache_mb = (
            self.chunk_size + (streaming_config.buffer_seconds * self.bytes_per_second)
        ) // (1024 * 1024)

        if fs.cache_max_size_mb < min_cache_mb:
            logger.warning(
                self._build_log_message(
                    f"Cache size ({fs.cache_max_size_mb}MB) is too small for buffer_seconds ({streaming_config.buffer_seconds} seconds). "
                    f"Minimum recommended: {min_cache_mb}MB. "
                    f"Cache thrashing may occur with concurrent reads, causing poor performance."
                )
            )

        try:
            self.async_client = di[httpx.AsyncClient]
        except KeyError:
            raise RuntimeError(
                "httpx.AsyncClient not found in dependency injector"
            ) from None

        # Start the main stream loop in the background,
        # dormant until the stream_start_event is set.
        trio.lowlevel.spawn_system_task(self.run)

    @cached_property
    def bytes_per_second(self) -> int:
        """Average bytes per second based on the file's bitrate."""

        bitrate = self.file_metadata["bitrate"]

        if not bitrate:
            logger.log(
                "STREAM",
                self._build_log_message(
                    f"No bitrate available. Falling back to {self.config.default_bitrate // 1000 // 1000} Mbps. "
                    f"Media analysis may have previously failed on this file. If you experience streaming issues, try re-analysing the file with FFProbe."
                ),
            )

            # Fallback to configured default bitrate if no probed information is available
            bitrate = self.config.default_bitrate

        return bitrate // 8

    @cached_property
    def chunk_size(self) -> int:
        """An optimal chunk size based on the file's bitrate."""

        target_chunk_duration_seconds = self.config.target_chunk_duration_seconds

        calculated_chunk_size = (
            (self.bytes_per_second // 1024) * 1024 * target_chunk_duration_seconds
        )

        # Clamp chunk size to min/max values
        min_chunk_size = self.config.min_chunk_size
        max_chunk_size = self.config.max_chunk_size

        clamped_chunk_size = max(
            min(calculated_chunk_size, max_chunk_size),
            min_chunk_size,
        )

        # Align chunk size to nearest block size boundary, rounded up.
        # This attempts to avoid cross-chunk reads that require expensive cache lookups.
        block_size = self.config.block_size
        aligned_chunk_size = -(clamped_chunk_size // -block_size) * block_size

        return aligned_chunk_size

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
            self.is_streaming = True

            logger.log(
                "STREAM",
                self._build_log_message("Starting stream loop"),
            )

            yield
        finally:
            self.is_streaming = False

            logger.log("STREAM", self._build_log_message("Stream loop ended"))

    @asynccontextmanager
    async def manage_connection(
        self,
        *,
        cancel_scope: trio.CancelScope,
        position: int,
    ) -> AsyncIterator[StreamConnection]:
        """Context manager to handle connection lifecycle."""

        try:
            self.connection = await self.connect(
                position=position,
                cancel_scope=cancel_scope,
            )

            yield self.connection
        except* (
            httpx.ReadError,
            httpx.RemoteProtocolError,
            httpx.StreamClosed,
        ) as e:
            logger.exception(
                self._build_log_message(
                    f"{e.exceptions[0].__class__.__name__} error occurred whilst managing stream connection: {e.exceptions[0]}"
                )
            )

            if not self.connection:
                raise pyfuse3.FUSEError(errno.EIO) from e.exceptions[0]

            logger.warning(self._build_log_message("Attempting to reconnect..."))
        except* httpx.ReadTimeout as e:
            logger.exception(
                self._build_log_message(f"Stream operation timed out whilst reading")
            )

            if self.connection:
                logger.debug(f"response details: {self.connection.response}")

            pass
        except* httpx.PoolTimeout as e:
            logger.exception(
                self._build_log_message(
                    f"Stream operation timed out whilst acquiring a connection"
                )
            )

            raise pyfuse3.FUSEError(errno.ETIMEDOUT) from e.exceptions[0]
        except* SeekRequiredException as e:
            for exc in e.exceptions:
                if isinstance(exc, SeekRequiredException):
                    logger.debug(
                        self._build_log_message(
                            f"Stream seek required: {exc.seek_position}"
                        )
                    )

                    pass
                else:
                    raise
        except* trio.TooSlowError as e:
            logger.exception(self._build_log_message(f"Stream operation too slow"))
        except* ConnectionKilledException:
            logger.debug(self._build_log_message("Stream connection killed"))

            cancel_scope.cancel("Connection killed")
        except* StopAsyncIteration:
            logger.debug(self._build_log_message("Stream exhausted"))

            cancel_scope.cancel("Stream exhausted")
        except* Exception as e:
            logger.error(
                self._build_log_message(
                    f"{e.__class__.__name__} occurred while managing stream connection: {e}"
                )
            )

            raise
        finally:
            await self.close()

    async def run(self) -> None:
        # Wait for the signal before starting the stream loop
        await self.stream_start_event.wait()

        if self.is_streaming:
            logger.error(
                self._build_log_message("Stream is already running, skipping start")
            )

            return

        async with self.stream_lifecycle():
            async with trio.open_nursery() as nursery:
                if not self.recent_reads.current_read:
                    raise RuntimeError(
                        "Cannot manage connection without a current read position"
                    )

                self.cancel_scope = nursery.cancel_scope
                position = self.recent_reads.current_read.first_chunk.start

                while not nursery._closed:
                    async with self.manage_connection(
                        cancel_scope=nursery.cancel_scope,
                        position=position,
                    ) as connection:
                        chunks_to_skip = 0
                        previous_fetched_chunk = None

                        async for chunks in self.requested_chunks.eventual_values():
                            for chunk in chunks:
                                if (
                                    previous_fetched_chunk
                                    and previous_fetched_chunk.index
                                    and abs(chunk.index - previous_fetched_chunk.index)
                                    > self.config.seek_chunk_tolerance
                                ):
                                    connection.seek(position=chunk.start)

                                chunk_label = f"[{chunk.start}-{chunk.end}]"

                                with self.benchmark(
                                    title=f"Fetching bytes {chunk_label}"
                                ):
                                    data = await anext(connection.reader)

                                previous_fetched_chunk = chunk
                                self.requested_chunks.value.discard(chunk)

                                with self.benchmark(
                                    title=f"Processing bytes {chunk_label}"
                                ):
                                    connection.increment_sequential_chunks()

                                    # Cache the chunk in the background without blocking the iterator.
                                    # This will be picked up by the reads asynchronously.
                                    nursery.start_soon(
                                        lambda: self._cache_chunk(
                                            start=chunk.start,
                                            data=data,
                                        )
                                    )

                                    connection.current_read_position += len(data)
                                    self.session_statistics.bytes_transferred += len(
                                        data
                                    )

                                    # Check to see if any subsequent chunks are already cached.
                                    #
                                    # Streams cannot skip content themselves; they must read all data in sequence.
                                    # This means that if future chunks are cached, it would need to re-download them
                                    # to reach the next uncached position.
                                    #
                                    # To avoid this, we can detect cached chunks ahead of time and manually seek past them.
                                    while True:
                                        test_chunk = self.chunker.get_chunk_range(
                                            position=connection.current_read_position
                                            + (chunks_to_skip * self.chunk_size)
                                        )

                                        uncached_chunks = await trio.to_thread.run_sync(
                                            lambda: self._get_uncached_chunks(
                                                chunks=test_chunk.chunks
                                            )
                                        )

                                        # If the next chunk is already cached, skip ahead
                                        if len(uncached_chunks) == 0:
                                            chunks_to_skip += 1
                                            await trio.sleep(0)
                                            continue

                                        break

                                    if chunks_to_skip > 0:
                                        target_chunk_index = (
                                            chunk.index + chunks_to_skip
                                        )

                                        if (
                                            target_chunk_index
                                            <= self.chunker.total_chunks_excluding_header_footer
                                        ):
                                            target_chunk = (
                                                self.chunker.get_chunk_by_index(
                                                    index=target_chunk_index
                                                )
                                            )

                                            logger.log(
                                                "STREAM",
                                                self._build_log_message(
                                                    f"Skipped ahead to byte "
                                                    f"{target_chunk} "
                                                    f"after finding {chunks_to_skip} cached chunks"
                                                ),
                                            )

                                            # If cached chunks were found, break out of the stream loop.
                                            connection.seek(position=target_chunk.start)
                                        else:
                                            logger.log(
                                                "STREAM",
                                                self._build_log_message(
                                                    f"Reached end of file while skipping cached chunks."
                                                ),
                                            )

                                            # Break out of the loop to let the context manager close the connection
                                            raise FileConsumedException()

                                    # Break early if the stream loop has been stopped or seeked.
                                    # Otherwise, the loop will continue until the target position is reached,
                                    # which can prevent the connection from being closed during large fetch windows.
                                    if not connection.is_active:
                                        logger.log(
                                            "STREAM",
                                            self._build_log_message(
                                                f"Stream loop termination signal detected with "
                                                f"{chunks[-1].end - connection.current_read_position} bytes remaining to read"
                                            ),
                                        )

                                        raise ConnectionKilledException()

                    position = connection.current_read_position

                    # logger.log(
                    #     "STREAM",
                    #     self._build_log_message(
                    #         f"Stream fetched {start_read_position}-{connection.current_read_position} "
                    #         f"({connection.current_read_position - start_read_position} bytes) "
                    #         f"in {iteration_duration:.3f}s. "
                    #         f"There are roughly {connection.calculate_num_seconds_behind(recent_reads=self.recent_reads)} seconds of buffer room available."
                    #     ),
                    # )

    async def connect(
        self,
        *,
        position: int,
        cancel_scope: trio.CancelScope,
    ) -> StreamConnection:
        """Establish a streaming connection starting at the given byte offset, aligned to the closest chunk."""

        chunk_aligned_start = max(
            self.config.header_size,
            self.chunker.get_chunk_range(position=position).first_chunk.start,
        )

        response = await self._prepare_response(start=chunk_aligned_start)

        self.connection = StreamConnection(
            bytes_per_second=self.bytes_per_second,
            response=response,
            start_position=chunk_aligned_start,
            current_read_position=chunk_aligned_start,
            reader=response.aiter_bytes(chunk_size=self.chunk_size),
            nursery_cancel_scope=cancel_scope,
        )

        logger.log(
            "STREAM",
            self._build_log_message(
                f"{response.http_version} stream connection established "
                f"from byte {chunk_aligned_start} / {self.file_metadata['file_size']}."
            ),
        )

        return self.connection

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

        if not self.connection:
            logger.debug(self._build_log_message("No active connection to kill"))

            return

        if self.is_streaming and self.cancel_scope:
            # Wait for the stream loop to close
            with trio.fail_after(5):
                self.cancel_scope.cancel("Stream killed")

                while self.is_streaming:
                    await trio.sleep(0.1)

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
            start=0,
            size=self.config.header_size,
        )

        return data[read_position : read_position + size]

    async def scan_footer(self, read_position: int, size: int) -> bytes:
        """
        Scans the end of the media file for footer data.

        This "over-fetches" for the individual request,
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

    @asynccontextmanager
    async def read_lifecycle(self, chunk_range: ChunkRange) -> AsyncIterator[ReadType]:
        """Context manager for managing read lifecycle."""

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

            self.recent_reads.current_read = chunk_range

            read_type = await self._detect_read_type(
                chunk_range=chunk_range,
            )

            yield read_type
        finally:
            self.recent_reads.previous_read = chunk_range

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
                case "body_read" | "seek":
                    self.stream_start_event.set()

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

        # Try cache first for the exact request (cache handles chunk lookup and slicing)
        # Use cache_key to share cache between all paths pointing to same file
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
            if (
                self.connection
                and self.connection.current_read_position
                and self.config.header_size < start < self.connection.start_position
            ):
                request_chunk_range = self.chunker.get_chunk_range(position=start)

                logger.log(
                    "STREAM",
                    self._build_log_message(
                        f"Requested start {start} "
                        f"is before current read position {self.connection.current_read_position} "
                        f"for {self.file_metadata['path']}. "
                        f"Seeking to new start position {request_chunk_range.first_chunk.start}/{self.file_metadata['file_size']}."
                    ),
                )

                # Always seek backwards if the requested start is before the stream's start position (excluding header, which is pre-fetched).
                # Streams can only read forwards, so a new connection must be made.
                return "seek"

            # Check if requested start is after current read position,
            # and if it exceeds the seek tolerance, move the stream to the new start.
            if self.connection and start > self.connection.current_read_position:
                request_chunk_range = self.chunker.get_chunk_range(position=start)

                read_position_chunk_range = self.chunker.get_chunk_range(
                    position=self.connection.current_read_position
                )

                chunk_difference = self.chunker.calculate_chunk_difference(
                    left=request_chunk_range,
                    right=read_position_chunk_range,
                )

                if chunk_difference >= self.config.seek_chunk_tolerance:
                    logger.log(
                        "STREAM",
                        self._build_log_message(
                            f"Requested start {start} "
                            f"is after current read position {self.connection.current_read_position} "
                            f"for {self.file_metadata['path']}. "
                            f"Seeking to new start position {request_chunk_range.first_chunk.start}/{self.file_metadata['file_size']}."
                        ),
                    )

                    return "seek"

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

        async for chunk in response.aiter_bytes(chunk_size=min(size, self.chunk_size)):
            data += chunk

            if len(data) >= size:
                break

        self.session_statistics.bytes_transferred += len(data)

        verified_data = self._verify_scan_integrity((start, start + size), data)

        chunk_range = self.chunker.get_chunk_range(position=start, size=size)

        logger.debug(f"chunk_range for discrete fetch: {chunk_range}")

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
            except Exception:
                logger.exception(
                    self._build_log_message(
                        f"Unexpected error during preflight checks: {e}"
                    )
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
        chunks = chunk_range.chunks

        has_requested = False

        try:
            with trio.fail_after(self.config.chunk_wait_timeout_seconds):
                while True:
                    uncached_chunks = await trio.to_thread.run_sync(
                        lambda: self._get_uncached_chunks(chunks=chunks)
                    )

                    if len(uncached_chunks) == 0:
                        logger.log(
                            "STREAM",
                            self._build_log_message(
                                f"Found cache, attempting to read {start}-{end}"
                            ),
                        )

                        break

                    if not has_requested:
                        has_requested = True

                        self.requested_chunks.value = self.requested_chunks.value.union(
                            uncached_chunks
                        )

                        logger.log(
                            "STREAM",
                            self._build_log_message(
                                f"Waiting for chunks {uncached_chunks} to be cached for read {start}-{end}..."
                            ),
                        )

                    await trio.sleep(0)
        except trio.TooSlowError:
            raise ChunksTooSlowException(
                threshold=self.config.chunk_wait_timeout_seconds,
                chunk_range=chunk_range,
            )

    def _get_uncached_chunks(self, *, chunks: list[Chunk]) -> OrderedSet[Chunk]:
        """Check the cache for the given chunks and return the ones that are not cached."""

        return OrderedSet(
            chunk
            for chunk in chunks
            if not self._check_cache(start=chunk.start, end=chunk.end)
        )

    def _check_cache(self, *, start: int, end: int) -> bool:
        """Check if the given byte range is fully cached."""

        return self.vfs.cache.has(
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

        return await self.vfs.cache.get(
            cache_key=self.file_metadata["original_filename"],
            start=start,
            end=end,
        )

    async def _cache_chunk(self, start: int, data: bytes) -> None:
        await self.vfs.cache.put(
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
            raise EmptyDataError(range=range)

        start, end = range
        expected_length = end - start
        actual_length = len(data)

        if actual_length < expected_length:
            raise RawByteLengthMismatchException(
                expected_length=expected_length,
                actual_length=actual_length,
                range=range,
            )

        return data

    @contextmanager
    def benchmark(self, title: str = "Benchmarking") -> Iterator[None]:
        """Context manager for benchmarking code execution time."""

        try:
            start_time = time()

            yield
        finally:
            end_time = time()

            logger.log(
                "STREAM",
                self._build_log_message(f"{title} took {end_time - start_time:.3f}s"),
            )

    def _build_log_message(self, message: str) -> str:
        return f"{message} [fh: {self.fh} file={self.file_metadata['path'].split('/')[-1]}]"
