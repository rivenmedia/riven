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


class ConnectionMetadata(TypedDict):
    is_connected: bool
    is_stream_consumed: bool
    is_closed: bool
    is_killed: bool
    http_version: str | None


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
        duration: int | None = None,
        header_size: int | None = None,
    ) -> None:
        self.bytes_transferred = 0
        self.lock = trio.Lock()
        self.vfs = vfs
        self.fh = fh
        self.file_size = file_size
        self.path = path
        self.bitrate = bitrate
        self.duration = duration
        self.scan_tolerance = self._calculate_scan_tolerance()
        self.chunk_size = self._calculate_chunk_size()
        self.footer_size = self._calculate_footer_size()
        self.original_filename = original_filename
        self.cache_key = original_filename
        self.connection_metadata = ConnectionMetadata(
            is_closed=False,
            is_stream_consumed=False,
            is_connected=False,
            is_killed=False,
            http_version=None,
        )
        self.response = None
        self.total_session_connections = 0

        self._header_size = header_size

        # Reads don't always *technically* come in exactly sequentially.
        # They may be interleaved with other reads (e.g. 1 -> 3 -> 2 -> 4), so allow for some tolerance.
        self.sequential_read_tolerance = 1024 * 128 * 10

        logger.trace(
            f"Initialized stream for {self.path} "
            f"with chunk size {self.chunk_size / (1024 * 1024):.2f} MB. "
            f"bitrate={self.bitrate}, "
            f"duration={self.duration}, "
            f"file_size={self.file_size} bytes"
        )

        try:
            self.async_client = di[httpx.AsyncClient]
        except KeyError:
            raise RuntimeError(
                "httpx.AsyncClient not found in dependency injector"
            ) from None

    @property
    def header_size(self) -> int:
        if not self._header_size:
            logger.error(
                f"Attempting to access header_size before it is set for {self.path}"
            )

            raise AttributeError("header_size not set") from None

        return self._header_size

    @asynccontextmanager
    async def manage_connection(self) -> AsyncIterator[None]:
        """Context manager to handle stream connection lifecycle."""

        async with self.lock:
            try:
                if self.response and self.response.is_closed:
                    logger.warning(
                        f"Stream connection was closed for {self.path}; attempting to reconnect."
                    )

                    chunk_range = self._get_chunk_range(
                        position=self.current_read_position
                    )

                    await self.connect(chunk_range=chunk_range)

                yield
            except Exception as e:
                logger.error(
                    f"({e.__class__.__name__}) occurred while managing stream connection for {self.path}: {e}"
                )
                raise

    async def connect(self, chunk_range: ChunkRange) -> None:
        """Establish a streaming connection starting at the given byte offset, aligned to the closest chunk."""

        logger.debug(
            f"first_chunk_start={chunk_range.first_chunk['start']} for {self.path}"
        )

        self.response = await self._prepare_response(
            start=chunk_range.first_chunk["start"]
        )
        self.iterator = self.response.aiter_bytes(chunk_size=chunk_range.chunk_size)
        self.connection_metadata["is_connected"] = True
        self.connection_metadata["http_version"] = self.response.http_version
        self.current_read_position = chunk_range.first_chunk["start"]

        logger.debug(
            f"{self.response.http_version} stream connection established for {self.path} from byte {chunk_range.first_chunk['start']}"
        )

    async def seek(self, chunk_range: ChunkRange) -> None:
        """Seek to a specific byte position in the stream."""

        await self.close()
        await self.connect(chunk_range=chunk_range)

    async def scan_header(self, read_position: int, size: int) -> bytes:
        """Scan the first N bytes of the media stream, and set the header size, to be used in future chunk calculations."""

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

        footer_start = self.file_size - self.footer_size

        data = await self._fetch_discrete_byte_range(
            start=footer_start,
            size=self.file_size - footer_start,
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

    async def read_bytes(self, start: int, end: int) -> bytes:
        """Read a specific number of bytes from the stream."""

        # Chunk boundaries for the request
        chunk_range = self._get_chunk_range(
            position=start,
            size=end - start + 1,
        )

        # A cross-chunk request is when the start and end positions span multiple chunks.
        # Usually this means the left chunk will be cached, and the right chunk will be streamed.
        # However, in some cases (e.g. seeks), the previous chunk may not be cached.
        # When a stream is connected, it is automatically aligned to the nearest chunk start.
        if chunk_range.is_cross_chunk_request:
            # Check to see if a previous request contains cached bytes
            cached_data = await trio.to_thread.run_sync(
                lambda: self.vfs.cache.get(
                    cache_key=self.original_filename,
                    start=start,
                    end=chunk_range.first_chunk["end"],
                )
            )

            if cached_data:
                chunk_range.cached_bytes_size = len(cached_data)

                logger.trace(
                    f"Cached bytes length: {len(cached_data)} for {self.path} [fh {self.fh}]"
                )

                logger.trace(
                    f"after update: chunk_range={chunk_range}, cached_data_length={len(cached_data)} for {self.path}"
                )

                logger.debug(
                    f"after update: first_chunk_start={chunk_range.first_chunk['start']} for {self.path}"
                )
        else:
            cached_data = b""

        if not self.connection_metadata["is_connected"]:
            await self.connect(chunk_range=chunk_range)

        if start + chunk_range.cached_bytes_size < self.current_read_position:
            logger.warning(
                f"Requested start {start} "
                f"is before current read position {self.current_read_position} "
                f"for {self.path}. "
                "Seeking to new start position."
            )
            await self.seek(chunk_range=chunk_range)

        data = b""

        # Get the chunk-aligned start for caching based on the stream's current read position
        cache_chunk_start = (
            self._get_chunk_range(position=self.current_read_position)
        ).first_chunk["start"]

        async for chunk in self.iterator:
            data += chunk

            self.current_read_position += len(chunk)
            self.bytes_transferred += len(chunk)

            logger.debug(
                f"current_read_position={self.current_read_position} for {self.path}"
            )

            if self.current_read_position >= chunk_range.last_chunk["end"] + 1:
                break

        await self._cache_chunk(cache_chunk_start, data)

        stitched_data = cached_data + data

        # Verify the data that was fetched matches what should be returned
        self._verify_read_integrity(chunk_range=chunk_range, data=stitched_data)

        return stitched_data[chunk_range.chunk_slice]

    async def close(self) -> None:
        """Close the active stream."""

        if self.response:
            await self.response.aclose()

            self.response = None

            self.connection_metadata["http_version"] = None
            self.connection_metadata["is_connected"] = False
            self.connection_metadata["is_closed"] = True

            logger.debug(
                f"Ended stream for {self.path} after transferring {self.bytes_transferred / (1024 * 1024):.2f}MB "
                f"in {self.total_session_connections} connections."
            )

    async def _fetch_discrete_byte_range(
        self, start: int, size: int, should_cache: bool = True
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

        self.bytes_transferred += len(data)

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
                self.original_filename,
                True,  # for_http (use unrestricted URL if available)
                False,  # force_resolve (don't unrestrict if already have unrestricted URL)
            )
        )

        if not entry_info:
            logger.error(f"No entry info for {self.original_filename}")
            raise pyfuse3.FUSEError(errno.ENOENT)

        self.target_url = entry_info["url"]

        if not self.target_url:
            logger.error(f"No URL for {self.original_filename}")
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
                        f"Server doesn't support range requests yet: path={self.path}"
                    )

                    if await self._retry_with_backoff(
                        preflight_attempt, max_preflight_attempts, backoffs
                    ):
                        continue

                    # Unable to get range support after retries
                    raise pyfuse3.FUSEError(errno.EIO)
            except httpx.RemoteProtocolError as e:
                logger.debug(
                    f"HTTP protocol error (attempt {preflight_attempt + 1}/{max_preflight_attempts}): path={self.path} error={type(e).__name__}"
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
                    f"Preflight HTTP error {preflight_status_code}: path={self.path}"
                )

                if preflight_status_code in (HTTPStatus.NOT_FOUND, HTTPStatus.GONE):
                    # File can't be found at this URL; try refreshing the URL once
                    if preflight_attempt == 0:
                        fresh_url = await trio.to_thread.run_sync(
                            self._refresh_download_url
                        )

                        if fresh_url:
                            logger.warning(
                                f"URL refresh after HTTP {preflight_status_code}: path={self.path}"
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
                        f"Unexpected preflight HTTP {preflight_status_code}: path={self.path}"
                    )
                    raise pyfuse3.FUSEError(errno.EIO) from e
            except (httpx.TimeoutException, httpx.ConnectError, httpx.InvalidURL) as e:
                logger.debug(
                    f"HTTP request failed (attempt {preflight_attempt + 1}/{max_preflight_attempts}): path={self.path} error={type(e).__name__}"
                )

                if preflight_attempt == 0:
                    # On first exception, try refreshing the URL in case it's a connectivity issue
                    fresh_url = await trio.to_thread.run_sync(
                        self._refresh_download_url
                    )

                    if fresh_url:
                        logger.warning(f"URL refresh after timeout: path={self.path}")

                if await self._retry_with_backoff(
                    preflight_attempt, max_preflight_attempts, backoffs
                ):
                    continue

                raise pyfuse3.FUSEError(errno.EIO) from e
            except pyfuse3.FUSEError:
                raise
            except Exception:
                logger.exception(
                    f"Unexpected error during preflight checks for {self.path}"
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
            logger.error(f"Preflight checks failed for {self.path}: {e}")
            raise

        max_attempts = 4
        backoffs = [0.2, 0.5, 1.0]

        for attempt in range(max_attempts):
            try:
                request = httpx.Request("GET", url=self.target_url, headers=headers)
                response = await self.async_client.send(request, stream=True)

                response.raise_for_status()

                content_length = response.headers.get("Content-Length")
                range_bytes = self.file_size - start

                if (
                    response.status_code == HTTPStatus.OK
                    and content_length is not None
                    and int(content_length) > range_bytes
                ):
                    # Server appears to be ignoring range request and returning full content
                    # This shouldn't happen due to preflight, treat as error
                    logger.warning(
                        f"Server returned full content instead of range: path={self.path}"
                    )
                    raise pyfuse3.FUSEError(errno.EIO)

                self.total_session_connections += 1

                return response
            except httpx.HTTPStatusError as e:
                status_code = e.response.status_code

                if status_code == HTTPStatus.FORBIDDEN:
                    # Forbidden - could be rate limiting or auth issue, don't refresh URL
                    logger.debug(
                        f"HTTP 403 Forbidden: path={self.path} attempt={attempt + 1}"
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
                        f"HTTP 429 Rate Limited: path={self.path} attempt={attempt + 1}"
                    )

                    if await self._retry_with_backoff(attempt, max_attempts, backoffs):
                        continue

                    raise pyfuse3.FUSEError(errno.EAGAIN) from e
                else:
                    # Other unexpected status codes
                    logger.warning(f"Unexpected HTTP {status_code}: path={self.path}")
                    raise pyfuse3.FUSEError(errno.EIO) from e
            except (
                httpx.TimeoutException,
                httpx.ConnectError,
                httpx.InvalidURL,
            ) as e:
                logger.debug(
                    f"HTTP request failed (attempt {attempt + 1}/{max_attempts}): path={self.path} error={type(e).__name__}"
                )

                if attempt == 0:
                    # On first exception, try refreshing the URL in case it's a connectivity issue
                    fresh_url = await trio.to_thread.run_sync(
                        self._refresh_download_url
                    )

                    if fresh_url:
                        logger.warning(f"URL refresh after timeout: path={self.path}")

                if await self._retry_with_backoff(attempt, max_attempts, backoffs):
                    continue

                raise pyfuse3.FUSEError(errno.EIO) from e
            except httpx.RemoteProtocolError as e:
                # This can happen if the server closes the connection prematurely
                logger.debug(
                    f"HTTP protocol error (attempt {attempt + 1}/{max_attempts}): path={self.path} error={type(e).__name__}"
                )

                if await self._retry_with_backoff(attempt, max_attempts, backoffs):
                    continue

                raise pyfuse3.FUSEError(errno.EIO) from e
            except pyfuse3.FUSEError:
                raise
            except Exception:
                logger.exception(
                    f"Unexpected error fetching data block for {self.path}"
                )
                raise pyfuse3.FUSEError(errno.EIO) from None

        raise pyfuse3.FUSEError(errno.EIO)

    def _calculate_scan_tolerance(self) -> int:
        percentage_tolerance = self.file_size // 100  # 1% of file size
        min_tolerance = 1024 * 1024 * 100  # Minimum tolerance of 100MB

        return max(percentage_tolerance, min_tolerance)

    def _calculate_chunk_size(self) -> int:
        # Calculate chunk size based on bitrate and target duration
        # Aim for approximately 2 seconds worth of data per chunk
        target_chunk_duration_seconds = 2

        if self.bitrate:
            bytes_per_second = self.bitrate // 8  # Convert bits to bytes
            calculated_chunk_size = (
                (bytes_per_second // 1024) * 1024 * target_chunk_duration_seconds
            )

            # Clamp chunk size between 256kB and 5MiB
            min_chunk_size = 256 * 1024
            max_chunk_size = 5 * 1024 * 1024

            return max(min(calculated_chunk_size, max_chunk_size), min_chunk_size)
        else:
            # Fallback to default chunk size if bitrate not available
            return 1024 * 1024  # 1MiB default chunk size

    def _get_chunk_range(
        self,
        position: int,
        size: int = 0,
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
                self.original_filename,
                start,
                data,
            )
        )

    def _calculate_footer_size(self) -> int:
        # Use a percentage-based approach for requesting the footer
        # using the file size to determine an appropriate range.
        min_footer_size = 1024 * 16  # Minimum footer size of 16KB
        max_footer_size = self.chunk_size * 2  # Maximum footer size of 1 chunk
        footer_percentage = 0.002  # 0.2% of file size

        percentage_size = int(self.file_size * footer_percentage)

        return min(max(percentage_size, min_footer_size), max_footer_size)

    def _refresh_download_url(self) -> bool:
        """
        Refresh download URL by unrestricting from provider.

        Updates the database with the fresh URL.

        Returns:
            True if successfully refreshed, False otherwise
        """
        # Query database by original_filename and force unrestrict
        entry_info = self.vfs.db.get_entry_by_original_filename(
            original_filename=self.original_filename,
            for_http=True,
            force_resolve=True,
        )

        if entry_info:
            fresh_url = entry_info.get("url")

            if fresh_url and fresh_url != self.target_url:
                logger.debug(f"Refreshed URL for {self.original_filename}")

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

        if self.current_read_position != last_chunk_end + 1:
            raise ReadPositionMismatchException(
                expected_position=last_chunk_end + 1,
                actual_position=self.current_read_position,
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
