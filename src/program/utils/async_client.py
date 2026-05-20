import asyncio

import httpx
import sniffio
from httpx._client import UseClientDefault
from httpx._types import AuthTypes
from loguru import logger

from program.settings import settings_manager


def _should_force_asyncio_sniffio() -> bool:
    """True only when an asyncio loop is running (API server thread).

    RivenVFS / pyfuse3 runs on a dedicated Trio thread with no asyncio loop.
    Forcing sniffio to \"asyncio\" there makes httpx schedule work on the wrong
    backend and can hang reads forever.
    """
    try:
        asyncio.get_running_loop()
        return True
    except RuntimeError:
        return False


# Sentinel for default values
USE_CLIENT_DEFAULT = UseClientDefault()


class AsyncClient(httpx.AsyncClient):
    """
    Async HTTP client configured for asyncio.

    Uses sniffio's contextvar to force asyncio backend detection during requests
    **only** when running inside uvicorn's asyncio loop. On the Trio-based FUSE
    thread we leave the current async library unchanged so httpx uses Trio.
    """

    def __init__(self) -> None:
        token = (
            sniffio.current_async_library_cvar.set("asyncio")
            if _should_force_asyncio_sniffio()
            else None
        )
        try:
            super().__init__(
                http2=True,
                follow_redirects=True,
                timeout=httpx.Timeout(120.0, connect=30.0, read=120.0),
                limits=httpx.Limits(
                    max_keepalive_connections=100,
                    max_connections=1000,
                    keepalive_expiry=60,
                ),
                event_hooks={"response": [self.raise_on_4xx_5xx]},
            )
        finally:
            if token is not None:
                sniffio.current_async_library_cvar.reset(token)

        enable_network_tracing = settings_manager.settings.enable_network_tracing

        if enable_network_tracing:
            self.event_hooks["request"].append(self.log_request)
            self.event_hooks["response"].append(self.log_response)

    async def raise_on_4xx_5xx(self, response: httpx.Response) -> None:
        """Raise an error if the response status code indicates an error."""

        # Do not use raise_for_status() as-is: it treats 3xx as errors. Response
        # hooks run on redirect responses before httpx follows them; e.g. TorBox
        # requestdl URLs return 307 to a CDN and would abort the redirect chain.
        if response.is_error:
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
        On the asyncio (uvicorn) thread, force sniffio to asyncio so Trio import
        does not steal httpx's backend. On the Trio (FUSE) thread, do not override.
        """
        if not _should_force_asyncio_sniffio():
            return await super().send(
                request,
                stream=stream,
                auth=auth,
                follow_redirects=follow_redirects,
            )

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

    async def aclose(self) -> None:
        """Close the client using the backend that matches the running loop.

        The shared DI client is used from both uvicorn (asyncio) and RivenVFS
        (trio). Lifespan shutdown runs on asyncio; without forcing sniffio here,
        httpx may try to close trio sockets from the wrong async context.
        """
        if not _should_force_asyncio_sniffio():
            await super().aclose()
            return

        token = sniffio.current_async_library_cvar.set("asyncio")
        try:
            await super().aclose()
        except RuntimeError as exc:
            if "async context" not in str(exc):
                raise
            logger.warning(
                "Skipping AsyncClient graceful close: Trio-backed connections "
                "cannot be torn down from the asyncio lifespan"
            )
        finally:
            sniffio.current_async_library_cvar.reset(token)
