import httpx
import sniffio
from httpx._client import UseClientDefault
from httpx._types import AuthTypes
from loguru import logger

from program.settings import settings_manager

# Sentinel for default values
USE_CLIENT_DEFAULT = UseClientDefault()


class AsyncClient(httpx.AsyncClient):
    """
    Async HTTP client configured for asyncio.

    Uses sniffio's contextvar to force asyncio backend detection during requests.
    This prevents conflicts when trio is imported by other modules (pyfuse3/VFS)
    but we're running in an asyncio context (FastAPI/uvicorn).
    """

    def __init__(self) -> None:
        super().__init__(
            http2=True,
            follow_redirects=True,
            limits=httpx.Limits(
                max_keepalive_connections=100,
                max_connections=1000,
                keepalive_expiry=60,
            ),
            event_hooks={"response": [self.raise_on_4xx_5xx]},
        )

        enable_network_tracing = settings_manager.settings.enable_network_tracing

        if enable_network_tracing:
            self.event_hooks["request"].append(self.log_request)
            self.event_hooks["response"].append(self.log_response)

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

    async def send(
        self,
        request: httpx.Request,
        *,
        stream: bool = False,
        auth: AuthTypes | UseClientDefault | None = USE_CLIENT_DEFAULT,
        follow_redirects: bool | UseClientDefault = USE_CLIENT_DEFAULT,
    ) -> httpx.Response:
        """
        Send a request with forced asyncio backend detection.

        This override ensures that sniffio reports 'asyncio' as the current
        async library during the request, preventing runtime conflicts when
        trio is also imported in the process (e.g., by pyfuse3 for VFS).
        """
        token = sniffio.current_async_library_cvar.set("asyncio")
        try:
            return await super().send(
                request,
                stream=stream,
                auth=auth,
                follow_redirects=follow_redirects,
            )
        finally:
            sniffio.current_async_library_cvar.reset(token)
