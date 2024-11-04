import json
import logging
from types import SimpleNamespace
from typing import Optional
from requests import Session
from lxml import etree
from requests.adapters import HTTPAdapter
from requests.exceptions import ConnectTimeout, RequestException
from requests.models import Response
from requests_cache import CacheMixin, CachedSession
from requests_ratelimiter import LimiterMixin, SQLiteBucket, LimiterSession, MemoryQueueBucket, MemoryListBucket
from pyrate_limiter import RequestRate, Duration, Limiter
from urllib3.util.retry import Retry
from xmltodict import parse as parse_xml

from program.utils import data_dir_path

logger = logging.getLogger(__name__)

class RateLimitExceeded(Exception):
    """Rate limit exceeded exception"""
    def __init__(self, message, response=None):
        super().__init__(message)
        self.response = response

class ResponseObject:
    """Response object to handle different response formats."""
    def __init__(self, response: Response, response_type=SimpleNamespace):
        self.response = response
        self.is_ok = response.ok
        self.status_code = response.status_code
        self.response_type = response_type
        self.data = self.handle_response(response)

    def handle_response(self, response: Response) -> dict:
        """Parse the response content based on content type."""
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

class CachedLimiterSession(CacheMixin, LimiterMixin, Session):
    """Session class with caching and rate-limiting behavior."""
    pass

def create_service_session(
        rate_limit_params: Optional[dict] = None,
        use_cache: bool = False,
        cache_params: Optional[dict] = None
) -> Session:
    """
    Create a session for a specific service with optional caching and rate-limiting.

    :param rate_limit_params: Dictionary of rate-limiting parameters.
    :param use_cache: Boolean indicating if caching should be enabled.
    :param cache_params: Dictionary of caching parameters if caching is enabled.
    :return: Configured session for the service.
    """
    if use_cache and not cache_params:
        raise ValueError("Cache parameters must be provided if use_cache is True.")

    if use_cache and cache_params:
        if rate_limit_params:
            return CachedLimiterSession(**rate_limit_params, **cache_params)
        else:
            return CachedSession(**cache_params)

    if rate_limit_params:
        return LimiterSession(**rate_limit_params)

    return Session()

def _handle_request_exception() -> ResponseObject:
    """Handle exceptions during requests and return a default ResponseObject."""
    logger.error("Request failed", exc_info=True)
    mock_response = SimpleNamespace(ok=False, status_code=500, content={}, headers={})
    return ResponseObject(mock_response)

def _make_request(
        session: Session,
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
) -> ResponseObject:
    if retry_if_failed:
        retry_strategy = Retry(total=3, backoff_factor=0.1, status_forcelist=[500, 502, 503, 504])
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)

    try:
        response = session.request(
            method, url, headers=additional_headers, data=data, params=params, timeout=timeout, proxies=proxies,
            json=json
        )
    except RequestException as e:
        logger.error(f"Request failed: {e}", exc_info=True)
        response = _handle_request_exception()
    finally:
        session.close()

    return ResponseObject(response, response_type)

def ping(session: Session, url: str, timeout: int = 10, additional_headers=None, proxies=None, params=None) -> ResponseObject:
    """Ping method to check connectivity to a URL by making a simple GET request."""
    return get(session=session, url=url, timeout=timeout, additional_headers=additional_headers, proxies=proxies, params=params)


from pyrate_limiter import RequestRate, Duration, Limiter, MemoryQueueBucket, MemoryListBucket
from requests_ratelimiter import SQLiteBucket
from typing import Optional


def get_rate_limit_params(
        per_second=None,
        per_minute=None,
        per_hour=None,
        calculated_rate=None,
        max_calls: Optional[int] = None,
        period: Optional[int] = None,
        db_name: Optional[str] = None,
        use_memory_list: bool = False
) -> dict:
    """
    Generate rate limit parameters for a service. If `db_name` is not provided,
    use an in-memory bucket for rate limiting.

    :param per_second: Requests per second limit.
    :param per_minute: Requests per minute limit.
    :param per_hour: Requests per hour limit.
    :param calculated_rate: Optional calculated rate for requests per minute.
    :param max_calls: Maximum calls allowed in a specified period.
    :param period: Time period in seconds for max_calls.
    :param db_name: Optional name for the SQLite database file for persistent rate limiting.
    :param use_memory_list: If true, use MemoryListBucket instead of MemoryQueueBucket for in-memory limiting.
    :return: Dictionary with rate limit configuration.
    """
    # Choose bucket type based on whether db_name is provided
    if db_name:
        bucket_class = SQLiteBucket
        bucket_kwargs = {"path": data_dir_path / f"{db_name}.db"}
    else:
        bucket_class = MemoryListBucket if use_memory_list else MemoryQueueBucket
        bucket_kwargs = {}

    # Set up the limiter based on available rate parameters
    if max_calls and period:
        limiter = Limiter(RequestRate(max_calls, Duration.SECOND * period))
        return {'limiter': limiter, 'bucket_class': bucket_class, 'bucket_kwargs': bucket_kwargs}
    elif calculated_rate:
        return {'per_minute': calculated_rate, 'bucket_class': bucket_class, 'bucket_kwargs': bucket_kwargs}
    else:
        limit_key = ('per_second' if per_second else 'per_minute' if per_minute else 'per_hour' if per_hour else None)
        if not limit_key:
            raise ValueError("One of max_calls and period, per_second, per_minute, or per_hour must be provided.")
        return {limit_key: locals()[limit_key], 'bucket_class': bucket_class, 'bucket_kwargs': bucket_kwargs}


def get_cache_params(cache_name: str = 'cache', expire_after: Optional[int] = 60) -> dict:
    """Generate cache parameters for a service, ensuring the cache file is in the specified directory."""
    cache_path = data_dir_path / f"{cache_name}.db"
    return {'cache_name': cache_path, 'expire_after': expire_after}

def xml_to_simplenamespace(xml_string: str) -> SimpleNamespace:
    root = etree.fromstring(xml_string)
    def element_to_simplenamespace(element):
        children_as_ns = {child.tag: element_to_simplenamespace(child) for child in element}
        attributes = {key: value for key, value in element.attrib.items()}
        attributes.update(children_as_ns)
        return SimpleNamespace(**attributes, text=element.text)
    return element_to_simplenamespace(root)

# HTTP method wrappers
def get(session: Session, url: str, **kwargs) -> ResponseObject:
    return _make_request(session, "GET", url, **kwargs)

def post(session: Session, url: str, **kwargs) -> ResponseObject:
    return _make_request(session, "POST", url, **kwargs)

def put(session: Session, url: str, **kwargs) -> ResponseObject:
    return _make_request(session, "PUT", url, **kwargs)

def delete(session: Session, url: str, **kwargs) -> ResponseObject:
    return _make_request(session, "DELETE", url, **kwargs)
