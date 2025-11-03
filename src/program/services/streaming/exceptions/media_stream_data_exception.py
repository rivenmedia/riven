from .media_stream_exception import MediaStreamException


class MediaStreamDataException(MediaStreamException):
    """Base class for streaming-related exceptions."""

    pass


class ByteLengthMismatchException(MediaStreamDataException):
    """Raised when the byte length of a stream does not match the expected length."""

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


class ReadPositionMismatchException(MediaStreamDataException):
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


class EmptyDataException(MediaStreamDataException):
    """Raised when no data is returned from a stream read operation."""

    def __init__(self, *, range: tuple[int, int]) -> None:
        super().__init__(
            f"No data returned from stream read operation for range {range}."
        )


class CacheDataNotFoundException(MediaStreamDataException):
    """Raised when requested cache data is not found."""

    def __init__(self, *, range: tuple[int, int]) -> None:
        super().__init__(f"Data with range {range} not found in the cache.")

        self.range = range
