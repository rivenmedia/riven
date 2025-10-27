import trio
import pyfuse3
import errno
import httpx

from dataclasses import dataclass
from functools import cached_property
from contextlib import asynccontextmanager
from loguru import logger
from typing import TYPE_CHECKING, Literal, TypedDict
from http import HTTPStatus
from kink import di
from collections.abc import AsyncIterator
from time import time

from src.program.services.streaming.chunk_range import Chunk, ChunkRange
from src.program.services.streaming.exceptions import (
    EmptyDataError,
    RawByteLengthMismatchException,
)
from program.settings.manager import settings_manager

if TYPE_CHECKING:
    from src.program.services.filesystem.vfs.rivenvfs import RivenVFS


@dataclass
class Config:
    """Configuration for the media stream."""

    # Reads don't always come in exactly sequentially;
    # they may be interleaved with other reads (e.g. 1 -> 3 -> 2 -> 4).
    #
    # This allows for some tolerance during the calculations.
    sequential_read_tolerance_blocks: int

    # Tolerance for detecting scan reads. Any read that jumps more than this value is considered a scan.
    scan_tolerance_blocks: int

    # Kernel block size; the byte length the OS reads/writes at a time.
    block_size: int

    # Maximum chunk size for adaptive chunk sizing.
    max_chunk_size: int

    # Minimum chunk size for adaptive chunk sizing.
    min_chunk_size: int

    # Target playback duration for each chunk in seconds.
    target_chunk_duration_seconds: int

    # Number of skipped chunks required to trigger a seek
    seek_chunk_tolerance: int

    # Default bitrate to use when no probed information is available.
    default_bitrate: int

    @property
    def header_size(self) -> int:
        """Default header size for scanning purposes."""

        return self.block_size * 2

    @property
    def sequential_read_tolerance(self) -> int:
        """Tolerance for sequential reads to account for interleaved reads."""

        return self.block_size * self.sequential_read_tolerance_blocks

    @property
    def scan_tolerance(self) -> int:
        """Tolerance for detecting scan reads. Any read that jumps more than this value is considered a scan."""

        return self.block_size * self.scan_tolerance_blocks


@dataclass
class Connection:
    """Metadata about the current streaming connection."""

    is_connected: bool = False
    is_exited: bool = False
    is_running: bool = False
    target_position: int = 0
    start_position: int = 0
    current_read_position: int | None = None
    last_read_end: int | None = None
    response: httpx.Response | None = None
    reader: AsyncIterator[bytes] | None = None
    lock: trio.Lock = trio.Lock()

    def __init__(self) -> None:
        self.current_request_chunk_range = None

    @property
    def current_request_chunk_range(self) -> ChunkRange | None:
        """The chunk range of the last request, if any."""

        return self._last_request_chunk_range

    @current_request_chunk_range.setter
    def current_request_chunk_range(self, value: ChunkRange | None) -> None:
        if not value:
            self._last_request_chunk_range = None
            self._sequential_chunks_fetched = 0

            return

        if self.current_request_chunk_range:
            last_chunk_fetched = self.current_request_chunk_range.last_chunk.index

            for chunk in reversed(value.chunks):
                chunk_index = chunk.index

                if last_chunk_fetched + 1 == chunk_index:
                    self.last_chunk_fetched = chunk_index
                    self._sequential_chunks_fetched += 1

                    break

        self._last_request_chunk_range = value

    @property
    def sequential_chunks_fetched(self) -> int:
        """The number of sequential chunks fetched so far."""

        return self._sequential_chunks_fetched

    async def reset(self) -> None:
        if self.response:
            await self.response.aclose()

        self.current_read_position = 0
        self.start_position = 0
        self.current_request_chunk_range = None
        self.last_read_end = None
        self.is_connected = False
        self.is_exited = False
        self.is_running = False
        self.response = None


@dataclass
class PrefetchScheduler:
    """Configuration for prefetching behaviour."""

    prefetch_seconds: int
    sequential_chunks_required_to_start: int

    lock: trio.Lock = trio.Lock()
    is_exited: bool = False
    is_running: bool = False

    def start(self) -> None:
        """Start the prefetch scheduler."""

        self.is_running = True

    def stop(self) -> None:
        """Stop the prefetch scheduler."""

        self.is_running = False


