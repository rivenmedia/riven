from dataclasses import dataclass


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

    # Timeout for waiting for a chunk to become available.
    chunk_wait_timeout_seconds: int = 10

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
