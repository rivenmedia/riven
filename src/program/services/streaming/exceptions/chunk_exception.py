from loguru import logger
from ordered_set import OrderedSet
from ..chunker import ChunkRange


class ChunkException(Exception):
    """Base class for chunk-related exceptions."""

    pass


class ChunksTooSlowException(ChunkException):
    """Raised when chunks took too long to be fetched from the cache."""

    def __init__(self, *, chunk_range: ChunkRange, threshold: int) -> None:
        logger.debug(f"ChunksTooSlowException: {chunk_range}, threshold={threshold}")

        uncached_chunks = OrderedSet(
            [chunk for chunk in chunk_range.chunks if not chunk.is_cached.value]
        )

        if len(uncached_chunks) == 1:
            chunk_message = f"Chunk #{uncached_chunks[0].index}"
        else:
            chunk_message = (
                f"Chunks #{uncached_chunks[0].index}-{uncached_chunks[-1].index}"
            )

        super().__init__(
            f"{chunk_message} took too long to fetch, exceeding threshold of {threshold}s."
        )

        self.chunk_range = chunk_range
        self.uncached_chunks = uncached_chunks
        self.threshold = threshold