@dataclass
class SessionStatistics:
    """Statistics about the current streaming session."""

    bytes_transferred: int = 0
    total_session_connections: int = 0


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

        self.config = Config(
            block_size=fs.block_size,
            max_chunk_size=1 * 1024 * 1024,  # 1 MiB
            min_chunk_size=256 * 1024,  # 256 kB
            sequential_read_tolerance_blocks=10,
            target_chunk_duration_seconds=2,
            seek_chunk_tolerance=5,
            scan_tolerance_blocks=25,
            default_bitrate=10 * 1000 * 1000,  # 10 Mbps
        )

        self.session_statistics = SessionStatistics()

        self.connection = Connection()

        self.prefetch_scheduler = PrefetchScheduler(
            prefetch_seconds=streaming_config.buffer_seconds,
            sequential_chunks_required_to_start=25,
        )

        self.file_metadata = FileMetadata(
            bitrate=bitrate,
            duration=duration,
            file_size=file_size,
            path=path,
            original_filename=original_filename,
        )

        self.read_lock = trio.Lock()
        self.vfs = vfs
        self.fh = fh

        logger.log(
            "STREAM",
            self._build_log_message(
                f"Initialized stream with chunk size {self.chunk_size / (1024 * 1024):.2f} MB "
                f"[{self.chunk_size // self.config.block_size} blocks]. "
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

    @property
    def should_prefetch_start(self) -> bool:
        """Whether prefetching should start based on recent chunk access patterns."""

        # Determine if we've had enough sequential chunk fetches to trigger prefetching.
        # This helps to avoid scans triggering expensive and unnecessary prefetches.
        has_sufficient_sequential_fetches = (
            self.connection.sequential_chunks_fetched
            >= self.prefetch_scheduler.sequential_chunks_required_to_start
        )

        # Determine if the current read position is within the prefetch lookahead range.
        is_within_prefetch_range = (
            self.num_seconds_behind <= self.prefetch_scheduler.prefetch_seconds
        )

        return (
            not self.prefetch_scheduler.is_running
            and has_sufficient_sequential_fetches
            and is_within_prefetch_range
        )

    @property
    def num_seconds_behind(self) -> float:
        """Number of seconds the last read end is behind the current read position."""

        # If no current reads, we're not behind at all.
        if (
            self.connection.last_read_end is None
            or self.connection.current_read_position is None
        ):
            return 0

        raw_seconds = (
            self.connection.current_read_position - self.connection.last_read_end
        ) / self.bytes_per_second

        return raw_seconds // 1

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

        # Adjust chunk size to scale based on the block size.
        return aligned_chunk_size * (block_size // (1024 * 128))

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
    async def manage_connection(self) -> AsyncIterator[None]:
        """Context manager to handle stream connection lifecycle."""

        try:
            yield
        except* trio.TooSlowError as e:
            logger.exception(self._build_log_message(f"Stream operation too slow"))

            raise pyfuse3.FUSEError(errno.EBUSY) from e.exceptions[0]
        except* httpx.ReadTimeout as e:
            pass
        except* (
            httpx.ReadError,
            httpx.RemoteProtocolError,
            httpx.StreamClosed,
        ) as e:
            if self.connection.current_read_position is None:
                logger.exception(
                    self._build_log_message(
                        f"Stream error occurred, "
                        f"but there is no current read position at which we can reconnect. "
                        f"Killing stream. {e.exceptions[0]}"
                    )
                )

                raise

            logger.warning(
                self._build_log_message(
                    f"Stream error occurred while managing stream connection: {e.exceptions[0]}. "
                    "Attempting to reconnect..."
                )
            )

            await self.connect(self.connection.current_read_position)

            if not self.connection.is_connected:
                logger.error(
                    self._build_log_message("Failed to reconnect stream connection.")
                )

                raise pyfuse3.FUSEError(errno.EIO) from e.exceptions[0]
        except* Exception as e:
            logger.error(
                self._build_log_message(
                    f"{e.__class__.__name__} occurred while managing stream connection: {e}"
                )
            )
            raise

    async def connect(self, position: int) -> None:
        """Establish a streaming connection starting at the given byte offset, aligned to the closest chunk."""

        chunk_aligned_start = self._get_chunk_range(position).first_chunk.start

        self.connection.response = await self._prepare_response(
            start=chunk_aligned_start
        )
        self.connection.is_connected = True
        self.connection.start_position = chunk_aligned_start
        self.connection.current_read_position = chunk_aligned_start
        self.connection.reader = self.connection.response.aiter_bytes(
            chunk_size=self.chunk_size
        )

        if not self.connection.is_running:
            trio.lowlevel.spawn_system_task(self._main_stream_loop)

        logger.log(
            "STREAM",
            self._build_log_message(
                f"{self.connection.response.http_version} stream connection established "
                f"from byte {chunk_aligned_start} / {self.file_metadata['file_size']}."
            ),
        )

    async def seek(self, position: int) -> None:
        """Seek to a specific byte position in the stream."""

        await self.close()
        await self.connect(position=position)

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

    async def scan(self, read_position: int, size: int) -> bytes:
        """Fetch extra, ephemeral data for scanning purposes."""

        data = await self._fetch_discrete_byte_range(
            start=read_position,
            size=size,
            should_cache=False,
        )

        return data[:size]

    async def read(
        self,
        *,
        request_start: int,
        request_end: int,
        request_size: int,
    ) -> bytes:
        """Handles incoming read requests from the VFS."""

        async with self.manage_connection():
            async with self.read_lock:
                logger.log(
                    "STREAM",
                    self._build_log_message(
                        "Read request: "
                        f"request_start={request_start} "
                        f"request_end={request_end} "
                        f"size={request_size}"
                    ),
                )

                read_type = self._detect_read_type(
                    start=request_start,
                    end=request_end,
                    size=request_size,
                )

                if read_type == "normal_read" and (
                    request_start < self.file_metadata["file_size"] - self.footer_size
                ):
                    self.connection.current_request_chunk_range = self._get_chunk_range(
                        position=request_start,
                        size=request_size,
                    )

                # Try cache first for the exact request (cache handles chunk lookup and slicing)
                # Use cache_key to share cache between all paths pointing to same file
                cached_bytes = await self._read_cache(
                    start=request_start,
                    end=request_end,
                )

                if cached_bytes:
                    returned_data = cached_bytes
                else:
                    logger.log(
                        "STREAM",
                        self._build_log_message(
                            f"Performing {read_type} for [{request_start}-{request_end}]"
                        ),
                    )

                    match read_type:
                        case "header_scan":
                            returned_data = await self.scan_header(
                                read_position=request_start,
                                size=request_size,
                            )
                        case "footer_scan":
                            returned_data = await self.scan_footer(
                                read_position=request_start,
                                size=request_size,
                            )
                        case "general_scan":
                            returned_data = await self.scan(
                                read_position=request_start,
                                size=request_size,
                            )
                        case "normal_read":
                            if not self.connection.is_connected:
                                await self.connect(
                                    position=max(
                                        self.config.header_size,
                                        request_start,
                                    )
                                )

                            if not self.prefetch_scheduler.is_running:
                                self.connection.target_position = request_end + 1

                            returned_data = await self.read_bytes(
                                start=request_start,
                                end=request_end,
                            )
                        case _:
                            # This should never happen due to prior validation
                            raise RuntimeError("Unknown read type")

                logger.log(
                    "STREAM",
                    self._build_log_message(
                        f"sequential_chunk_fetches={self.connection.sequential_chunks_fetched} "
                        f"current_read_position={self.connection.current_read_position} "
                        f"last_read_end={self.connection.last_read_end} "
                    ),
                )

                self.connection.last_read_end = request_end

                if self.should_prefetch_start:
                    trio.lowlevel.spawn_system_task(self._main_prefetch_loop)

                return returned_data

    async def read_bytes(
        self,
        start: int,
        end: int,
    ) -> bytes:
        """Read a specific number of bytes from the stream."""

        await self._maybe_seek(position=start)

        if not self.connection.current_request_chunk_range:
            raise httpx.StreamError("No chunk range available for current request")

        required_chunks = self.connection.current_request_chunk_range.chunks

        with trio.fail_after(10):
            while True:
                uncached_chunks = await trio.to_thread.run_sync(
                    lambda: self._get_uncached_chunks(chunks=required_chunks)
                )

                if len(uncached_chunks) == 0:
                    logger.log(
                        "STREAM",
                        self._build_log_message(
                            f"Found cache, attempting to read {start}-{end}"
                        ),
                    )
                    break

                logger.log(
                    "STREAM",
                    self._build_log_message(
                        f"Waiting for chunks {uncached_chunks} to be cached for read {start}-{end}..."
                    ),
                )

                await trio.sleep(0.1)

        cached_data = await self._read_cache(
            start=start,
            end=end,
        )

        if cached_data:
            logger.log(
                "STREAM",
                self._build_log_message(
                    f"Found chunk {start}-{end} ({len(cached_data)} bytes) from cache."
                ),
            )

            return cached_data

        raise httpx.StreamError(
            "Failed to read requested bytes from cache after waiting."
        )

    async def close(self) -> None:
        """Close the active stream."""

        if self.connection.is_running:
            # Wait for the stream loop to close
            with trio.fail_after(5):
                self.connection.is_running = False

                while not self.connection.is_exited:
                    await trio.sleep(0.1)

        if self.prefetch_scheduler.is_running:
            # Wait for the prefetch loop to close
            with trio.fail_after(5):
                self.prefetch_scheduler.stop()

                while not self.prefetch_scheduler.is_exited:
                    await trio.sleep(0.1)

        await self.connection.reset()

        logger.log(
            "STREAM",
            self._build_log_message(
                f"Ended stream for {self.file_metadata['path']} fh={self.fh} "
                f"after transferring {self.session_statistics.bytes_transferred / (1024 * 1024):.2f}MB "
                f"in {self.session_statistics.total_session_connections} connections."
            ),
        )

    async def _maybe_seek(self, *, position: int) -> None:
        """Seeks the stream if the read position is outside the current chunk range."""

        if self.connection.current_read_position is None:
            raise httpx.StreamError("Stream is not connected")

        if (
            self.connection.current_read_position
            and self.config.header_size < position < self.connection.start_position
        ):
            request_chunk_range = self._get_chunk_range(position=position)

            logger.log(
                "STREAM",
                self._build_log_message(
                    f"Requested start {position} "
                    f"is before current read position {self.connection.current_read_position} "
                    f"for {self.file_metadata['path']}. "
                    f"Seeking to new start position {request_chunk_range.first_chunk.start}/{self.file_metadata['file_size']}."
                ),
            )

            # Always seek backwards if the requested start is before the stream's start position (excluding header, which is pre-fetched).
            # Streams can only read forwards, so a new connection must be made.
            await self.seek(position=request_chunk_range.first_chunk.start)

        # Check if requested start is after current read position,
        # and if it exceeds the seek tolerance, move the stream to the new start.
        if (
            self.connection.current_read_position
            and position > self.connection.current_read_position
        ):
            request_chunk_range = self._get_chunk_range(position=position)

            read_position_chunk_range = self._get_chunk_range(
                position=self.connection.current_read_position
            )

            chunk_difference = read_position_chunk_range.calculate_chunk_difference(
                request_chunk_range
            )

            if chunk_difference >= self.config.seek_chunk_tolerance:
                logger.log(
                    "STREAM",
                    self._build_log_message(
                        f"Requested start {position} "
                        f"is after current read position {self.connection.current_read_position} "
                        f"for {self.file_metadata['path']}. "
                        f"Seeking to new start position {request_chunk_range.first_chunk.start}/{self.file_metadata['file_size']}."
                    ),
                )

                await self.seek(position=request_chunk_range.first_chunk.start)

    def _detect_read_type(
        self,
        *,
        start: int,
        end: int,
        size: int,
    ) -> Literal["header_scan", "footer_scan", "general_scan", "normal_read"]:
        file_size = self.file_metadata["file_size"]

        is_header_scan = start < end <= self.config.header_size

        is_footer_scan = (
            (self.connection.last_read_end or 0)
            < start - self.config.sequential_read_tolerance
        ) and file_size - self.footer_size <= start <= file_size

        is_general_scan = (
            not is_header_scan
            and not is_footer_scan
            and (
                self.connection.last_read_end
                and (
                    # This behaviour is seen during scanning
                    # and captures large jumps in read position
                    # generally observed when the player is reading the footer
                    # for cues or metadata after initial playback start.
                    #
                    # Scans typically read less than a single block.
                    abs(self.connection.last_read_end - start)
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
                    and self.connection.last_read_end == 0
                )
            )
        )

        if is_header_scan:
            return "header_scan"
        elif is_footer_scan:
            return "footer_scan"
        elif is_general_scan:
            return "general_scan"
        else:
            return "normal_read"

    async def _main_stream_loop(self) -> None:
        logger.log(
            "STREAM",
            self._build_log_message("Starting stream loop"),
        )

        self.connection.is_running = True

        sleep_interval = 0.01

        chunks_to_skip = 0

        async with self.manage_connection():
            async with trio.open_nursery() as nursery:
                while self.connection.is_running:
                    if not self.connection.current_read_position or (
                        self.connection.current_read_position
                        and self.connection.current_read_position
                        >= self.connection.target_position
                    ):
                        await trio.sleep(sleep_interval)
                        continue

                    async with self.connection.lock:
                        if not self.connection.reader:
                            raise httpx.StreamError("No stream reader available")

                        start_read_position = self.connection.current_read_position

                        now = time()
                        last_iteration_time = now

                        async for chunk in self.connection.reader:
                            # Cache the chunk in the background without blocking the iterator.
                            # This will be picked up by the reads asynchronously.
                            nursery.start_soon(
                                self._cache_chunk,
                                self.connection.current_read_position,
                                chunk,
                            )

                            self.connection.current_read_position += len(chunk)
                            self.session_statistics.bytes_transferred += len(chunk)

                            # Check to see if any subsequent chunks are already cached.
                            #
                            # Streams cannot skip content themselves; they must read all data in sequence.
                            # This means that if future chunks are cached, it would need to re-download them
                            # to reach the next uncached position.
                            #
                            # To avoid this, we can detect cached chunks ahead of time and manually seek past them.
                            while True:
                                test_chunk = self._get_chunk_range(
                                    position=self.connection.current_read_position
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

                                    await trio.sleep(sleep_interval)
                                    continue

                                break

                            # If cached chunks were found, kill the stream loop.
                            # This will be picked up after the loop exits.
                            if chunks_to_skip > 0:
                                self.connection.is_running = False

                                logger.log(
                                    "STREAM",
                                    self._build_log_message(
                                        f"Exiting stream loop to skip {chunks_to_skip} cached chunks"
                                    ),
                                )

                            iteration_duration = time() - last_iteration_time
                            last_iteration_time = time()

                            logger.log(
                                "STREAM",
                                self._build_log_message(
                                    f"Fetched {len(chunk)} bytes "
                                    f"[{self.connection.current_read_position - len(chunk)}-{self.connection.current_read_position - 1}] "
                                    f"in {iteration_duration:.3f}s"
                                ),
                            )

                            # Break early if the stream loop has been stopped.
                            # Otherwise, the loop will continue until the target position is reached,
                            # which can prevent the connection from being closed during large fetch windows.
                            if not self.connection.is_running:
                                logger.log(
                                    "STREAM",
                                    self._build_log_message(
                                        f"Stream loop termination signal detected with "
                                        f"{self.connection.target_position - self.connection.current_read_position} bytes remaining to read"
                                    ),
                                )

                                break

                            if (
                                self.connection.current_read_position
                                >= self.connection.target_position
                            ):
                                break

                        iteration_duration = time() - now

                        logger.log(
                            "STREAM",
                            self._build_log_message(
                                f"Stream fetched {start_read_position}-{self.connection.current_read_position} "
                                f"({self.connection.current_read_position - start_read_position} bytes) "
                                f"in {iteration_duration:.3f}s"
                            ),
                        )

                    await trio.sleep(sleep_interval)

                nursery.cancel_scope.cancel()

            self.connection.is_exited = True

            # If cached chunks were found, seek the stream to the new position
            #
            # This **MUST BE CALLED AFTER** the stream loop has exited to avoid deadlocks.
            # Seeking closes the connection, which attempts to close the loop and wait for is_exited to become true.
            if self.connection.current_read_position and chunks_to_skip > 0:
                target_read_position = self.connection.current_read_position + (
                    chunks_to_skip * self.chunk_size
                )

                if target_read_position >= self.file_metadata["file_size"]:
                    logger.log(
                        "STREAM",
                        self._build_log_message(
                            f"Reached end of file while skipping cached chunks."
                        ),
                    )

                    await self.close()
                else:
                    logger.log(
                        "STREAM",
                        self._build_log_message(
                            f"Skipped ahead to byte "
                            f"{target_read_position} "
                            f"after finding {chunks_to_skip} cached chunks"
                        ),
                    )

                    await self.seek(target_read_position)

            logger.log("STREAM", self._build_log_message("Stream loop ended"))

    async def _main_prefetch_loop(self) -> None:
        logger.log("STREAM", self._build_log_message("Starting prefetcher"))

        self.prefetch_scheduler.start()

        prefetch_buffer_size = (
            self.prefetch_scheduler.prefetch_seconds * self.bytes_per_second
        )

        sleep_interval = 0.1

        async with self.prefetch_scheduler.lock:
            while self.prefetch_scheduler.is_running:
                if (
                    self.connection.last_read_end is None
                    or self.connection.current_read_position is None
                ):
                    # This shouldn't happen; prefetcher should only start after some data has been read.
                    logger.log(
                        "STREAM",
                        self._build_log_message(
                            "Invalid read state; stopping prefetcher"
                        ),
                    )

                    break

                # Calculate the prefetch target position, clamped to the file size.
                target_position = min(
                    self.connection.last_read_end + prefetch_buffer_size,
                    self.file_metadata["file_size"],
                )

                if target_position < self.connection.current_read_position:
                    await trio.sleep(sleep_interval)
                    continue

                # Prefetches are quite simple; we just move the target position forward
                # and let the main stream loop handle the actual fetching in the background.
                #
                # This keeps the prefetch logic decoupled from the main stream logic,
                # and allows us to avoid complex coordination between the two that tends to result in deadlocks.
                self.connection.target_position = target_position

                await trio.sleep(sleep_interval)

            logger.log("STREAM", self._build_log_message("Prefetcher stopped"))

            self.prefetch_scheduler.is_exited = True

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

        if should_cache:
            await self._cache_chunk(start, verified_data[:size])

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

    def _get_chunk_range(
        self,
        position: int,
        size: int = 1,
    ) -> ChunkRange:
        """Get the range of bytes required to fulfil a read at the given position and for the given size, aligned to chunk boundaries."""

        return ChunkRange(
            position=position,
            chunk_size=self.chunk_size,
            header_size=self.config.header_size,
            size=size,
        )

    def _get_uncached_chunks(self, *, chunks: list[Chunk]) -> set[Chunk]:
        """Check the cache for the given chunks and return the ones that are not cached."""

        return set(
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

    async def _read_cache(self, start: int, end: int) -> bytes:
        return await self.vfs.cache.get(
            cache_key=self.file_metadata["original_filename"],
            start=start,
            end=end,
        )

    async def _cache_chunk(self, start: int, data: bytes) -> None:
        await self.vfs.cache.put(
            self.file_metadata["original_filename"],
            start,
            data,
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

    def _build_log_message(self, message: str) -> str:
        return f"{message} [fh: {self.fh} file={self.file_metadata['path'].split('/')[-1]}]"
