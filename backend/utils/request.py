"""Requests wrapper"""
import json
import logging
import time
from multiprocessing import Lock
from types import SimpleNamespace
from typing import Optional

import requests
from lxml import etree
from requests.adapters import HTTPAdapter
from requests.exceptions import ConnectTimeout, RequestException
from urllib3.util.retry import Retry
from xmltodict import parse as parse_xml

logger = logging.getLogger(__name__)

_retry_strategy = Retry(
    total=3,
    backoff_factor=0.1,
    status_forcelist=[500, 502, 503, 504],
)
_adapter = HTTPAdapter(max_retries=_retry_strategy)


class ResponseObject:
    """Response object"""

    def __init__(self, response: requests.Response, response_type=SimpleNamespace):
        self.response = response
        self.is_ok = response.ok
        self.status_code = response.status_code
        self.response_type = response_type
        self.data = self.handle_response(response)

    def handle_response(self, response: requests.Response) -> dict:
        """Handle different types of responses."""
        timeout_statuses = [408, 460, 504, 520, 524, 522, 598, 599]
        client_error_statuses = list(range(400, 451))  # 400-450
        server_error_statuses = list(range(500, 512))  # 500-511

        if self.status_code in timeout_statuses:
            raise ConnectTimeout(f"Connection timed out with status {self.status_code}", response=response)
        if self.status_code in client_error_statuses:
            raise RequestException(f"Client error with status {self.status_code}", response=response)
        if self.status_code in server_error_statuses:
            raise RequestException(f"Server error with status {self.status_code}", response=response)
        if not self.is_ok:
            raise RequestException(f"Request failed with status {self.status_code}", response=response)

        content_type = response.headers.get("Content-Type", "")
        if not content_type or response.content == b"":
            return {}
        
        try:
            if "application/json" in content_type:
                if self.response_type == dict:
                    return json.loads(response.content)
                return json.loads(response.content, object_hook=lambda item: SimpleNamespace(**item))
            elif "application/xml" in content_type or "text/xml" in content_type:
                return xml_to_simplenamespace(response.content)
            elif "application/rss+xml" in content_type or "application/atom+xml" in content_type:
                return parse_xml(response.content)
            else:
                return {}
        except Exception as e:
            logger.error(f"Failed to parse response content: {e}", exc_info=True)
            return {}


def _handle_request_exception() -> SimpleNamespace:
    """Handle exceptions during requests and return a namespace object."""
    logger.error("Request failed", exc_info=True)
    return SimpleNamespace(ok=False, data={}, content={}, status_code=500)


def _make_request(
    method: str,
    url: str,
    data: dict = None,
    params: dict = None,
    timeout=5,
    additional_headers=None,
    retry_if_failed=True,
    response_type=SimpleNamespace,
    proxies=None,
    json=None
) -> ResponseObject:
    session = requests.Session()
    if retry_if_failed:
        session.mount("http://", _adapter)
        session.mount("https://", _adapter)
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if additional_headers:
        headers.update(additional_headers)

    try:
        response = session.request(
            method, url, headers=headers, data=data, params=params, timeout=timeout, proxies=proxies, json=json
        )
    except requests.exceptions.RequestException as e:
        logger.error(f"Request failed: {e}", exc_info=True)
        response = _handle_request_exception()
    finally:
        session.close()

    return ResponseObject(response, response_type)


def ping(url: str, timeout=10, additional_headers=None, proxies=None):
    return requests.Session().get(url, headers=additional_headers, timeout=timeout, proxies=proxies)


def get(
    url: str,
    timeout=10,
    data=None,
    params=None,
    additional_headers=None,
    retry_if_failed=True,
    response_type=SimpleNamespace,
    proxies=None,
    json=None
) -> ResponseObject:
    """Requests get wrapper"""
    return _make_request(
        "GET",
        url,
        data=data,
        params=params,
        timeout=timeout,
        additional_headers=additional_headers,
        retry_if_failed=retry_if_failed,
        response_type=response_type,
        proxies=proxies,
        json=json
    )


