from dataclasses import dataclass
from typing import TypedDict


@dataclass(frozen=True)
class FileMetadata(TypedDict):
    """Metadata about the file being streamed."""

    bitrate: int | None
    duration: float | None
    original_filename: str
    file_size: int
    path: str
