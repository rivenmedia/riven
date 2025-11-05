import cachetools
from dataclasses import dataclass, field
from functools import cached_property
from kink import di
from ordered_set import OrderedSet
import trio_util


class ChunkCacheNotifier:
    """Manages chunk cache emitters for notifying when chunks have been cached."""

    emitters = cachetools.LRUCache["Chunk", trio_util.AsyncBool](maxsize=1024)

    def get_emitter(
        self,
        *,
        chunk: "Chunk",
    ) -> trio_util.AsyncBool:
        """Get or create an emitter for the given chunk.

        Parameters:
            chunk (Chunk): The chunk identifier.

        Returns:
            trio_util.AsyncBool: The emitter for the chunk.
        """

        if chunk not in self.emitters:
            from .cache import Cache

            is_cached = di[Cache].has(
                cache_key=chunk.cache_key,
                start=chunk.start,
                end=chunk.end,
            )

            self.emitters[chunk] = trio_util.AsyncBool(is_cached)

        return self.emitters[chunk]

    def clear_emitter(self, *, chunk: "Chunk") -> None:
        """Clear the emitter for a specific chunk."""

        if chunk in self.emitters:
            del self.emitters[chunk]

    def clear_emitters(self, *, cache_key: str) -> None:
        """Clear all emitters for a specific cache key."""

        self.emitters = {
            k: v for k, v in self.emitters.items() if k.cache_key != cache_key
        }


@dataclass(frozen=True, unsafe_hash=True)
class Chunk:
    """Represents a single chunk of data within a media stream."""

    cache_key: str
    index: int
    start: int
    end: int

    _emitter: trio_util.AsyncBool = field(
        init=False,
        hash=False,
        repr=False,
        compare=False,
    )

    def __post_init__(self) -> None:
        if self.start < 0 or self.end < 0:
            raise ValueError("Chunk start and end must be non-negative integers.")

        if self.end < self.start:
            raise ValueError("Chunk end must be greater than or equal to start.")

        # Retrieve an emitter from the chunk cache manager,
        # which will be used to signal when this chunk has been cached.
        object.__setattr__(
            self,
            "_emitter",
            di[ChunkCacheNotifier].get_emitter(chunk=self),
        )

    @property
    def is_cached(self) -> trio_util.AsyncBool:
        """An emitter that indicates whether the chunk is cached."""

        if not self._emitter.value:
            from .cache import Cache

            cache_hit = di[Cache].has(
                cache_key=self.cache_key,
                start=self.start,
                end=self.end,
            )

            if cache_hit:
                self._emitter.value = True

        return self._emitter

    def emit_cache_signal(self) -> None:
        """Emit that the chunk is now cached."""

        # Set the emitter to True to indicate the chunk is cached,
        # and notify any listeners.
        self._emitter.value = True

        # Clear the emitter from the manager to free up memory.
        di[ChunkCacheNotifier].clear_emitter(chunk=self)

    @property
    def size(self) -> int:
        """The size of the chunk in bytes."""

        return self.end - self.start + 1

    def __repr__(self) -> str:
        """
        String representation of the Chunk.

        e.g.
        `Chunk #1 [0-1023] (1024 bytes)`
        """

        cached_str = "(cached) " if self.is_cached.value else ""

        return (
            f"{self.__class__.__name__} #{self.index} {cached_str}"
            f"[{self.start}-{self.end}] "
            f"({self.size} bytes)"
        )


