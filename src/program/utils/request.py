import json
from enum import Enum
from types import SimpleNamespace
from typing import Dict, Type, Optional, Any
from requests import Session
from lxml import etree
from requests.exceptions import ConnectTimeout, RequestException, HTTPError
from requests.models import Response
from requests_cache import CacheMixin, CachedSession
from requests_ratelimiter import LimiterMixin, LimiterSession
from xmltodict import parse as parse_xml
from loguru import logger
from program.utils import data_dir_path
from pyrate_limiter import RequestRate, Duration, Limiter, MemoryQueueBucket, MemoryListBucket
from requests_ratelimiter import SQLiteBucket


class HttpMethod(Enum):
    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    DELETE = "DELETE"
    PATCH = "PATCH"


class ResponseType(Enum):
    SIMPLE_NAMESPACE = "simple_namespace"
    DICT = "dict"


class BaseRequestParameters:
    """Holds base parameters that may be included in every request."""

    def to_dict(self) -> Dict[str, Any]:
        """Convert all non-None attributes to a dictionary for inclusion in requests."""
        return {key: value for key, value in self.__dict__.items() if value is not None}


class ResponseObject:
    """Response object to handle different response formats."""
    def __init__(self, response: Response, response_type: ResponseType = ResponseType.SIMPLE_NAMESPACE):
        self.response = response
        self.is_ok = response.ok
        self.status_code = response.status_code
        self.response_type = response_type
        self.data = self.handle_response(response, response_type)


    def handle_response(self, response: Response, response_type: ResponseType) -> dict | SimpleNamespace:
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
                if response_type == ResponseType.DICT:
                    return response.json()
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

class BaseRequestHandler:
    def __init__(self, session: Session, response_type: ResponseType = ResponseType.SIMPLE_NAMESPACE, base_url: Optional[str] = None, base_params: Optional[BaseRequestParameters] = None,
                 custom_exception: Optional[Type[Exception]] = None, request_logging: bool = False):
        self.session = session
        self.response_type = response_type
        self.BASE_URL = base_url
        self.BASE_REQUEST_PARAMS = base_params or BaseRequestParameters()
        self.custom_exception = custom_exception or Exception
        self.request_logging = request_logging

    def _request(self, method: HttpMethod, endpoint: str, ignore_base_url: Optional[bool] = None, overriden_response_type: ResponseType = None, **kwargs) -> ResponseObject:
        """Generic request handler with error handling, using kwargs for flexibility."""
        try:
            url = f"{self.BASE_URL}/{endpoint}".rstrip('/') if not ignore_base_url and self.BASE_URL else endpoint

            # Add base parameters to kwargs if they exist
            request_params = self.BASE_REQUEST_PARAMS.to_dict()
            if request_params:
                kwargs.setdefault('params', {}).update(request_params)
            elif 'params' in kwargs and not kwargs['params']:
                del kwargs['params']

            if self.request_logging:
                logger.debug(f"Making request to {url} with kwargs: {kwargs}")

            response = self.session.request(method.value, url, **kwargs)
            response.raise_for_status()

            request_response_type = overriden_response_type or self.response_type

            response_obj = ResponseObject(response=response, response_type=request_response_type)
            if self.request_logging:
                logger.debug(f"ResponseObject: status_code={response_obj.status_code}, data={response_obj.data}")
            return response_obj

        except HTTPError as e:
            if e.response.status_code == 429:
                logger.warning(f"Rate limit hit: {e}")
                raise RateLimitExceeded(f"Rate limit exceeded for {url}", response=e.response) from e
            else:
                logger.error(f"Request failed: {e}")
                raise self.custom_exception(f"Request failed: {e}") from e


class RateLimitExceeded(Exception):
    """Rate limit exceeded exception"""
    def __init__(self, message, response=None):
        super().__init__(message)
        self.response = response

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

    session_kwargs = {}
    if rate_limit_params:
        session_kwargs = {
            'limiter': rate_limit_params['limiter'],
            'bucket_class': rate_limit_params['bucket_class'],
            'bucket_kwargs': rate_limit_params['bucket_kwargs'],
            'limit_statuses': rate_limit_params.get('limit_statuses', [429])
        }

    if use_cache and cache_params:
        session_class = CachedLimiterSession if rate_limit_params else CachedSession
        return session_class(**session_kwargs, **cache_params)

    if rate_limit_params:
        return LimiterSession(**session_kwargs)

    return Session()

def get_rate_limit_params(
        per_second: Optional[int] = None,
        per_minute: Optional[int] = None,
        per_hour: Optional[int] = None,
        calculated_rate: Optional[int] = None,
        max_calls: Optional[int] = None,
        period: Optional[int] = None,
        db_name: Optional[str] = None,
        use_memory_list: bool = False,
        limit_statuses: Optional[list[int]] = None
) -> Dict[str, any]:
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
    :param limit_statuses: Optional list of status codes to track for rate limiting.
    :return: Dictionary with rate limit configuration.
    """
    bucket_class = SQLiteBucket if db_name else (MemoryListBucket if use_memory_list else MemoryQueueBucket)
    bucket_kwargs = {"path": data_dir_path / f"{db_name}.db"} if db_name else {}

    rate_limits = []
    if per_second:
        rate_limits.append(RequestRate(per_second, Duration.SECOND))
    if per_minute:
        rate_limits.append(RequestRate(per_minute, Duration.MINUTE))
    if per_hour:
        rate_limits.append(RequestRate(per_hour, Duration.HOUR))
    if calculated_rate:
        rate_limits.append(RequestRate(calculated_rate, Duration.MINUTE))
    if max_calls and period:
        rate_limits.append(RequestRate(max_calls, Duration.SECOND * period))

    if not rate_limits:
        raise ValueError("At least one rate limit (per_second, per_minute, per_hour, calculated_rate, or max_calls and period) must be specified.")

    limiter = Limiter(*rate_limits, bucket_class=bucket_class, bucket_kwargs=bucket_kwargs)

    return {
        'limiter': limiter,
        'bucket_class': bucket_class,
        'bucket_kwargs': bucket_kwargs,
        'limit_statuses': limit_statuses or [429]
    }


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
