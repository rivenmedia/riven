class DebridServiceException(Exception):
    """Base exception for debrid service errors."""

    pass


class DebridServiceRefusedRangeRequestException(DebridServiceException):
    """Raised when the debrid service refuses a range request."""

    def __init__(self, provider: str) -> None:
        super().__init__(f"{provider} refused range request")

        self.provider = provider


class DebridServiceRangeNotSatisfiableException(DebridServiceException):
    """Raised when the debrid service reports that the requested range is not satisfiable."""

    def __init__(self, provider: str) -> None:
        super().__init__(
            f"{provider} reports that the requested range is not satisfiable"
        )

        self.provider = provider


class DebridServiceUnableToConnectException(DebridServiceException):
    """Raised when the debrid service does not provide a download URL."""

    def __init__(self, provider: str) -> None:
        super().__init__(f"{provider} did not provide a download URL")

        self.provider = provider


class DebridServiceForbiddenException(DebridServiceException):
    """Raised when access to the debrid service is forbidden."""

    def __init__(self, provider: str) -> None:
        super().__init__(f"Access to {provider} is forbidden")

        self.provider = provider


class DebridServiceRateLimitedException(DebridServiceException):
    """Raised when the debrid service rate limits requests."""

    def __init__(self, provider: str) -> None:
        super().__init__(f"{provider} is rate limiting requests")

        self.provider = provider


class DebridServiceServiceUnavailableException(DebridServiceException):
    """Raised when the debrid service reports that the service is unavailable."""

    def __init__(self, provider: str) -> None:
        super().__init__(f"{provider} reports that the service is unavailable")

        self.provider = provider


class DebridServiceFileNotFoundException(DebridServiceException):
    """Raised when a file is not found on the debrid service."""

    def __init__(self, provider: str, path: str) -> None:
        super().__init__(f"File with path '{path}' not found on {provider}")

        self.provider = provider
        self.path = path


class DebridServiceClosedConnectionException(DebridServiceException):
    """Raised when the debrid service closes the connection prematurely."""

    def __init__(self, provider: str) -> None:
        super().__init__(f"{provider} closed the connection prematurely")

        self.provider = provider
