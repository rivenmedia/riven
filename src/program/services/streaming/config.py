from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    """Configuration for the media stream."""

    # Chunk size (in bytes) used for streaming calculations.
    chunk_size: int

    # Timeout for detecting stalled streams.
    stream_timeout_seconds: int

    # Timeout for waiting for a chunk to become available.
    chunk_wait_timeout_seconds: int

    # Timeout for establishing a connection to the streaming service.
    connect_timeout_seconds: int

    # Reads don't always come in exactly sequentially;
    # they may be interleaved with other reads (e.g. 1 -> 3 -> 2 -> 4).
    #
    # This allows for some tolerance during the calculations.
    sequential_read_tolerance_blocks: int = 10

    # Tolerance for detecting scan reads. Any read that jumps more than this value is considered a scan.
    scan_tolerance_blocks: int = 25

    @property
    def block_size(self) -> int:
        """Kernel block size; the byte length the OS reads/writes at a time."""

        return 128 * 1024

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
