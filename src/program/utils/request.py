from collections.abc import Generator, Mapping
from datetime import datetime
import json
import random
import ssl
import time
import threading
import httpx
import requests

from email.utils import parsedate_to_datetime
from types import SimpleNamespace
from typing import Any, cast
from urllib.parse import urlparse
from contextlib import closing
from loguru import logger
from lxml import etree

from program.services.rate_limit import (
    CircuitBreakerOpen,
    TokenBucket,
    get_rate_limit_service,
)

# Re-export for backward compatibility
__all__ = [
    "CircuitBreakerOpen",
    "TokenBucket",
    "SmartResponse",
    "SmartSession",
    "get_hostname_from_url",
]


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
            logger.debug(f"Failed to parse response: {e}")
            self._cached_data = {}

        return self._cached_data

    def _xml_to_simplenamespace(self, xml_string: str) -> SimpleNamespace:
        """Convert XML string to SimpleNamespace recursively."""

        def element_to_simplenamespace(element: etree._Element) -> SimpleNamespace:
            children = list(element)
            if not children:
                return SimpleNamespace(text=element.text)

            result: dict[str, Any] = {}
            for child in children:
                child_obj = element_to_simplenamespace(child)
                tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
                if tag in result:
                    if not isinstance(result[tag], list):
                        result[tag] = [result[tag]]
                    result[tag].append(child_obj)
                else:
                    result[tag] = child_obj

            return SimpleNamespace(
                **result,
                text=element.text,
            )

        root = etree.fromstring(xml_string.encode("utf-8"))

        return element_to_simplenamespace(root)


