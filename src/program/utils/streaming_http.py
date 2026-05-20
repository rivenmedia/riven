"""HTTP clients for VFS / MediaStream (Trio thread only).

Kept separate from the FastAPI lifespan ``di[AsyncClient]`` so uvicorn shutdown
does not close connections while FUSE is still streaming.
"""

from __future__ import annotations

import threading

import trio
from loguru import logger

from program.settings import settings_manager
from program.utils.async_client import AsyncClient
from program.utils.proxy_client import ProxyClient

_lock = threading.Lock()
_streaming_client: AsyncClient | None = None
_streaming_proxy_client: ProxyClient | None = None


def get_streaming_async_client() -> AsyncClient:
    with _lock:
        global _streaming_client
        if _streaming_client is None:
            _streaming_client = AsyncClient()
        return _streaming_client


def get_streaming_proxy_client() -> ProxyClient:
    proxy_url = settings_manager.settings.downloaders.proxy_url
    if not proxy_url:
        raise RuntimeError("Proxy URL is not configured")

    with _lock:
        global _streaming_proxy_client
        if _streaming_proxy_client is None:
            _streaming_proxy_client = ProxyClient(proxy_url=proxy_url)
        return _streaming_proxy_client


async def close_streaming_http_clients() -> None:
    with _lock:
        clients: list[AsyncClient | ProxyClient] = []
        global _streaming_client, _streaming_proxy_client
        if _streaming_client is not None:
            clients.append(_streaming_client)
            _streaming_client = None
        if _streaming_proxy_client is not None:
            clients.append(_streaming_proxy_client)
            _streaming_proxy_client = None

    for client in clients:
        try:
            await client.aclose()
        except Exception:
            logger.exception("Error closing streaming HTTP client")


def close_streaming_http_sync() -> None:
    with _lock:
        if _streaming_client is None and _streaming_proxy_client is None:
            return

    try:
        import pyfuse3

        token = pyfuse3.trio_token
        if token is not None:
            trio.from_thread.run(close_streaming_http_clients, trio_token=token)
            return
    except Exception:
        pass

    trio.run(close_streaming_http_clients)
