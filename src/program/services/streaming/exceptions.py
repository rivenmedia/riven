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
        difference = expected_length - actual_length

        super().__init__(
            f"Expected raw byte length {expected_length}, but got {actual_length} for request range {range}, "
            f"a difference of {'+' if difference > 0 else '-'}{difference} bytes."
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
        difference = expected_length - actual_length

        super().__init__(
            f"Expected byte length {expected_length}, but got {actual_length}, "
            f"a difference of {'+' if difference > 0 else '-'}{difference} bytes."
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
        actual_position: int,
    ) -> None:
        difference = expected_position - actual_position

        super().__init__(
            f"Expected read position {expected_position}, but got {actual_position}, a difference of {'+' if difference > 0 else '-'}{difference} bytes."
        )

        self.expected_position = expected_position
        self.actual_position = actual_position


class EmptyDataError(MediaStreamException):
    """Raised when no data is returned from a stream read operation."""

    def __init__(self, *, range: tuple[int, int]) -> None:
        super().__init__(
            f"No data returned from stream read operation for range {range}."
        )