class SmartSession:
    """
    SmartSession adds automatic SmartResponse wrapping, rate limiting, circuit breaker, proxies, and retries.

    Rate limits and circuit breakers are delegated to RateLimitService via rate_limit_map.
    """

    response_class = SmartResponse

    def __init__(
        self,
        base_url: str | None = None,
        rate_limit_map: dict[str, list[str]] | None = None,
        rate_limits: Mapping[str, Mapping[str, float | int]] | None = None,
        proxies: dict[str, str] | None = None,
        retries: int = 3,
        backoff_factor: float = 0.3,
        extra_rate_limit_keys: list[str] | None = None,
    ):
        if rate_limits:
            logger.warning(
                "SmartSession(rate_limits=...) is deprecated; register keys on RateLimitService "
                "and pass rate_limit_map instead"
            )

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
        self.rate_limit_map = dict(rate_limit_map or {})
        self.extra_rate_limit_keys = list(extra_rate_limit_keys or [])
        self.retries = int(retries)
        self.backoff_factor = float(backoff_factor)

        self.proxies = proxies or {}
        self.headers = dict[str, str]()
        self.auth = None
        self.cookies = None

        self._rl = get_rate_limit_service()

    def _resolve_rate_limit_keys(
        self, url: str, rate_limit_keys: list[str] | None
    ) -> list[str]:
        keys: list[str] = list(self.extra_rate_limit_keys)
        if rate_limit_keys:
            keys.extend(rate_limit_keys)
        parsed = urlparse(url)
        domain = parsed.hostname.lower() if parsed.hostname else ""
        if domain and domain in self.rate_limit_map:
            keys.extend(self.rate_limit_map[domain])
        path = (parsed.path or "").lower()
        for pattern, pattern_keys in self.rate_limit_map.items():
            if pattern.startswith("/") and pattern in path:
                keys.extend(pattern_keys)
        # dedupe preserve order
        seen: set[str] = set()
        out: list[str] = []
        for k in keys:
            if k not in seen:
                seen.add(k)
                out.append(k)
        return out

    def request(
        self,
        method: str,
        url: str,
        *,
        rate_limit_keys: list[str] | None = None,
        **kwargs: Any,
    ) -> SmartResponse:
        if self.base_url and not url.lower().startswith(("http://", "https://")):
            url = f"{self.base_url}/{url.lstrip('/')}"

        rl_keys = self._resolve_rate_limit_keys(url, rate_limit_keys)

        base_headers = dict(self.headers)
        req_headers = kwargs.pop("headers", {})

        if req_headers:
            base_headers.update(req_headers)

        headers = base_headers
        kwargs["headers"] = headers

        follow_redirects = kwargs.pop("allow_redirects", True)
        stream = bool(kwargs.pop("stream", False))

        timeout_kw = kwargs.pop("timeout", None)

        if isinstance(timeout_kw, (int, float)):
            req_timeout = httpx.Timeout(timeout_kw)
        elif isinstance(timeout_kw, httpx.Timeout):
            req_timeout = timeout_kw
        else:
            req_timeout = self._client.timeout

        kwargs.pop("verify", None)
        kwargs.pop("cert", None)

        auth = kwargs.pop("auth", self.auth)
        cookies = kwargs.pop("cookies", self.cookies)

        per_request_proxies = kwargs.pop("proxies", None)

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

        def _run_with_client(active_client: httpx.Client) -> SmartResponse:
            nonlocal tmp_client
            attempt = 0

            while True:
                attempt += 1

                if rl_keys:
                    self._rl.enter_many(rl_keys)

                try:
                    if stream:
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

                    if hx_resp.status_code == 429 or 500 <= hx_resp.status_code < 600:
                        delay = self._compute_retry_delay(hx_resp, attempt)

                        if attempt <= self.retries:
                            time.sleep(delay)
                            continue

                    response = self._to_smart_response(hx_resp, url, stream=stream)

                    if tmp_client is not None:
                        if stream:
                            orig_close = hx_resp.close

                            def _close():
                                try:
                                    orig_close()
                                finally:
                                    try:
                                        if tmp_client:
                                            tmp_client.close()
                                    except Exception:
                                        pass

                            response.close = _close
                            tmp_client = None

                    is_rate_limited = (
                        response.status_code == 429
                        or 500 <= response.status_code < 600
                    )

                    if rl_keys:
                        if response.status_code == 429:
                            delay = self._compute_retry_delay(hx_resp, attempt)
                            self._rl.record_many_failure(
                                rl_keys, retry_after=delay
                            )
                        elif 500 <= response.status_code < 600:
                            self._rl.record_many_failure(rl_keys)
                        else:
                            self._rl.record_many_success(rl_keys)

                    return response

                except CircuitBreakerOpen:
                    raise
                except httpx.TimeoutException as e:
                    if attempt <= self.retries:
                        time.sleep(self._backoff(attempt))
                        continue

                    if rl_keys:
                        self._rl.record_many_failure(rl_keys)

                    self._raise_requests_timeout(e)
                except httpx.RequestError as e:
                    if attempt <= self.retries:
                        time.sleep(self._backoff(attempt))
                        continue

                    if rl_keys:
                        self._rl.record_many_failure(rl_keys)

                    self._raise_requests_connection(e)
                except Exception:
                    if rl_keys:
                        self._rl.record_many_failure(rl_keys)
                    raise

        if per_request_client_factory is not None:
            with closing(per_request_client_factory()) as pr_client:
                return _run_with_client(pr_client)
        else:
            if tmp_client is not None:
                try:
                    return _run_with_client(tmp_client)
                finally:
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

    def __exit__(self, exc_type: Any, exc_value: Any, traceback: Any):
        self.close()

    def _to_smart_response(
        self,
        httpx_response: httpx.Response,
        url: str,
        stream: bool = False,
    ) -> SmartResponse:
        r = requests.Response()
        r.status_code = httpx_response.status_code

        if stream:
            r._content = None

            class _RawAdapter:
                def __init__(self, resp: httpx.Response):
                    self._resp = resp

                def read(self, *args: tuple[Any, ...], **kwargs: dict[str, Any]):
                    return self._resp.read()

                def close(self):
                    try:
                        self._resp.close()
                    except Exception:
                        pass

            r.raw = _RawAdapter(httpx_response)

            def _iter_content(
                chunk_size: int | None = 8192,
                decode_unicode: bool = False,
            ) -> Generator[bytes]:
                yield from httpx_response.iter_bytes(chunk_size=chunk_size)

            r.iter_content = _iter_content
            r.close = httpx_response.close
        else:
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
        try:
            ra = httpx_response.headers.get("Retry-After")
        except Exception:
            ra = None

        if ra:
            try:
                return max(0.0, float(int(ra)))
            except Exception:
                try:
                    dt = cast(datetime, parsedate_to_datetime(ra))
                    return max(0.0, float(int(round(dt.timestamp() - time.time()))))
                except Exception:
                    pass

        return self._backoff(attempt)

    def _backoff(self, attempt: int) -> float:
        base = float(self.backoff_factor) * (2 ** (max(0, attempt - 1)))
        return base * (0.5 + 0.5 * random.random())

    def _raise_requests_timeout(self, e: httpx.TimeoutException):
        raise requests.exceptions.Timeout(str(e))

    def _raise_requests_connection(self, e: httpx.RequestError):
        raise requests.exceptions.ConnectionError(str(e))


def get_hostname_from_url(url: str) -> str:
    parsed = urlparse(url)
    return parsed.hostname.lower() if parsed.hostname else ""
