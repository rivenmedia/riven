from collections.abc import Generator
from datetime import datetime
import json
import random
import ssl
import time
import threading
from email.utils import parsedate_to_datetime
from types import SimpleNamespace
from typing import Any, cast
from urllib.parse import urlparse
from contextlib import closing

import httpx
import requests
from loguru import logger
from lxml import etree


class TokenBucket:
    """
    Token bucket for rate limiting (thread-safe).

    Attributes:
        name (str|None): Optional identifier (e.g., host) for trace logging.
        rate (float): Tokens per second.
        capacity (float): Maximum number of tokens in the bucket.
        tokens (float): Current number of tokens (float for precision).
        last_refill (float): Timestamp of last refill (monotonic seconds).
    """

    def __init__(self, rate: float, capacity: float | int, name: str | None = None):
        """Initialize the token bucket."""

        self.name = name
        self.rate: float = float(rate)
        self.capacity: float = float(capacity)
        self.tokens: float = float(capacity)
        self.last_refill: float = time.monotonic()
        self._lock = threading.Lock()

    def _refill(self, now: float | None = None) -> None:
        """Refill tokens based on elapsed time. Caller must hold the lock."""

        if now is None:
            now = time.monotonic()

        elapsed = now - self.last_refill

        if elapsed <= 0:
            return

        self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)
        self.last_refill = now

    def consume(self, tokens: int = 1) -> bool:
        """Attempt to consume tokens atomically; returns True if successful."""

        need = float(tokens)

        with self._lock:
            self._refill()

            if self.tokens >= need:
                self.tokens -= need

                return True

            return False

    def wait(self, tokens: int = 1) -> None:
        """
        Block until enough tokens are available. Uses precise sleep based on
        deficit/rate, releasing the lock during sleep so other threads can progress.
        """

        need = float(tokens)

        while True:
            with self._lock:
                now = time.monotonic()
                self._refill(now)

                if self.tokens >= need:
                    self.tokens -= need
                    return

                # Compute exact time to wait for next available tokens
                deficit = max(0.0, need - self.tokens)
                sleep_for = deficit / self.rate if self.rate > 0 else 0.05

                if self.name:
                    logger.trace(
                        "Rate limit sleep: host={} sleep={:.3f}s deficit={:.3f} rate={:.3f} tokens={:.3f}/{:.0f}",
                        self.name,
                        sleep_for,
                        deficit,
                        self.rate,
                        self.tokens,
                        self.capacity,
                    )

            # Release lock while sleeping to allow other threads to make progress
            time.sleep(sleep_for)


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

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_time: int = 30,
        name: str = "unknown",
    ):
        """Initialize the circuit breaker."""
        self.failure_threshold = failure_threshold
        self.recovery_time = recovery_time
        self.failures = 0
        self.last_failure_time: float | None = None
        self.state = "CLOSED"
        self.name = name

    def before_request(self):
        """
        Check circuit breaker before making a request.

        Raises:
            RuntimeError: If the breaker is OPEN and recovery time not passed.
        """
        if self.state == "OPEN" and self.last_failure_time:
            if (time.monotonic() - self.last_failure_time) > self.recovery_time:
                self.state = "HALF_OPEN"
                logger.debug(f"Breaker for {self.name} HALF_OPEN (probe)")
            else:
                logger.debug(f"Breaker for {self.name} OPEN (fail-fast)")
                raise CircuitBreakerOpen(self.name)

    def after_request(self, success: bool):
        """
        Update circuit breaker state after a request.

        Args:
            success (bool): True if the request succeeded, False otherwise.
        """

        if success:
            if self.state in ("HALF_OPEN", "OPEN"):
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
        logger.info(f"Circuit breaker reset to CLOSED for {self.name}")


