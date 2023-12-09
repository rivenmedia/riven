"""Requests wrapper"""
import json
import logging
from multiprocessing import Lock
import time
from types import SimpleNamespace
import requests
from lxml import etree
from urllib3.util.retry import Retry
from requests.adapters import HTTPAdapter
import xmltodict

logger = logging.getLogger(__name__)

_retry_strategy = Retry(
    total=5,
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

    def handle_response(self, response: requests.Response):
        """Handle different types of responses"""
        if not self.is_ok:
            logger.warning("Error: %s %s", response.status_code, response.content)
        if self.status_code not in [200, 201, 204]:
            if self.status_code == 429:
                raise requests.exceptions.RequestException(response.content)
            return {}
        if len(response.content) > 0:
            if "handler error" not in response.text:
                content_type = response.headers.get("Content-Type")
                if "text/xml" in content_type:
                    if self.response_type == dict:
                        return xmltodict.parse(response.content)
                    return _xml_to_simplenamespace(response.content)
                if "application/json" in content_type:
                    if self.response_type == dict:
                        return json.loads(response.content)
                    return json.loads(
                        response.content,
                        object_hook=lambda item: SimpleNamespace(**item),
                    )
        return {}


def _handle_request_exception() -> SimpleNamespace:
    """Handle exceptions during requests and return a namespace object."""
    logger.error("Request failed", exc_info=True)
    return SimpleNamespace(ok=False, data={}, content={}, status_code=500)


def _make_request(
    method: str,
    url: str,
    data: dict = None,
    timeout=5,
    additional_headers=None,
    retry_if_failed=True,
    response_type=SimpleNamespace,
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
            method, url, headers=headers, data=data, timeout=timeout
        )
    except requests.RequestException:
        response = _handle_request_exception()

    session.close()
    return ResponseObject(response, response_type)


def get(
    url: str,
    timeout=10,
    additional_headers=None,
    retry_if_failed=True,
    response_type=SimpleNamespace,
) -> ResponseObject:
    """Requests get wrapper"""
    return _make_request(
        "GET",
        url,
        timeout=timeout,
        additional_headers=additional_headers,
        retry_if_failed=retry_if_failed,
        response_type=response_type,
    )


def post(
    url: str, data: dict, timeout=10, additional_headers=None, retry_if_failed=False
) -> ResponseObject:
    """Requests post wrapper"""
    return _make_request(
        "POST",
        url,
        data=data,
        timeout=timeout,
        additional_headers=additional_headers,
        retry_if_failed=retry_if_failed,
    )


def put(
    url: str,
    data: dict = None,
    timeout=10,
    additional_headers=None,
    retry_if_failed=False,
) -> ResponseObject:
    """Requests put wrapper"""
    return _make_request(
        "PUT",
        url,
        data=data,
        timeout=timeout,
        additional_headers=additional_headers,
        retry_if_failed=retry_if_failed,
    )


def _xml_to_simplenamespace(xml_string):
    root = etree.fromstring(xml_string)

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
    def __init__(self, max_calls, period, raise_on_limit=False):
        self.max_calls = max_calls
        self.period = period
        self.tokens = max_calls
        self.last_call = (
            time.time() - period
        )  # Initialize as if the last call was a "period" ago
        self.lock = Lock()
        self.raise_on_limit = raise_on_limit

    def __enter__(self):
        with self.lock:
            current_time = time.time()
            time_since_last_call = current_time - self.last_call

            # Refill tokens only if the entire period has elapsed
            if time_since_last_call >= self.period:
                self.tokens = self.max_calls

            if self.tokens < 1:
                if self.raise_on_limit:
                    raise RateLimitExceeded("Rate limit exceeded!")
                time_to_sleep = self.period - time_since_last_call
                time.sleep(time_to_sleep)
                # After sleeping, update the last_call to account for the time we just waited
                self.last_call = current_time + time_to_sleep
            else:
                # If we had enough tokens, just consume one and update the last call
                self.tokens -= 1
                self.last_call = current_time

        return self

    def __exit__(self, exc_type, exc_value, traceback):
        pass
