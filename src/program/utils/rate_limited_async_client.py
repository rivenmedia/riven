import ssl
import httpx
import httpx_retries

from loguru import logger
from httpx_limiter.async_rate_limited_transport import AsyncRateLimitedTransport
from httpx_limiter.abstract_rate_limiter_repository import AbstractRateLimiterRepository
from httpx_limiter.rate import Rate

from program.settings.manager import settings_manager


class RateLimitedAsyncClient(httpx.AsyncClient):
    def __init__(
        self,
        *,
        base_url: str | None = None,
        rate_limit: Rate,
        proxy: httpx.Proxy | None = None,
        retry: httpx_retries.Retry | None = None,
    ) -> None:
        ctx = ssl.create_default_context()

        super().__init__(
            http2=True,
            follow_redirects=True,
            limits=httpx.Limits(
                max_connections=200,
                max_keepalive_connections=100,
                keepalive_expiry=60.0,
            ),
            timeout=httpx.Timeout(
                connect=5.0,
                read=30.0,
                write=10.0,
                pool=5.0,
            ),
            event_hooks={
                "response": [self.raise_on_4xx_5xx],
            },
            verify=ctx,
            proxy=proxy,
            transport=httpx_retries.RetryTransport(
                transport=AsyncRateLimitedTransport.create(rate=rate_limit),
                retry=retry,
            ),
        )

        if base_url:
            self.base_url = httpx.URL(base_url)

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
