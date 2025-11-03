from ..chunker import ChunkRange


class ChunkException(Exception):
    """Base class for chunk-related exceptions."""

    pass


class ChunksTooSlowException(ChunkException):
    """Raised when chunks took too long to be fetched from the cache."""

    def __init__(self, *, chunk_range: ChunkRange, threshold: int) -> None:
        chunk_message = (
            f"Chunks {chunk_range.first_chunk.index}-{chunk_range.last_chunk.index}"
            if len(chunk_range.chunks) > 1
            else f"Chunk {chunk_range.first_chunk.index}"
        )

        super().__init__(
            f"{chunk_message} took too long to fetch, exceeding threshold of {threshold}s."
        )

        self.chunk_range = chunk_range
        self.threshold = threshold
