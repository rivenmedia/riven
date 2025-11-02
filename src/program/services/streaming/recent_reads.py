from dataclasses import dataclass, field

from typing import TYPE_CHECKING

from ordered_set import OrderedSet

from src.program.services.streaming.chunker import Chunk, ChunkRange

if TYPE_CHECKING:
    from src.program.services.streaming.media_stream import ReadType


@dataclass
class Read:
    """Represents a single read operation."""

    chunk_range: ChunkRange
    read_type: "ReadType"
    uncached_chunks: OrderedSet[Chunk] = field(default_factory=lambda: OrderedSet([]))


@dataclass
class RecentReads:
    """Tracks recent read operations."""

    current_read: Read | None = None
    previous_read: Read | None = None

    @property
    def last_read_end(self) -> int | None:
        """The end position of the last read operation."""

        if not self.previous_read:
            return None

        return self.previous_read.chunk_range.request_range[1]