class SmartResponse(requests.Response):
    """
    SmartResponse automatically parses JSON/XML/RSS responses into dot-notation objects.

    Attributes:
        _cached_data: Cached parsed data.
    """

    _cached_data: SimpleNamespace | dict[str, Any] | None = None

    @property
    def data(self):
        """
        Lazily parse the response content into a SimpleNamespace object.

        Returns:
            "SimpleNamespace" or dict: Parsed response data.
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
            elif (
                "application/xml" in content_type
                or "text/xml" in content_type
                or "application/rss+xml" in content_type
                or "application/atom+xml" in content_type
            ):
                self._cached_data = self._xml_to_simplenamespace(
                    self.content.decode("utf-8")
                )
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
            children_as_ns = {
                child.tag: element_to_simplenamespace(child) for child in element
            }
            attributes = {key: value for key, value in element.attrib.items()}
            attributes.update(children_as_ns)

            return SimpleNamespace(**attributes, text=element.text)

        return element_to_simplenamespace(root)


class SmartSession:
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
        headers (dict): Default headers applied to all requests (requests-compatible attribute).
    """

    response_class = SmartResponse

    def __init__(
        self,
        base_url: str | None = None,
        rate_limits: dict[str, dict[str, float | int]] | None = None,
        proxies: dict[str, str] | None = None,
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

        # Tuned for higher concurrency and longer keep-alive to reduce reconnect overhead
        self._limits = httpx.Limits(
            max_connections=200,
            max_keepalive_connections=100,
            keepalive_expiry=60.0,
        )

        self._timeout = httpx.Timeout(
            connect=5.0,
            read=30.0,
            write=10.0,
            pool=5.0,
        )

        # Reuse a single SSLContext per session to enable TLS session resumption and avoid repeated CA setup
        self._ssl_context = ssl.create_default_context()

        mounts = None

        if proxies:
            http_proxy = (
                proxies.get("http") or proxies.get("all") or proxies.get("all://")
            )
            https_proxy = proxies.get("https") or http_proxy
            transports = dict[str, Any]()

            if http_proxy:
                transports["http://"] = httpx.HTTPTransport(proxy=http_proxy)

            if https_proxy:
                transports["https://"] = httpx.HTTPTransport(proxy=https_proxy)

            if transports:
                mounts = transports

        self._client = httpx.Client(
            http2=True,
            limits=self._limits,
            timeout=self._timeout,
            verify=self._ssl_context,
            cert=None,
            mounts=mounts or None,
        )

        self.base_url = base_url.rstrip("/") if base_url else None
        self.limiters: dict[str, TokenBucket] = {}
        self.breakers: dict[str, CircuitBreaker] = {}
        self.retries = int(retries)
        self.backoff_factor = float(backoff_factor)

        # requests-compatible attributes that callers may set
        self.proxies = proxies or {}
        self.headers: dict[str, str] = {}
        self.auth = None
        self.cookies = None

        if rate_limits:
            for domain, cfg in rate_limits.items():
                self.limiters[domain] = TokenBucket(
                    rate=cfg.get("rate", 1),
                    capacity=cfg.get("capacity", 5),
                    name=domain,
                )
                self.breakers[domain] = CircuitBreaker(name=domain)

    # --- public API ---
    def request(self, method: str, url: str, **kwargs: Any) -> SmartResponse:
        """
        Make a request with automatic SmartResponse, rate limiting, and circuit breaker.

        Args:
            method (str): HTTP method.
            url (str): Request URL (relative or absolute).
            **kwargs: Additional requests-compatible parameters.

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

        base_headers = dict(self.headers)
        req_headers = kwargs.pop("headers", {})

        if req_headers:
            base_headers.update(req_headers)

        headers = base_headers
        kwargs["headers"] = headers

        # Redirect behavior: requests follows redirects by default on GET; emulate broadly
        follow_redirects = kwargs.pop("allow_redirects", True)

        # Streaming: if stream=True, defer reading content; propagate to httpx
        stream = bool(kwargs.pop("stream", False))

        # Timeout mapping (requests allows float/tuple). httpx accepts Timeout or float seconds.
        timeout_kw = kwargs.pop("timeout", None)

        if isinstance(timeout_kw, (int, float)):
            req_timeout = httpx.Timeout(timeout_kw)
        elif isinstance(timeout_kw, tuple) and timeout_kw:
            # map (connect, read) to httpx
            connect = float(timeout_kw[0]) if len(timeout_kw) >= 1 else 5.0
            read = float(timeout_kw[1]) if len(timeout_kw) >= 2 else 30.0
            req_timeout = httpx.Timeout(connect=connect, read=read)
        else:
            req_timeout = self._client.timeout

        # Security/auth params (per-request verify/cert not supported by httpx; use client-level)
        kwargs.pop("verify", None)
        kwargs.pop("cert", None)

        auth = kwargs.pop("auth", self.auth)
        cookies = kwargs.pop("cookies", self.cookies)

        # Per-request proxies: requests supports this, httpx (version here) does not on request(); emulate via a temporary Client
        per_request_proxies = kwargs.pop("proxies", None)

        # Choose client: default to session client; build a temporary client if per-request proxies specified
        client = self._client
        per_request_client_factory = None
        tmp_client = None

        if per_request_proxies:
            mounts = None

            try:
                http_proxy = (
                    per_request_proxies.get("http")
                    or per_request_proxies.get("all")
                    or per_request_proxies.get("all://")
                )
                https_proxy = per_request_proxies.get("https") or http_proxy
                transports = dict[str, Any]()

                if http_proxy:
                    transports["http://"] = httpx.HTTPTransport(proxy=http_proxy)

                if https_proxy:
                    transports["https://"] = httpx.HTTPTransport(proxy=https_proxy)

                if transports:
                    mounts = transports
            except Exception:
                mounts = None

            # Prefer context manager when not streaming; for streaming we will hand off client closure to resp.close
            if not stream:

                def _make_client():
                    return httpx.Client(
                        http2=True,
                        limits=self._limits,
                        timeout=self._timeout,
                        verify=self._ssl_context,
                        cert=None,
                        mounts=mounts or None,
                    )

                per_request_client_factory = _make_client
            else:
                tmp_client = httpx.Client(
                    http2=True,
                    limits=self._limits,
                    timeout=self._timeout,
                    verify=self._ssl_context,
                    cert=None,
                    mounts=mounts or None,
                )
                client = tmp_client

        # Helper to run the request attempt loop with a given client
        def _run_with_client(active_client: httpx.Client) -> SmartResponse:
            nonlocal tmp_client
            attempt = 0

            while True:
                attempt += 1

                try:
                    if stream:
                        # For streaming, build request and send with stream=True to avoid pre-reading body
                        # Ensure cookies are represented via header if provided
                        if cookies:
                            headers.setdefault(
                                "Cookie",
                                "; ".join(f"{k}={v}" for k, v in cookies.items()),
                            )

                        req = active_client.build_request(
                            method.upper(),
                            url,
                            headers=headers,
                            params=kwargs.get("params"),
                            data=kwargs.get("data"),
                            json=kwargs.get("json"),
                            files=kwargs.get("files"),
                            content=kwargs.get("content"),
                        )

                        hx_resp = active_client.send(
                            req,
                            stream=True,
                            auth=auth,
                            follow_redirects=follow_redirects,
                        )
                    else:
                        hx_resp = active_client.request(
                            method.upper(),
                            url,
                            follow_redirects=follow_redirects,
                            timeout=req_timeout,
                            auth=auth,
                            cookies=cookies,
                            **{k: v for k, v in kwargs.items()},
                        )

                    # Retry on status codes
                    if hx_resp.status_code == 429 or 500 <= hx_resp.status_code < 600:
                        delay = self._compute_retry_delay(hx_resp, attempt)

                        if attempt <= self.retries:
                            time.sleep(delay)
                            continue

                    response = self._to_smart_response(hx_resp, url, stream=stream)

                    # If we used a temporary client for per-request proxies, ensure it closes appropriately
                    if tmp_client is not None:
                        if stream:
                            orig_close = hx_resp.close

                            def _close():
                                try:
                                    orig_close()
                                finally:
                                    try:
                                        tmp_client.close()
                                    except Exception:
                                        pass

                            response.close = _close

                            # Prevent outer finally from closing the client prematurely
                            tmp_client = None
                        else:
                            # Non-streaming: active content is read; defer closing to outer finally or context manager
                            pass

                    success_for_breaker = not (
                        response.status_code == 429 or 500 <= response.status_code < 600
                    )

                    if breaker:
                        breaker.after_request(success_for_breaker)

                    return response

                except httpx.TimeoutException as e:
                    if attempt <= self.retries:
                        time.sleep(self._backoff(attempt))
                        continue

                    if breaker:
                        breaker.after_request(False)

                    self._raise_requests_timeout(e)
                except httpx.RequestError as e:
                    if attempt <= self.retries:
                        time.sleep(self._backoff(attempt))
                        continue

                    if breaker:
                        breaker.after_request(False)

                    self._raise_requests_connection(e)
                except Exception:
                    if breaker:
                        breaker.after_request(False)

                    raise

        if per_request_client_factory is not None:
            # Use context manager so the client is always closed
            with closing(per_request_client_factory()) as pr_client:
                return _run_with_client(pr_client)
        else:
            if tmp_client is not None:
                try:
                    return _run_with_client(tmp_client)
                finally:
                    # Close tmp_client if still owned here (not handed off for streaming)
                    try:
                        tmp_client.close()
                    except Exception:
                        pass
            else:
                return _run_with_client(client)

    def get(self, url: str, **kwargs: Any) -> SmartResponse:
        return self.request("GET", url, **kwargs)

    def post(self, url: str, **kwargs: Any) -> SmartResponse:
        return self.request("POST", url, **kwargs)

    def put(self, url: str, **kwargs: Any) -> SmartResponse:
        return self.request("PUT", url, **kwargs)

    def delete(self, url: str, **kwargs: Any) -> SmartResponse:
        return self.request("DELETE", url, **kwargs)

    def patch(self, url: str, **kwargs: Any) -> SmartResponse:
        return self.request("PATCH", url, **kwargs)

    def head(self, url: str, **kwargs: Any) -> SmartResponse:
        return self.request("HEAD", url, **kwargs)

    def options(self, url: str, **kwargs: Any) -> SmartResponse:
        return self.request("OPTIONS", url, **kwargs)

    def close(self):
        try:
            self._client.close()
        except Exception:
            pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()

    # --- helpers ---
    def _to_smart_response(
        self,
        httpx_response: httpx.Response,
        url: str,
        stream: bool = False,
    ) -> SmartResponse:
        """
        Convert httpx.Response to a SmartResponse (requests.Response subclass).

        If stream is True, avoid pre-reading content and provide lazy access via .content/.iter_content.
        """

        r = requests.Response()
        r.status_code = httpx_response.status_code

        if stream:
            # Do not pre-read body; let .content or .iter_content consume it on demand
            r._content = None  # requests will read from r.raw when content accessed

            class _RawAdapter:
                def __init__(self, resp: httpx.Response):
                    self._resp = resp

                def read(self, *args, **kwargs):
                    # Read full body on-demand; httpx buffers efficiently
                    return self._resp.read()

                def close(self):
                    try:
                        self._resp.close()
                    except Exception:
                        pass

            r.raw = _RawAdapter(httpx_response)

            # Provide iter_content similar to requests
            def _iter_content(
                chunk_size: int | None = 8192,
                decode_unicode: bool = False,
            ) -> Generator[bytes]:
                yield from httpx_response.iter_bytes(chunk_size=chunk_size)

            r.iter_content = _iter_content

            # Ensure context manager closes underlying response
            r.close = httpx_response.close
        else:
            # Non-streaming: read content now and release the connection promptly
            r._content = httpx_response.content or b""

            try:
                httpx_response.close()
            except Exception:
                pass

        try:
            r.headers.update(dict(httpx_response.headers))
        except Exception:
            pass

        r.url = str(httpx_response.request.url)
        r.reason = httpx_response.reason_phrase

        if httpx_response.encoding:
            r.encoding = httpx_response.encoding

        r.__class__ = SmartResponse

        return cast(SmartResponse, r)

    def _compute_retry_delay(
        self, httpx_response: httpx.Response, attempt: int
    ) -> float:
        # Honor Retry-After if present

        try:
            ra = httpx_response.headers.get("Retry-After")
        except Exception:
            ra = None

        if ra:
            try:
                return max(0.0, float(int(ra)))
            except Exception:
                try:
                    dt = cast(datetime | None, parsedate_to_datetime(ra))
                    return max(0.0, float(int(round(dt.timestamp() - time.time()))))
                except Exception:
                    pass
        # Fallback to exponential backoff
        return self._backoff(attempt)

    def _backoff(self, attempt: int) -> float:
        """
        Exponential backoff with equal jitter to reduce thundering herds.

        See: https://aws.amazon.com/blogs/architecture/exponential-backoff-and-jitter/
        """

        base = float(self.backoff_factor) * (2 ** (max(0, attempt - 1)))
        # Equal jitter: random between 50% and 100% of the backoff window
        return base * (0.5 + 0.5 * random.random())

    def _raise_requests_timeout(self, e: httpx.TimeoutException):
        # Map to requests.exceptions.Timeout
        raise requests.exceptions.Timeout(str(e))

    def _raise_requests_connection(self, e: httpx.RequestError):
        # Map to requests.exceptions.ConnectionError (base RequestException)
        raise requests.exceptions.ConnectionError(str(e))


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
