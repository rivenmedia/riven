from dataclasses import dataclass

from src.program.services.streaming.chunk_range import ChunkRange


@dataclass
class RecentReads:
    """Tracks recent read operations."""

    current_read: ChunkRange | None = None
    previous_read: ChunkRange | None = None

    @property
    def last_read_end(self) -> int | None:
        """The end position of the last read operation."""

        if not self.previous_read:
            return None

        return self.previous_read.request_range[1]
