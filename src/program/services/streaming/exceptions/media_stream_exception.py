class MediaStreamException(Exception):
    """Base class for streaming-related exceptions."""

    pass


class FatalMediaStreamException(MediaStreamException):
    """Raised when a fatal error occurs in the media stream."""

    def __init__(self, original_exception: Exception) -> None:
        super().__init__(
            f"A fatal error occurred in the media stream: {original_exception}"
        )

        self.original_exception = original_exception


class RecoverableMediaStreamException(MediaStreamException):
    """Raised when a recoverable error occurs in the media stream."""

    def __init__(self, original_exception: Exception) -> None:
        super().__init__(
            f"A recoverable error occurred in the media stream: {original_exception}"
        )

        self.original_exception = original_exception
