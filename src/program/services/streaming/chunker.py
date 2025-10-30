from dataclasses import dataclass
from functools import cached_property


@dataclass(frozen=True, unsafe_hash=True)
class Chunk:
    """Represents a single chunk of data within a media stream."""

    index: int
    start: int
    end: int


@dataclass(frozen=True)
class ChunkRange:
    """
    Represents a range of data to be fetched from a media stream,
    including calculations for chunk boundaries and required bytes.

    Values are immutable, and cached for the current state.
    """

    position: int
    header_size: int
    chunk_size: int
    footer_size: int
    file_size: int
    size: int
    max_chunks: int

    @cached_property
    def request_range(self) -> tuple[int, int]:
        """The byte range requested."""

        start = self.position
        end = start + self.size - 1

        return (start, end)

    @cached_property
    def footer_start(self) -> int:
        """The starting position of the footer."""

        return self.file_size - self.footer_size

    @cached_property
    def content_position(self) -> int:
        """The position within the content, excluding header."""

        start, _ = self.request_range

        if self.header_size < start < self.footer_start:
            return max(0, start - self.header_size)
        elif self.footer_start <= start:
            return min(self.footer_start, start)
        else:
            return start

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
            self.max_chunks + 1,
        )
        upper_chunk_index = min(
            content_request_end // self.chunk_size,
            self.max_chunks + 1,
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

    @cached_property
    def first_chunk(self) -> Chunk:
        """The byte range of the first chunk needed for the request."""

        return self.chunks[0]

    @cached_property
    def last_chunk(self) -> Chunk:
        """The byte range of the last chunk needed for the request."""

        return self.chunks[-1]

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}("
            f"request_range={self.request_range}, "
            f"content_position={self.content_position}, "
            f"size={self.size}, "
            f"chunks={self.chunks}, "
            f"chunks_required={len(self.chunks)}, "
            f"bytes_required={self.bytes_required}, "
            f"header_size={self.header_size}, "
            f"chunk_size={self.chunk_size}"
            ")"
        )


class Chunker:
    """Handles chunk calculations for media streams."""

    def __init__(
        self,
        *,
        chunk_size: int,
        header_size: int,
        footer_size: int,
        file_size: int,
    ) -> None:
        self.chunk_size = chunk_size
        self.header_size = header_size
        self.file_size = file_size
        self.footer_size = footer_size
        self.footer_start = file_size - footer_size
        self.total_chunks_excluding_header_footer = (
            self.file_size - self.footer_size - self.header_size
        ) // self.chunk_size

    def get_chunk_range(self, *, position: int, size: int = 1) -> ChunkRange:
        """Get a chunk range for the given position and size.

        Parameters:
            position (int): The position in the file.
            size (int): The size of the data to fetch.
        Returns:
            ChunkRange: The calculated ChunkRange.
        """

        return ChunkRange(
            position=position,
            size=size,
            chunk_size=self.chunk_size,
            header_size=self.header_size,
            footer_size=self.footer_size,
            file_size=self.file_size,
            max_chunks=self.total_chunks_excluding_header_footer,
        )

    def get_chunk_by_index(self, index: int) -> Chunk:
        """Get a chunk by its index.

        Parameters:
            index (int): The index of the chunk.
        Returns:
            Chunk: The calculated chunk.
        """

        if index == 0:
            return Chunk(
                index=0,
                start=0,
                end=self.header_size - 1,
            )

        chunk_start = min(
            self.header_size + ((index - 1) * self.chunk_size),
            self.footer_start,
        )
        chunk_end = min(
            chunk_start + self.chunk_size - 1,
            self.file_size - 1,
        )

        return Chunk(
            index=index,
            start=chunk_start,
            end=chunk_end,
        )

    def calculate_chunk_difference(
        self,
        left: "ChunkRange",
        right: "ChunkRange",
    ) -> int:
        """Calculate the difference in chunk indices between two chunk ranges.

        Parameters:
            left (ChunkRange): The first chunk range to compare.
            right (ChunkRange): The other chunk range to compare against.
        Returns:
            difference (int): The difference in chunk indices.
        """

        if left.chunk_size != right.chunk_size:
            raise ValueError(
                "Chunk sizes must be the same to calculate chunk difference."
            )

        left_chunk_index = left.content_position // left.chunk_size
        right_chunk_index = right.content_position // right.chunk_size

        return abs(left_chunk_index - right_chunk_index)
