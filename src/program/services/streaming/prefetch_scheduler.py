from dataclasses import dataclass


@dataclass(frozen=True)
class PrefetchScheduler:
    """Configuration for prefetching behaviour."""

    buffer_seconds: int
    bytes_per_second: int
    sequential_chunks_required_to_start: int

    @property
    def buffer_size(self) -> int:
        """The buffer size in bytes for prefetching."""

        return self.buffer_seconds * self.bytes_per_second
