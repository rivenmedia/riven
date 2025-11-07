from loguru import logger
from ordered_set import OrderedSet
from ..chunker import Chunk


class ChunkException(Exception):
    """Base class for chunk-related exceptions."""

    pass


class ChunksTooSlowException(ChunkException):
    """Raised when chunks took too long to be fetched from the cache."""

    def __init__(self, *, chunks: OrderedSet[Chunk], threshold: int) -> None:
        logger.debug(f"ChunksTooSlowException: {chunks}, threshold={threshold}")

        if len(chunks) == 0:
            return

        if len(chunks) == 1:
            chunk_message = f"Chunk #{chunks[0].index}"
        else:
            chunk_message = f"Chunks #{chunks[0].index}-{chunks[-1].index}"

        super().__init__(
            f"{chunk_message} took too long to fetch, exceeding threshold of {threshold}s."
        )

        self.chunks = chunks
        self.threshold = threshold
