import json
import logging
from contextlib import nullcontext
from types import SimpleNamespace
from typing import Optional

import requests
from lxml import etree
from requests.adapters import HTTPAdapter
from requests.exceptions import ConnectTimeout, RequestException
from urllib3.util.retry import Retry
from xmltodict import parse as parse_xml
from utils.useragents import user_agent_factory
from utils.ratelimiter import RateLimiter, RateLimitExceeded

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
        rate_limit_statuses = [429]
        client_error_statuses = list(range(400, 451))  # 400-450
        server_error_statuses = list(range(500, 512))  # 500-511

        if self.status_code in timeout_statuses:
            raise ConnectTimeout(f"Connection timed out with status {self.status_code}", response=response)
        if self.status_code in rate_limit_statuses:
            raise RateLimitExceeded(f"Rate Limit Exceeded {self.status_code}", response=response)
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
        json=None,
        specific_rate_limiter: Optional[RateLimiter] = None,
        overall_rate_limiter: Optional[RateLimiter] = None
) -> ResponseObject:
    session = requests.Session()
    if retry_if_failed:
        session.mount("http://", _adapter)
        session.mount("https://", _adapter)
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": user_agent_factory.get_random_user_agent()
    }
    if additional_headers:
        headers.update(additional_headers)

    specific_context = specific_rate_limiter if specific_rate_limiter else nullcontext()
    overall_context = overall_rate_limiter if overall_rate_limiter else nullcontext()

    try:
        with overall_context:
            with specific_context:
                response = session.request(
                    method, url, headers=headers, data=data, params=params, timeout=timeout, proxies=proxies, json=json
                )
    except requests.exceptions.RequestException as e:
        logger.error(f"Request failed: {e}", exc_info=True)
        response = _handle_request_exception()
    finally:
        session.close()

    return ResponseObject(response, response_type)


def ping(
        url: str,
        timeout=10,
        additional_headers=None,
        proxies=None,
        specific_rate_limiter: Optional[RateLimiter] = None,
        overall_rate_limiter: Optional[RateLimiter] = None):
    return get(
        url,
        additional_headers=additional_headers,
        timeout=timeout,
        proxies=proxies,
        specific_rate_limiter=specific_rate_limiter,
        overall_rate_limiter=overall_rate_limiter)


def get(
        url: str,
        timeout=10,
        data=None,
        params=None,
        additional_headers=None,
        retry_if_failed=True,
        response_type=SimpleNamespace,
        proxies=None,
        json=None,
        specific_rate_limiter: Optional[RateLimiter] = None,
        overall_rate_limiter: Optional[RateLimiter] = None
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
        json=json,
        specific_rate_limiter=specific_rate_limiter,
        overall_rate_limiter=overall_rate_limiter
    )


def post(
        url: str,
        data: Optional[dict] = None,
        params: dict = None,
        timeout=10,
        additional_headers=None,
        retry_if_failed=False,
        proxies=None,
        json: Optional[dict] = None,
        specific_rate_limiter: Optional[RateLimiter] = None,
        overall_rate_limiter: Optional[RateLimiter] = None
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
        json=json,
        specific_rate_limiter=specific_rate_limiter,
        overall_rate_limiter=overall_rate_limiter
    )


def put(
        url: str,
        data: dict = None,
        timeout=10,
        additional_headers=None,
        retry_if_failed=False,
        proxies=None,
        json=None,
        specific_rate_limiter: Optional[RateLimiter] = None,
        overall_rate_limiter: Optional[RateLimiter] = None
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
        json=json,
        specific_rate_limiter=specific_rate_limiter,
        overall_rate_limiter=overall_rate_limiter
    )


def delete(
        url: str,
        timeout=10,
        data=None,
        additional_headers=None,
        retry_if_failed=False,
        proxies=None,
        json=None,
        specific_rate_limiter: Optional[RateLimiter] = None,
        overall_rate_limiter: Optional[RateLimiter] = None
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
        json=json,
        specific_rate_limiter=specific_rate_limiter,
        overall_rate_limiter=overall_rate_limiter
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