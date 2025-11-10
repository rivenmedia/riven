import httpx


class ProxyClient(httpx.AsyncClient):
    def __init__(self, *, proxy_url: str) -> None:
        super().__init__(
            http2=True,
            proxy=proxy_url,
        )
