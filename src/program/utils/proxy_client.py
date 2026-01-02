import httpx
import sniffio
from httpx._client import UseClientDefault
from httpx._types import AuthTypes

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
        super().__init__(
            http2=True,
            proxy=proxy_url,
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
