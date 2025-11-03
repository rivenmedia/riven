from dataclasses import dataclass
from typing import TypedDict


@dataclass(frozen=True)
class FileMetadata(TypedDict):
    """Metadata about the file being streamed."""

    original_filename: str
    file_size: int
    path: str
