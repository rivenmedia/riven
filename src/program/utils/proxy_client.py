import httpx
import sniffio
from httpx._client import UseClientDefault
from httpx._types import AuthTypes

from program.utils.async_client import _should_force_asyncio_sniffio

# Sentinel for default values
USE_CLIENT_DEFAULT = UseClientDefault()


class ProxyClient(httpx.AsyncClient):
    """
    Async HTTP client configured for asyncio with proxy support.

    Uses sniffio's contextvar to force asyncio backend detection during requests.
    This prevents conflicts when trio is imported by other modules (pyfuse3/VFS)
    but we're running in an asyncio context (FastAPI/uvicorn).
    """

    def __init__(self, *, proxy_url: str) -> None:
        token = (
            sniffio.current_async_library_cvar.set("asyncio")
            if _should_force_asyncio_sniffio()
            else None
        )
        try:
            super().__init__(
                http2=True,
                proxy=proxy_url,
                timeout=httpx.Timeout(120.0, connect=30.0, read=120.0),
            )
        finally:
            if token is not None:
                sniffio.current_async_library_cvar.reset(token)

    async def send(
        self,
        request: httpx.Request,
        *,
        stream: bool = False,
        auth: AuthTypes | UseClientDefault | None = USE_CLIENT_DEFAULT,
        follow_redirects: bool | UseClientDefault = USE_CLIENT_DEFAULT,
    ) -> httpx.Response:
        """
        On the asyncio (uvicorn) thread, force sniffio to asyncio. On the Trio
        (FUSE) thread, do not override.
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
