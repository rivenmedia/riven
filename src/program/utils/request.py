import time
import json
from loguru import logger
from types import SimpleNamespace
from typing import Optional, Dict
from collections import deque
from urllib.parse import urlparse

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from lxml import etree


class TokenBucket:
    """
    Token bucket for rate limiting.

    This implements a classic token bucket algorithm with a queue
    for housekeeping of consumed tokens.

    Attributes:
        rate (float): Tokens per second.
        capacity (int): Maximum number of tokens in the bucket.
        tokens (int): Current number of tokens.
        last_refill (float): Timestamp of last refill.
        queue (deque): Queue of timestamps for consumed tokens.
    """

    def __init__(self, rate: float, capacity: int):
        """Initialize the token bucket."""
        self.rate = rate
        self.capacity = capacity
        self.tokens = capacity
        self.last_refill = time.monotonic()
        self.queue = deque()

    def consume(self, tokens: int = 1) -> bool:
        """
        Consume tokens from the bucket.

        Args:
            tokens (int): Number of tokens to consume.

        Returns:
            bool: True if tokens were successfully consumed, False otherwise.
        """
        self._refill()
        if self.tokens >= tokens:
            self.tokens -= tokens
            self.queue.append(time.monotonic())
            return True
        return False

    def wait(self, tokens: int = 1):
        """
        Block until enough tokens are available.

        Args:
            tokens (int): Number of tokens to consume.
        """
        while not self.consume(tokens):
            time.sleep(0.05)

    def _refill(self):
        """Refill tokens based on elapsed time."""
        now = time.monotonic()
        elapsed = now - self.last_refill
        refill = elapsed * self.rate
        if refill >= 1:
            self.tokens = min(self.capacity, self.tokens + int(refill))
            self.last_refill = now

    def cleanup(self, ttl: float = 60):
        """
        Clean up expired token timestamps from the queue.

        Args:
            ttl (float): Time-to-live in seconds for old tokens.
        """
        now = time.monotonic()
        expired = 0
        while self.queue and (now - self.queue[0]) >= ttl:
            self.queue.popleft()
            expired += 1
        if expired:
            logger.debug(f"Cleaned up {expired} expired tokens")


class CircuitBreakerOpen(RuntimeError):
    """Raised when a circuit breaker is OPEN and requests should fail fast."""
    def __init__(self, name: str):
        super().__init__(f"Circuit breaker OPEN for {name}")
        self.name = name


class CircuitBreaker:
    """
    Circuit breaker for per-domain failure handling.

    Attributes:
        failure_threshold (int): Number of failures before tripping.
        recovery_time (int): Seconds to wait before attempting recovery.
        failures (int): Current failure count.
        last_failure_time (float): Timestamp of last failure.
        state (str): Current state: 'CLOSED', 'OPEN', 'HALF_OPEN'.
    """

    def __init__(self, failure_threshold: int = 5, recovery_time: int = 30, name: str = "unknown"):
        """Initialize the circuit breaker."""
        self.failure_threshold = failure_threshold
        self.recovery_time = recovery_time
        self.failures = 0
        self.last_failure_time: Optional[float] = None
        self.state = "CLOSED"
        self.name = name

    def before_request(self):
        """
        Check circuit breaker before making a request.

        Raises:
            RuntimeError: If the breaker is OPEN and recovery time not passed.
        """
        if self.state == "OPEN":
            if (time.monotonic() - self.last_failure_time) > self.recovery_time:
                self.state = "HALF_OPEN"
                logger.info(f"Breaker for {self.name} HALF_OPEN (probe)")
            else:
                logger.warning(f"Breaker for {self.name} OPEN (fail-fast)")
                # raise a specific exception so callers can abort the whole operation
                raise CircuitBreakerOpen(self.name)

    def after_request(self, success: bool):
        """
        Update circuit breaker state after a request.

        Args:
            success (bool): True if the request succeeded, False otherwise.
        """
        if success:
            if self.state in ("HALF_OPEN", "OPEN"):
                logger.debug(f"Circuit breaker reset to CLOSED for {self.name}")
                self._reset()
        else:
            self.failures += 1
            self.last_failure_time = time.monotonic()
            if self.failures >= self.failure_threshold:
                self.state = "OPEN"
                logger.warning(f"Circuit breaker tripped to OPEN for {self.name}")

    def _reset(self):
        """Reset the circuit breaker to CLOSED state."""
        self.failures = 0
        self.state = "CLOSED"
        self.last_failure_time = None
        logger.debug(f"Circuit breaker reset to CLOSED for {self.name}")