def post(
    url: str,
    data: Optional[dict] = None,
    params: dict = None,
    timeout=10,
    additional_headers=None,
    retry_if_failed=False,
    proxies=None,
    json: Optional[dict] = None
) -> ResponseObject:
    """Requests post wrapper"""
    return _make_request(
        "POST",
        url,
        data=data,
        params=params,
        timeout=timeout,
        additional_headers=additional_headers,
        retry_if_failed=retry_if_failed,
        proxies=proxies,
        json=json
    )


def put(
    url: str,
    data: dict = None,
    timeout=10,
    additional_headers=None,
    retry_if_failed=False,
    proxies=None,
    json=None
) -> ResponseObject:
    """Requests put wrapper"""
    return _make_request(
        "PUT",
        url,
        data=data,
        timeout=timeout,
        additional_headers=additional_headers,
        retry_if_failed=retry_if_failed,
        proxies=proxies,
        json=json
    )


def delete(
    url: str,
    timeout=10,
    data=None,
    additional_headers=None,
    retry_if_failed=False,
    proxies=None,
    json=None
) -> ResponseObject:
    """Requests delete wrapper"""
    return _make_request(
        "DELETE",
        url,
        data=data,
        timeout=timeout,
        additional_headers=additional_headers,
        retry_if_failed=retry_if_failed,
        proxies=proxies,
        json=json
    )


def xml_to_simplenamespace(xml_string):
    root = etree.fromstring(xml_string)  # noqa: S320

    def element_to_simplenamespace(element):
        children_as_ns = {
            child.tag: element_to_simplenamespace(child) for child in element
        }
        attributes = {key: value for key, value in element.attrib.items()}
        attributes.update(children_as_ns)
        return SimpleNamespace(**attributes, text=element.text)

    return element_to_simplenamespace(root)

class RateLimitExceeded(Exception):
    pass


class RateLimiter:
    """
    A rate limiter class that limits the number of calls within a specified period.

    Args:
        max_calls (int): The maximum number of calls allowed within the specified period.
        period (float): The time period (in seconds) within which the calls are limited.
        raise_on_limit (bool, optional): Whether to raise an exception when the rate limit is exceeded.
            Defaults to False.

    Attributes:
        max_calls (int): The maximum number of calls allowed within the specified period.
        period (float): The time period (in seconds) within which the calls are limited.
        tokens (int): The number of available tokens for making calls.
        last_call (float): The timestamp of the last call made.
        lock (threading.Lock): A lock used for thread-safety.
        raise_on_limit (bool): Whether to raise an exception when the rate limit is exceeded.

    Methods:
        limit_hit(): Resets the token count to 0, indicating that the rate limit has been hit.
        __enter__(): Enters the rate limiter context and checks if a call can be made.
        __exit__(): Exits the rate limiter context.

    Raises:
        RateLimitExceeded: If the rate limit is exceeded and `raise_on_limit` is set to True.
    """

    def __init__(self, max_calls, period, raise_on_limit=False):
        self.max_calls = max_calls
        self.period = period
        self.tokens = max_calls
        self.last_call = time.time() - period
        self.lock = Lock()
        self.raise_on_limit = raise_on_limit

    def limit_hit(self):
        """
        Resets the token count to 0, indicating that the rate limit has been hit.
        """
        self.tokens = 0

    def __enter__(self):
        """
        Enters the rate limiter context and checks if a call can be made.
        """
        with self.lock:
            current_time = time.time()
            time_elapsed = current_time - self.last_call

            if time_elapsed >= self.period:
                self.tokens = self.max_calls

            if self.tokens <= 0:
                if self.raise_on_limit:
                    raise RateLimitExceeded("Rate limit exceeded")
                time.sleep(self.period - time_elapsed)
                self.last_call = time.time()
                self.tokens = self.max_calls
            else:
                self.tokens -= 1

            self.last_call = current_time
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        """
        Exits the rate limiter context.
        """