@dataclass(frozen=True)
class ChunkRange:
    """
    Represents a range of data to be fetched from a media stream,
    including calculations for chunk boundaries and required bytes.

    Values are immutable, and cached for the current state.
    """

    cache_key: str
    position: int
    chunk_size: int
    file_size: int
    size: int
    max_chunks: int
    header_chunk: Chunk
    footer_chunk: Chunk

    @cached_property
    def request_range(self) -> tuple[int, int]:
        """The byte range requested."""

        start = self.position
        end = start + self.size - 1

        return (start, end)

    @cached_property
    def bytes_required(self) -> int:
        """The number of bytes required to satisfy this range."""

        if len(self.chunks) == 1:
            return self.chunk_size

        return self.last_chunk.end - self.first_chunk.start + 1

    @cached_property
    def chunks(self) -> OrderedSet[Chunk]:
        """The list of chunks needed for the request."""

        start, end = self.request_range

        # If the request is entirely within the header, return just the header chunk.
        if end < self.header_chunk.size:
            return OrderedSet([self.header_chunk])

        # If the request is entirely within the footer, return just the footer chunk.
        if start >= self.footer_chunk.start:
            return OrderedSet([self.footer_chunk])

        # The request spans content, so calculate the required chunks.
        content_request_start = max(0, start - self.header_chunk.size)
        content_request_end = min(
            max(0, end - self.header_chunk.size),
            self.footer_chunk.start - 1,
        )

        lower_chunk_index = min(
            content_request_start // self.chunk_size,
            self.max_chunks + 1,
        )
        upper_chunk_index = min(
            content_request_end // self.chunk_size,
            self.max_chunks + 1,
        )

        chunks = OrderedSet([])

        # If the current request is within the header boundaries, include the header chunk.
        # This is sized differently to normal chunks, so handle it separately.
        if self.size and self.position < self.header_chunk.size:
            chunks.add(self.header_chunk)

        for chunk_index in range(lower_chunk_index, upper_chunk_index + 1):
            chunk_start = self.header_chunk.size + (chunk_index * self.chunk_size)
            chunk_end = min(
                chunk_start + self.chunk_size - 1,
                self.footer_chunk.start - 1,
            )

            chunks.add(
                Chunk(
                    cache_key=self.cache_key,
                    index=chunk_index + 1,
                    start=chunk_start,
                    end=chunk_end,
                )
            )

        # If the request spans into the footer, include the footer chunk.
        if end >= self.footer_chunk.start:
            chunks.add(self.footer_chunk)

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
            f"position={self.position}, "
            f"size={self.size}, "
            f"chunks={self.chunks}, "
            f"chunks_required={len(self.chunks)}, "
            f"bytes_required={self.bytes_required}, "
            f"header_chunk={self.header_chunk}, "
            f"footer_chunk={self.footer_chunk}, "
            f"chunk_size={self.chunk_size}"
            ")"
        )


class Chunker:
    """Handles chunk calculations for media streams."""

    def __init__(
        self,
        *,
        cache_key: str,
        chunk_size: int,
        header_size: int,
        footer_size: int,
        file_size: int,
    ) -> None:
        self.cache_key = cache_key
        self.chunk_size = chunk_size
        self.header_size = header_size
        self.file_size = file_size
        self.footer_size = footer_size
        self.footer_start = file_size - footer_size
        self.total_chunks_excluding_header_footer = (
            self.file_size - self.footer_size - self.header_size
        ) // self.chunk_size

    @cached_property
    def header_chunk(self) -> Chunk:
        """Get the header chunk.

        Returns:
            Chunk: The header chunk.
        """

        index = 0

        return Chunk(
            cache_key=self.cache_key,
            index=index,
            start=0,
            end=self.header_size - 1,
        )

    @cached_property
    def footer_chunk(self) -> Chunk:
        """Get the footer chunk.

        Returns:
            Chunk: The footer chunk.
        """

        index = self.total_chunks_excluding_header_footer + 1

        return Chunk(
            cache_key=self.cache_key,
            index=index,
            start=self.footer_start,
            end=self.file_size - 1,
        )

    def get_chunk_range(self, *, position: int, size: int = 1) -> ChunkRange:
        """Get a chunk range for the given position and size.

        Parameters:
            position (int): The position in the file.
            size (int): The size of the data to fetch.
        Returns:
            ChunkRange: The calculated ChunkRange.
        """

        return ChunkRange(
            cache_key=self.cache_key,
            position=position,
            size=size,
            chunk_size=self.chunk_size,
            header_chunk=self.header_chunk,
            footer_chunk=self.footer_chunk,
            file_size=self.file_size,
            max_chunks=self.total_chunks_excluding_header_footer,
        )
