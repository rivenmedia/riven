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
        del self.content_position
        del self.bytes_required
        del self.first_chunk
        del self.last_chunk
        del self.chunks_required
        del self.chunk_slice

    @cached_property
    def request_range(self) -> tuple[int, int]:
        """The byte range requested from the stream."""

        return (self.position, self.position + self.size - 1)

    @cached_property
    def content_position(self) -> int:
        """The position within the content, excluding the header size."""

        return max(0, self.position + self.cached_bytes_size - self.header_size)

    @cached_property
    def bytes_required(self) -> int:
        """The number of bytes required to satisfy this range with chunk-aware boundaries."""

        return self.chunks_required * self.chunk_size

    @cached_property
    def first_chunk(self) -> Chunk:
        """The byte range of the first chunk needed for the request."""

        chunk_index = self.content_position // self.chunk_size
        chunk_start = min(
            self.position,
            self.header_size + (chunk_index * self.chunk_size),
        )
        chunk_end = chunk_start + self.chunk_size - 1

        return Chunk(
            index=chunk_index,
            start=chunk_start,
            end=chunk_end,
        )

    @cached_property
    def last_chunk(self) -> Chunk:
        """The byte range of the last chunk needed for the request."""

        # Calculate request end position
        request_end = self.position + self.size - 1

        # Calculate last chunk range based on content position
        content_request_end = max(0, request_end - self.header_size)

        last_chunk_index = content_request_end // self.chunk_size
        last_chunk_start = self.header_size + (last_chunk_index * self.chunk_size)
        last_chunk_end = last_chunk_start + self.chunk_size - 1

        return Chunk(
            index=last_chunk_index,
            start=last_chunk_start,
            end=last_chunk_end,
        )

    @cached_property
    def chunks_required(self) -> int:
        """The number of chunks required to satisfy this range."""

        first_chunk_index = self.first_chunk["index"]
        last_chunk_index = self.last_chunk["index"]

        return last_chunk_index - first_chunk_index + 1

    @cached_property
    def chunk_slice(self) -> slice:
        """The slice within the chunk range that corresponds to the requested range."""

        content_offset_in_chunk = self.content_position % self.chunk_size
        slice_left = content_offset_in_chunk
        slice_right = slice_left + self.size

        return slice(slice_left, slice_right, 1)

    @property
    def is_cross_chunk_request(self) -> bool:
        """Whether the request spans multiple chunks."""

        return self.chunks_required > 1

    @property
    def required_new_bytes(self) -> int:
        """The number of new bytes required, excluding cached bytes."""

        return self.size - self.cached_bytes_size

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}("
            f"range={self.request_range}, "
            f"size={self.size}, "
            f"first_chunk={self.first_chunk}, "
            f"last_chunk={self.last_chunk}, "
            f"chunks_required={self.chunks_required}, "
            f"bytes_required={self.bytes_required}, "
            f"cached_bytes={self.cached_bytes_size}, "
            f"required_new_bytes={self.required_new_bytes}, "
            f"chunk_slice={self.chunk_slice}, "
            f"header_size={self.header_size}, "
            f"chunk_size={self.chunk_size}"
            ")"
        )
