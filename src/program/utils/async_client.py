import httpx
from loguru import logger

from program.settings.manager import settings_manager


def trace_log(event_name, info):
    logger.log("NETWORK", f"{event_name} - {info}")


class AsyncClient(httpx.AsyncClient):
    def __init__(self) -> None:
        enable_network_tracing = settings_manager.settings.enable_network_tracing

        hooks = (
            {
                "request": [self.log_request],
                "response": [self.log_response, self.raise_on_4xx_5xx],
            }
            if enable_network_tracing
            else None
        )

        super().__init__(
            http2=True,
            follow_redirects=True,
            limits=httpx.Limits(
                max_keepalive_connections=100,
                max_connections=1000,
                keepalive_expiry=60,
            ),
            event_hooks=hooks,
        )

    async def raise_on_4xx_5xx(self, response: httpx.Response) -> None:
        """Raise an error if the response status code indicates an error."""

        response.raise_for_status()

    async def log_request(self, request: httpx.Request) -> None:
        """Log the HTTP request details.

        Args:
            request (httpx.Request): The HTTP request to log.
        """
        logger.log(
            "NETWORK",
            f"Request event hook: {request.method} {request.url} - Waiting for response",
        )

    async def log_response(self, response: httpx.Response) -> None:
        """Log the HTTP response details.

        Args:
            response (httpx.Response): The HTTP response to log.
        """

        logger.log(
            "NETWORK",
            f"Response event hook: {response.request.method} {response.request.url} - Status {response.status_code}",
        )
