from dataclasses import dataclass
from functools import cached_property

from loguru import logger


@dataclass(frozen=True, unsafe_hash=True)
class Chunk:
    """Represents a single chunk of data within a media stream."""

    index: int
    start: int
    end: int


class ChunkRange:
    """
    Represents a range of data to be fetched from a media stream,
    including calculations for chunk boundaries and required bytes.

    Values are immutable, and cached for the current state.
    If cached bytes are provided, the relevant property cached will be invalidated.
    """

    def __init__(
        self,
        *,
        position: int,
        chunk_size: int,
        header_size: int,
        footer_size: int,
        file_size: int,
        size: int,
    ) -> None:
        self.position = position
        self.size = size
        self.chunk_size = chunk_size
        self.header_size = header_size
        self.file_size = file_size
        self.footer_size = footer_size
        self.footer_start = file_size - footer_size
        self.request_range = (position, position + size - 1)
        self.total_chunks_excluding_header_footer = (
            self.file_size - self.footer_size - self.header_size
        ) // self.chunk_size

        if header_size < position < self.footer_start:
            self.content_position = max(0, position - header_size)
        elif self.footer_start <= position:
            self.content_position = min(self.footer_start, position)
        else:
            self.content_position = position

    @cached_property
    def bytes_required(self) -> int:
        """The number of bytes required to satisfy this range."""

        if len(self.chunks) == 1:
            return self.chunk_size

        return self.last_chunk.end - self.first_chunk.end + 1

    @cached_property
    def chunks(self) -> list[Chunk]:
        """The list of chunks needed for the request."""

        start, end = self.request_range

        content_request_start = max(0, start - self.header_size)
        content_request_end = max(0, end - self.header_size)

        lower_chunk_index = min(
            content_request_start // self.chunk_size,
            self.total_chunks_excluding_header_footer + 1,
        )
        upper_chunk_index = min(
            content_request_end // self.chunk_size,
            self.total_chunks_excluding_header_footer + 1,
        )

        chunks: list[Chunk] = []

        # If the current request is within the header boundaries, include the header chunk.
        # This is sized differently to normal chunks, so handle it separately.
        if self.size and self.content_position < self.header_size:
            chunks.append(Chunk(index=0, start=0, end=self.header_size - 1))

        for chunk_index in range(lower_chunk_index, upper_chunk_index + 1):
            chunk_start = min(
                self.header_size + (chunk_index * self.chunk_size),
                self.footer_start,
            )
            chunk_end = min(
                chunk_start + self.chunk_size - 1,
                self.file_size - 1,
            )

            chunks.append(
                Chunk(
                    index=chunk_index + 1,
                    start=chunk_start,
                    end=chunk_end,
                )
            )

        return chunks

    @property
    def first_chunk(self) -> Chunk:
        """The byte range of the first chunk needed for the request."""

        return self.chunks[0]

    @property
    def last_chunk(self) -> Chunk:
        """The byte range of the last chunk needed for the request."""

        return self.chunks[-1]

    def calculate_chunk_difference(self, other: "ChunkRange") -> int:
        """Calculate the difference in chunk indices between this range and another position.

        Parameters:
            other (ChunkRange): The other chunk range to compare against.
        Returns:
            int: The difference in chunk indices.
        """

        if self.chunk_size != other.chunk_size:
            raise ValueError(
                "Chunk sizes must be the same to calculate chunk difference."
            )

        current_chunk_index = self.content_position // self.chunk_size
        other_chunk_index = other.content_position // other.chunk_size

        return abs(current_chunk_index - other_chunk_index)

    @staticmethod
    def get_chunk_index(position: int, chunk_size: int, header_size: int) -> int:
        """Get the chunk index for a given position.

        Parameters:
            position (int): The position in the file.
            chunk_size (int): The size of each chunk.
            header_size (int): The size of the header.

        Returns:
            int: The chunk index.
        """

        if position < header_size:
            return 0
        else:
            return (position - header_size) // chunk_size + 1

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}("
            f"request_range={self.request_range}, "
            f"position={self.position}, "
            f"content_position={self.content_position}, "
            f"size={self.size}, "
            f"chunks={self.chunks}, "
            f"chunks_required={len(self.chunks)}, "
            f"bytes_required={self.bytes_required}, "
            f"header_size={self.header_size}, "
            f"chunk_size={self.chunk_size}"
            ")"
        )
