import httpx


class AsyncClient(httpx.AsyncClient):
    def __init__(self) -> None:
        super().__init__(http2=True)