class SmartResponse(requests.Response):
    """
    SmartResponse automatically parses JSON/XML/RSS responses into dot-notation objects.

    Attributes:
        _cached_data: Cached parsed data.
    """

    _cached_data = None

    @property
    def data(self):
        """
        Lazily parse the response content into a SimpleNamespace object.

        Returns:
            SimpleNamespace or dict: Parsed response data.
        """
        if self._cached_data is not None:
            return self._cached_data

        content_type = self.headers.get("Content-Type", "")
        if not content_type or self.content == b"":
            self._cached_data = {}
            return self._cached_data

        try:
            if "application/json" in content_type:
                self._cached_data = json.loads(
                    self.content, object_hook=lambda d: SimpleNamespace(**d)
                )
            elif "application/xml" in content_type or "text/xml" in content_type:
                self._cached_data = self._xml_to_simplenamespace(self.content)
            elif "application/rss+xml" in content_type or "application/atom+xml" in content_type:
                self._cached_data = self._xml_to_simplenamespace(self.content)
            else:
                self._cached_data = {}
        except Exception as e:
            logger.error(f"Failed to parse response content: {e}", exc_info=True)
            self._cached_data = {}

        return self._cached_data

    def _xml_to_simplenamespace(self, xml_string: str) -> SimpleNamespace:
        """
        Convert XML string to SimpleNamespace object.

        Args:
            xml_string (str): XML content.

        Returns:
            SimpleNamespace: Parsed XML.
        """
        root = etree.fromstring(xml_string)

        def element_to_simplenamespace(element):
            children_as_ns = {child.tag: element_to_simplenamespace(child) for child in element}
            attributes = {key: value for key, value in element.attrib.items()}
            attributes.update(children_as_ns)
            return SimpleNamespace(**attributes, text=element.text)

        return element_to_simplenamespace(root)


class SmartSession(requests.Session):
    """
    SmartSession adds automatic SmartResponse wrapping, rate limiting, circuit breaker, proxies, and retries.

    Attributes:
        base_url (str): Optional base URL; relative request URLs will be resolved against this.
        rate_limits (dict): Optional per-domain rate limits, e.g., {"api.example.com": {"rate": 1, "capacity": 5}}.
        proxies (dict): Optional dictionary of HTTP/HTTPS proxies.
        retries (int): Number of retries for failed requests.
        backoff_factor (float): Backoff factor for retries.
        response_class (type): Response class to wrap requests.
        limiters (dict): Per-domain TokenBucket instances.
        breakers (dict): Per-domain CircuitBreaker instances.
    """

    response_class = SmartResponse

    def __init__(
        self,
        base_url: Optional[str] = None,
        rate_limits: Optional[Dict[str, Dict[str, int]]] = None,
        proxies: Optional[Dict[str, str]] = None,
        retries: int = 3,
        backoff_factor: float = 0.3,
    ):
        """
        Initialize SmartSession.

        Args:
            base_url (str): Optional base URL; relative request URLs will be resolved against this.
            rate_limits (dict): Optional per-domain rate limits, e.g., {"api.example.com": {"rate": 1, "capacity": 5}}.
            proxies (dict): Optional dictionary of HTTP/HTTPS proxies.
            retries (int): Number of retries for failed requests.
            backoff_factor (float): Backoff factor for retries.
        """
        super().__init__()

        adapter = HTTPAdapter(
            pool_connections=50,
            pool_maxsize=100,
            pool_block=True,
            max_retries=Retry(
                total=retries,
                backoff_factor=backoff_factor,
                status_forcelist=[429, 500, 502, 503, 504],
            )
        )
        self.mount("http://", adapter)
        self.mount("https://", adapter)

        self.base_url = base_url.rstrip("/") if base_url else None
        self.limiters: Dict[str, TokenBucket] = {}
        self.breakers: Dict[str, CircuitBreaker] = {}

        if rate_limits:
            for domain, cfg in rate_limits.items():

                self.limiters[domain] = TokenBucket(
                    rate=cfg.get("rate", 1), capacity=cfg.get("capacity", 5)
                )
                self.breakers[domain] = CircuitBreaker(name=domain)

        if proxies:
            self.proxies.update(proxies)

    def request(self, method: str, url: str, **kwargs) -> SmartResponse:
        """
        Make a request with automatic SmartResponse, rate limiting, and circuit breaker.

        Args:
            method (str): HTTP method.
            url (str): Request URL (relative or absolute).
            **kwargs: Additional requests.Session parameters.

        Returns:
            SmartResponse: Parsed response object.
        """
        if self.base_url and not url.lower().startswith(("http://", "https://")):
            url = f"{self.base_url}/{url.lstrip('/')}"

        parsed = urlparse(url)
        domain = parsed.hostname.lower() if parsed.hostname else ""

        breaker = self.breakers.get(domain)
        if breaker:
            breaker.before_request()

        limiter = self.limiters.get(domain)
        if limiter:
            limiter.wait()

        try:
            resp: SmartResponse = super().request(method, url, **kwargs)
            resp.__class__ = SmartResponse
            if breaker:
                breaker.after_request(resp.ok)
            return resp
        except Exception:
            if breaker:
                breaker.after_request(False)
            raise

def get_hostname_from_url(url: str) -> str:
    """
    Extract the hostname from a URL.

    Args:
        url (str): URL string.

    Returns:
        str: Lowercase hostname.
    """
    parsed = urlparse(url)
    return parsed.hostname.lower() if parsed.hostname else ""
