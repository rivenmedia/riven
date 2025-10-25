from functools import cached_property
from typing import TypedDict


class Chunk(TypedDict):
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
        size: int,
    ) -> None:
        self.position = position
        self.size = size
        self.chunk_size = chunk_size
        self.header_size = header_size
        self.request_range = (position, position + size - 1)

        if position > header_size:
            self.content_position = max(0, position - header_size)
        else:
            self.content_position = position

    @property
    def cached_bytes_size(self) -> int:
        """The number of cached bytes already available."""

        if not hasattr(self, "_cached_bytes_size"):
            self._cached_bytes_size = 0

        return self._cached_bytes_size

    @cached_bytes_size.setter
    def cached_bytes_size(self, value: int) -> None:
        """Set the number of cached bytes already available."""

        self._cached_bytes_size = value

        # Mark cached properties for recalculation
        for attr in [
            "bytes_required",
            "chunks",
            "chunk_slice",
        ]:
            if hasattr(self, attr):
                delattr(self, attr)

    @cached_property
    def bytes_required(self) -> int:
        """The number of bytes required to satisfy this range with chunk-aware boundaries."""

        if len(self.chunks) == 1:
            return self.chunk_size

        return self.last_chunk["end"] - self.first_chunk["end"] + 1

    @cached_property
    def chunks(self) -> list[Chunk]:
        """The list of chunks needed for the request."""

        start, end = self.request_range

        content_request_start = max(0, start - self.header_size)
        content_request_end = max(0, end - self.header_size)

        lower_chunk_index = (
            content_request_start + self.cached_bytes_size
        ) // self.chunk_size
        upper_chunk_index = (
            content_request_end + self.cached_bytes_size
        ) // self.chunk_size

        chunks: list[Chunk] = []

        # If the current request is within the header boundaries, include the header chunk.
        # This is sized differently to normal chunks, so handle it separately.
        if self.size and self.cache_aware_content_position < self.header_size:
            chunks.append(Chunk(index=0, start=0, end=self.header_size - 1))

        for chunk_index in range(lower_chunk_index, upper_chunk_index + 1):
            chunk_start = self.header_size + (chunk_index * self.chunk_size)
            chunk_end = chunk_start + self.chunk_size - 1

            chunks.append(
                Chunk(
                    index=chunk_index + 1,
                    start=chunk_start,
                    end=chunk_end,
                )
            )

        return chunks

    @cached_property
    def chunk_slice(self) -> slice:
        """The slice within the chunk range that corresponds to the requested range."""

        divisor = (
            self.chunk_size if self.position >= self.header_size else self.header_size
        )
        content_offset_in_chunk = self.cache_aware_content_position % divisor
        slice_left = content_offset_in_chunk
        slice_right = slice_left + self.size

        return slice(slice_left, slice_right, 1)

    @property
    def first_chunk(self) -> Chunk:
        """The byte range of the first chunk needed for the request."""

        return self.chunks[0]

    @property
    def last_chunk(self) -> Chunk:
        """The byte range of the last chunk needed for the request."""

        return self.chunks[-1]

    @property
    def cache_aware_content_position(self) -> int:
        """The content position adjusted for cached bytes."""

        return self.content_position + self.cached_bytes_size

    @property
    def is_cross_chunk_request(self) -> bool:
        """Whether the request spans multiple chunks."""

        return len(self.chunks) > 1

    @property
    def required_new_bytes(self) -> int:
        """The number of new bytes required, excluding cached bytes."""

        return self.size - self.cached_bytes_size

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

        current_chunk_index = self.cache_aware_content_position // self.chunk_size
        other_chunk_index = other.cache_aware_content_position // other.chunk_size

        return abs(current_chunk_index - other_chunk_index)

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}("
            f"request_range={self.request_range}, "
            f"position={self.position}, "
            f"content_position={self.content_position}, "
            f"cache_aware_content_position={self.cache_aware_content_position}, "
            f"size={self.size}, "
            f"chunks={self.chunks}, "
            f"chunks_required={len(self.chunks)}, "
            f"bytes_required={self.bytes_required}, "
            f"cached_bytes={self.cached_bytes_size}, "
            f"required_new_bytes={self.required_new_bytes}, "
            f"chunk_slice={self.chunk_slice}, "
            f"header_size={self.header_size}, "
            f"chunk_size={self.chunk_size}"
            ")"
        )
