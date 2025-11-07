import httpx

from collections.abc import AsyncIterator
from dataclasses import dataclass

import trio_util

from program.services.streaming.chunker import ChunkRange


@dataclass
class StreamConnection:
    """Metadata about the current streaming connection."""

    reader: AsyncIterator[bytes]
    response: httpx.Response

    _sequential_chunks_fetched: int = 0

    def __init__(
        self,
        *,
        response: httpx.Response,
        start_position: int,
        current_read_position: int,
        reader: AsyncIterator[bytes],
    ) -> None:
        self.response = response
        self.start_position = start_position
        self.current_read_position = current_read_position
        self.reader = reader
        self.seek_required = trio_util.AsyncBool(False)
        self.seek_range: ChunkRange | None = None

    @property
    def sequential_chunks_fetched(self) -> int:
        """The number of sequential chunks fetched so far."""

        return self._sequential_chunks_fetched

    @property
    def current_read_position(self) -> int:
        """The current read position in the stream."""

        return self._current_read_position

    @current_read_position.setter
    def current_read_position(self, value: int) -> None:
        """Set the current read position in the stream."""

        if value < 0:
            raise ValueError("Current read position cannot be negative")

        self._current_read_position = value

    @property
    def start_position(self) -> int:
        """The start position in the stream."""

        return self._start_position

    @start_position.setter
    def start_position(self, value: int) -> None:
        """Set the start position in the stream."""

        if value < 0:
            raise ValueError("Start position cannot be negative")

        if value > self.current_read_position:
            raise ValueError(
                "Start position cannot be greater than current read position"
            )

        self._start_position = value

    def increment_sequential_chunks(
        self,
    ) -> None:
        """Increment the count of sequential chunks fetched."""

        self._sequential_chunks_fetched += 1

    def seek(self, chunk_range: ChunkRange) -> None:
        """Seek to a new position in the stream."""

        if len(chunk_range.uncached_chunks) > 0:
            self.seek_range = chunk_range
            self.current_read_position = chunk_range.uncached_chunks[0].start
            self.seek_required.value = True
