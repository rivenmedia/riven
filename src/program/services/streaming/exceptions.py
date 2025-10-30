from src.program.services.streaming.chunk_range import ChunkRange


class MediaStreamException(Exception):
    """Base class for streaming-related exceptions."""

    pass


class RawByteLengthMismatchException(MediaStreamException):
    """Raised when the unsliced byte length of a stream does not match the expected length."""

    def __init__(
        self,
        *,
        expected_length: int,
        actual_length: int,
        range: tuple[int, int],
    ) -> None:
        difference = actual_length - expected_length

        super().__init__(
            f"Expected raw byte length {expected_length}, but got {actual_length} for request range {range}, "
            f"a difference of {difference} bytes."
        )

        self.expected_length = expected_length
        self.actual_length = actual_length
        self.range = range


class ByteLengthMismatchException(MediaStreamException):
    """Raised when the byte length of a stream does not match the expected length."""

    def __init__(
        self,
        *,
        expected_length: int,
        actual_length: int,
        range: tuple[int, int],
        slice_range: slice,
    ) -> None:
        difference = actual_length - expected_length

        super().__init__(
            f"Expected byte length {expected_length}, but got {actual_length}, "
            f"a difference of {difference} bytes."
            f"for request range {range} and slice range ({slice_range.start}, {slice_range.stop})."
        )

        self.expected_length = expected_length
        self.actual_length = actual_length
        self.range = range
        self.slice_range = slice_range


class ReadPositionMismatchException(MediaStreamException):
    """Raised when the read position in a stream does not match the expected position."""

    def __init__(
        self,
        *,
        expected_position: int,
        actual_position: int | None,
    ) -> None:
        if actual_position is not None:
            difference = actual_position - expected_position

            super().__init__(
                f"Expected read position {expected_position}, but got {actual_position}, a difference of {difference} bytes."
            )
        else:
            super().__init__(
                f"Expected read position {expected_position}, but got None."
            )

        self.expected_position = expected_position
        self.actual_position = actual_position


class EmptyDataError(MediaStreamException):
    """Raised when no data is returned from a stream read operation."""

    def __init__(self, *, range: tuple[int, int]) -> None:
        super().__init__(
            f"No data returned from stream read operation for range {range}."
        )


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
