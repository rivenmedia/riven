from dataclasses import dataclass


@dataclass(frozen=True)
class FileMetadata:
    """Metadata about the file being streamed."""

    original_filename: str
    file_size: int
    path: str
