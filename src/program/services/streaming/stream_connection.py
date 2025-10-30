from collections.abc import AsyncIterator
from dataclasses import dataclass

import httpx

from src.program.services.streaming.prefetch_scheduler import PrefetchScheduler
from src.program.services.streaming.recent_reads import RecentReads
from src.program.settings.manager import settings_manager


@dataclass
class StreamConnection:
    """Metadata about the current streaming connection."""

    reader: AsyncIterator[bytes]
    response: httpx.Response
    is_active: bool = True
    should_close: bool = False
    seek_to: int | None = None

    _sequential_chunks_fetched: int = 0

    def __init__(
        self,
        *,
        bytes_per_second: int,
        response: httpx.Response,
        start_position: int,
        current_read_position: int,
        reader: AsyncIterator[bytes],
    ) -> None:
        streaming_config = settings_manager.settings.streaming

        self.bytes_per_second = bytes_per_second
        self.response = response
        self.start_position = start_position
        self.current_read_position = current_read_position
        self.reader = reader
        self.prefetch_scheduler = PrefetchScheduler(
            bytes_per_second=bytes_per_second,
            buffer_seconds=streaming_config.buffer_seconds,
            sequential_chunks_required_to_start=streaming_config.sequential_chunks_required_for_prefetch,
        )

    @property
    def sequential_chunks_fetched(self) -> int:
        """The number of sequential chunks fetched so far."""

        return self._sequential_chunks_fetched

    def is_prefetch_unlocked(self, *, recent_reads: "RecentReads") -> bool:
        """Whether prefetching is currently unlocked."""

        # Determine if we've had enough sequential chunk fetches to trigger prefetching.
        # This helps to avoid scans triggering expensive and unnecessary prefetches.
        has_sufficient_sequential_fetches = (
            self.sequential_chunks_fetched
            >= self.prefetch_scheduler.sequential_chunks_required_to_start
        )

        # Calculate how far behind the current read position is from the last read end.
        num_seconds_behind = self.calculate_num_seconds_behind(
            recent_reads=recent_reads
        )

        # Determine if the current read position is within the prefetch lookahead range.
        is_within_prefetch_range = (
            num_seconds_behind <= self.prefetch_scheduler.buffer_seconds
        )

        return has_sufficient_sequential_fetches and is_within_prefetch_range

    @property
    def current_read_position(self) -> int:
        """The current read position in the stream."""

        return self._current_read_position

    @current_read_position.setter
    def current_read_position(self, value: int | None) -> None:
        """Set the current read position in the stream."""

        if value is None:
            if hasattr(self, "_current_read_position"):
                del self._current_read_position

            return

        if value < 0:
            raise ValueError("Current read position cannot be negative")

        self._current_read_position = value

    @property
    def start_position(self) -> int:
        """The start position in the stream."""

        return self._start_position

    @start_position.setter
    def start_position(self, value: int | None) -> None:
        """Set the start position in the stream."""

        if value is None:
            if hasattr(self, "_start_position"):
                del self._start_position

            return

        if value < 0:
            raise ValueError("Start position cannot be negative")

        self._start_position = value

    def calculate_num_seconds_behind(self, *, recent_reads: "RecentReads") -> float:
        """Number of seconds the last read end is behind the current read position."""

        # If no current reads, we're not behind at all.
        if recent_reads.last_read_end is None:
            return 0.0

        return (
            self.current_read_position - recent_reads.last_read_end
        ) // self.bytes_per_second

    def calculate_target_position(self, recent_reads: "RecentReads") -> int:
        """Calculate the target position for the current read."""

        if not recent_reads.current_read:
            return 0

        prefetch_size = (
            self.prefetch_scheduler.buffer_size
            if self.is_prefetch_unlocked(recent_reads=recent_reads)
            else 0
        )

        return recent_reads.current_read.last_chunk.end + prefetch_size + 1

    def increment_sequential_chunks(
        self,
    ) -> None:
        """Increment the count of sequential chunks fetched."""

        self._sequential_chunks_fetched += 1

    async def close(self) -> None:
        if self.response:
            await self.response.aclose()
