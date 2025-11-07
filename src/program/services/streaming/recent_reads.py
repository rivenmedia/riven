from dataclasses import dataclass, field

from typing import TYPE_CHECKING

import time
from ordered_set import OrderedSet
import trio
import trio_util

from program.services.streaming.chunker import Chunk, ChunkRange

if TYPE_CHECKING:
    from program.services.streaming.media_stream import ReadType


@dataclass(frozen=True)
class Read:
    """Represents a single read operation."""

    chunk_range: ChunkRange
    read_type: "ReadType"
    timestamp: float = field(default_factory=trio.current_time)

    @property
    def uncached_chunks(self) -> OrderedSet[Chunk]:
        """The uncached chunks in this read operation."""

        return OrderedSet(
            [chunk for chunk in self.chunk_range.chunks if not chunk.is_cached.value]
        )


@dataclass
class RecentReads:
    """Tracks recent read operations."""

    current_read: trio_util.AsyncValue[Read | None] = field(
        default_factory=lambda: trio_util.AsyncValue(None)
    )
    previous_read: trio_util.AsyncValue[Read | None] = field(
        default_factory=lambda: trio_util.AsyncValue(None)
    )

    @property
    def last_read_end(self) -> int | None:
        """The end position of the last read operation."""

        if not self.previous_read.value:
            return None

        return self.previous_read.value.chunk_range.request_range[1]
