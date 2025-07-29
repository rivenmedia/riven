import json
import hashlib
import time
from enum import Enum
from threading import RLock
from types import SimpleNamespace
from typing import Any, Dict, Optional, Type

from loguru import logger
from lxml import etree
from pyrate_limiter import (
    Duration,
    Limiter,
    MemoryListBucket,
    MemoryQueueBucket,
    RequestRate,
)
from requests import Session
from requests.adapters import HTTPAdapter
from requests.exceptions import ConnectTimeout, HTTPError, RequestException
from requests.models import Response
from requests_cache import CachedSession, CacheMixin
from requests_ratelimiter import (
    LimiterAdapter,
    LimiterMixin,
    LimiterSession,
    SQLiteBucket,
)
from urllib3.util.retry import Retry
from xmltodict import parse as parse_xml

from program.utils import data_dir_path


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
    """Response object to handle different response formats.

    :param response: The response object to parse.
    :param response_type: The response type to parse the content as.
    """

    def __init__(self, response: Response, response_type: ResponseType = ResponseType.SIMPLE_NAMESPACE):
        self.response = response
        self.is_ok = response.ok
        self.status_code = response.status_code
        self.response_type = response_type
        self.data = self.handle_response(response, response_type)


    def handle_response(self, response: Response, response_type: ResponseType) -> dict | SimpleNamespace:
        """Parse the response content based on content type.

        :param response: The response object to parse.
        :param response_type: The response type to parse the content as.
        :return: Parsed response content.
        """

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
    """Base request handler for services.

    :param session: The session to use for requests.
    :param response_type: The response type to parse the content as.
    :param base_url: Optional base URL to use for requests.
    :param base_params: Optional base parameters to include in requests.
    :param custom_exception: Optional custom exception to raise on request failure.
    :param request_logging: Boolean indicating if request logging should be enabled.
    """
    def __init__(self, session: Session | LimiterSession, response_type: ResponseType = ResponseType.SIMPLE_NAMESPACE, base_url: Optional[str] = None, base_params: Optional[BaseRequestParameters] = None,
                 custom_exception: Optional[Type[Exception]] = None, request_logging: bool = False):
        self.session = session
        self.response_type = response_type
        self.BASE_URL = base_url
        self.BASE_REQUEST_PARAMS = base_params or BaseRequestParameters()
        self.custom_exception = custom_exception or Exception
        self.request_logging = request_logging
        self.timeout = 15

    def _request(self, method: HttpMethod, endpoint: str, ignore_base_url: Optional[bool] = None, overriden_response_type: ResponseType = None, **kwargs) -> ResponseObject:
        """Generic request handler with error handling, using kwargs for flexibility.

        :param method: HTTP method to use for the request.
        :param endpoint: Endpoint to request.
        :param ignore_base_url: Boolean indicating if the base URL should be ignored.
        :param overriden_response_type: Optional response type to use for the request.
        :param retry_policy: Optional retry policy to use for the request.
        :param kwargs: Additional parameters to pass to the request.
        :return: ResponseObject with the response data.
        """
        try:
            url = f"{self.BASE_URL}/{endpoint}".rstrip('/') if not ignore_base_url and self.BASE_URL else endpoint

            request_params = self.BASE_REQUEST_PARAMS.to_dict()
            if request_params:
                kwargs.setdefault('params', {}).update(request_params)
            elif 'params' in kwargs and not kwargs['params']:
                del kwargs['params']

            kwargs.setdefault("timeout", self.timeout)

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
            if e.response is not None and e.response.status_code == 429:
                # Extract retry-after header if available
                retry_after = e.response.headers.get('Retry-After')
                if retry_after:
                    try:
                        retry_delay = int(retry_after)
                        logger.warning(f"Rate limited for {url}, server suggests waiting {retry_delay}s")
                    except ValueError:
                        retry_delay = None
                else:
                    retry_delay = None

                raise RateLimitExceeded(f"Rate limit exceeded for {url}", response=e.response, retry_after=retry_delay) from e
            else:
                raise self.custom_exception(f"Request failed: {e}") from e


class RateLimitExceeded(Exception):
    """Rate limit exceeded exception for requests with enhanced retry information."""
    def __init__(self, message, response=None, retry_after=None):
        super().__init__(message)
        self.response = response
        self.retry_after = retry_after  # Server-suggested retry delay in seconds
        self.should_retry = True  # Flag indicating this is a retryable error
        self.suggested_delay = retry_after or 30  # Default 30s delay if no server suggestion


class CircuitBreaker:
    """
    Generic circuit breaker for API rate limiting and failure management.
    Prevents overwhelming services that are experiencing issues.
    """
    def __init__(self, failure_threshold=5, recovery_timeout=300, service_name="Unknown"):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.service_name = service_name
        self.failure_count = 0
        self.last_failure_time = None
        self.state = "CLOSED"  # CLOSED, OPEN, HALF_OPEN

    def can_execute(self):
        """Check if requests can be executed based on circuit breaker state"""
        if self.state == "CLOSED":
            return True
        elif self.state == "OPEN":
            if self.last_failure_time:
                from datetime import datetime, timedelta
                if datetime.now() - self.last_failure_time > timedelta(seconds=self.recovery_timeout):
                    self.state = "HALF_OPEN"
                    logger.debug(f"Circuit breaker for {self.service_name} moving to HALF_OPEN state")
                    return True
            return False
        else:  # HALF_OPEN
            return True

    def record_success(self):
        """Record a successful request - resets failure count and closes circuit"""
        if self.failure_count > 0 or self.state != "CLOSED":
            logger.debug(f"Circuit breaker for {self.service_name} recording success - resetting to CLOSED")
        self.failure_count = 0
        self.state = "CLOSED"

    def record_failure(self):
        """Record a failed request - may trip circuit breaker"""
        self.failure_count += 1
        from datetime import datetime
        self.last_failure_time = datetime.now()

        if self.failure_count >= self.failure_threshold:
            self.state = "OPEN"
            logger.warning(f"Circuit breaker for {self.service_name} OPEN - too many failures ({self.failure_count}/{self.failure_threshold})")
        else:
            logger.debug(f"Circuit breaker for {self.service_name} recorded failure {self.failure_count}/{self.failure_threshold}")

    def get_status(self):
        """Get current circuit breaker status for monitoring"""
        return {
            'state': self.state,
            'failure_count': self.failure_count,
            'last_failure_time': self.last_failure_time,
            'service_name': self.service_name
        }


class TTLCache:
    """
    Generic Time-To-Live cache for API responses and availability checks.
    Thread-safe with automatic expiration cleanup.
    """
    def __init__(self, ttl: int = 300, max_size: int = 1000):
        self._cache = {}
        self._lock = RLock()
        self._ttl = ttl
        self._max_size = max_size

    def get(self, key: str):
        """Get cached result if available and not expired."""
        with self._lock:
            if key in self._cache:
                result, timestamp = self._cache[key]
                if time.time() - timestamp < self._ttl:
                    return result
                else:
                    del self._cache[key]
        return None

    def set(self, key: str, value):
        """Cache result with TTL expiration."""
        with self._lock:
            # Clean up if cache is getting too large
            if len(self._cache) >= self._max_size:
                self._cleanup_expired()

            self._cache[key] = (value, time.time())

    def _cleanup_expired(self):
        """Remove expired entries from cache."""
        current_time = time.time()
        expired_keys = [
            key for key, (_, timestamp) in self._cache.items()
            if current_time - timestamp >= self._ttl
        ]
        for key in expired_keys:
            del self._cache[key]

    def clear(self):
        """Clear all cached entries."""
        with self._lock:
            self._cache.clear()

    def size(self):
        """Get current cache size."""
        with self._lock:
            return len(self._cache)


class DeduplicationMixin:
    """Mixin to add request deduplication with very short TTL for live data."""

    def __init__(self, *args, dedup_ttl: int = 3, **kwargs):
        super().__init__(*args, **kwargs)
        self.dedup_ttl = dedup_ttl  # Short TTL in seconds for live data
        self._dedup_cache = {}  # In-memory cache for deduplication

    def _get_request_key(self, method: str, url: str, **kwargs) -> str:
        """Generate a unique key for the request."""
        # Include method, url, and relevant parameters
        key_data = {
            'method': method.upper(),
            'url': url,
            'params': kwargs.get('params', {}),
            'data': kwargs.get('data', {}),
            'json': kwargs.get('json', {}),
        }
        key_string = json.dumps(key_data, sort_keys=True)
        return hashlib.md5(key_string.encode()).hexdigest()

    def _cleanup_expired_entries(self):
        """Remove expired entries from deduplication cache."""
        current_time = time.time()
        expired_keys = [
            key for key, (timestamp, _) in self._dedup_cache.items()
            if current_time - timestamp > self.dedup_ttl
        ]
        for key in expired_keys:
            del self._dedup_cache[key]

    def request(self, method: str, url: str, **kwargs):
        """Override request method to add deduplication."""
        # Clean up expired entries periodically
        self._cleanup_expired_entries()

        # Generate request key
        request_key = self._get_request_key(method, url, **kwargs)
        current_time = time.time()

        # Check if we have a recent response for this exact request
        if request_key in self._dedup_cache:
            timestamp, response = self._dedup_cache[request_key]
            if current_time - timestamp <= self.dedup_ttl:
                logger.debug(f"Returning deduplicated response for {method} {url}")
                return response

        # Make the actual request
        response = super().request(method, url, **kwargs)

        # Store the response for deduplication (only for successful requests)
        if response.status_code < 400:
            self._dedup_cache[request_key] = (current_time, response)

        return response


class CachedLimiterSession(CacheMixin, LimiterMixin, Session):
    """Session class with caching and rate-limiting behavior."""
    pass


class DeduplicatedSession(DeduplicationMixin, Session):
    """Session class with request deduplication for live data."""
    pass


class DeduplicatedLimiterSession(DeduplicationMixin, LimiterMixin, Session):
    """Session class with request deduplication and rate-limiting for live data."""
    pass

def create_service_session(
        rate_limit_params: Optional[dict] = None,
        use_cache: bool = False,
        cache_params: Optional[dict] = None,
        use_deduplication: bool = False,
        dedup_ttl: int = 3,
        session_adapter: Optional[HTTPAdapter | LimiterAdapter] = None,
        retry_policy: Optional[Retry] = None,
        log_config: Optional[bool] = False,
) -> Session | CachedSession | CachedLimiterSession | DeduplicatedSession | DeduplicatedLimiterSession:
    """
    Create a session for a specific service with optional caching, rate-limiting, and deduplication.

    :param rate_limit_params: Dictionary of rate-limiting parameters.
    :param use_cache: Boolean indicating if caching should be enabled.
    :param cache_params: Dictionary of caching parameters if caching is enabled.
    :param use_deduplication: Boolean indicating if request deduplication should be enabled for live data.
    :param dedup_ttl: Time-to-live for deduplication cache in seconds.
    :param session_adapter: Optional custom HTTP adapter to use for the session.
    :param retry_policy: Optional retry policy to use for the session.
    :param log_config: Boolean indicating if the session configuration should be logged.
    :return: Configured session for the service.
    """
    if use_cache and not cache_params:
        raise ValueError("Cache parameters must be provided if use_cache is True.")

    # Caching takes precedence over deduplication (for static data)
    if use_cache and cache_params:
        if log_config:
            logger.debug(f"Rate Limit Parameters: {rate_limit_params}")
            logger.debug(f"Cache Parameters: {cache_params}")
        session_class = CachedLimiterSession if rate_limit_params else CachedSession
        cache_session = session_class(**rate_limit_params, **cache_params)
        _create_and_mount_session_adapter(cache_session, session_adapter, retry_policy, log_config)
        return cache_session

    # Deduplication for live data (short TTL)
    if use_deduplication:
        if log_config:
            logger.debug(f"Rate Limit Parameters: {rate_limit_params}")
            logger.debug(f"Deduplication TTL: {dedup_ttl}s")

        if rate_limit_params:
            dedup_session = DeduplicatedLimiterSession(dedup_ttl=dedup_ttl, **rate_limit_params)
        else:
            dedup_session = DeduplicatedSession(dedup_ttl=dedup_ttl)

        _create_and_mount_session_adapter(dedup_session, session_adapter, retry_policy, log_config)
        return dedup_session

    # Standard rate-limited or basic session
    if rate_limit_params:
        if log_config:
            logger.debug(f"Rate Limit Parameters: {rate_limit_params}")
        limiter_session = LimiterSession(**rate_limit_params)
        _create_and_mount_session_adapter(limiter_session, session_adapter, retry_policy, log_config)
        return limiter_session

    standard_session = Session()
    _create_and_mount_session_adapter(standard_session, session_adapter, retry_policy, log_config)
    return standard_session


def get_rate_limit_params(
        custom_limiter: Optional[Limiter] = None,
        per_second: Optional[int] = None,
        per_minute: Optional[int] = None,
        per_hour: Optional[int] = None,
        calculated_rate: Optional[int] = None,
        max_calls: Optional[int] = None,
        period: Optional[int] = None,
        db_name: Optional[str] = None,
        use_memory_list: bool = False,
        limit_statuses: Optional[list[int]] = None,
        max_delay: Optional[int] = 0,

) -> Dict[str, any]:
    """
    Generate rate limit parameters for a service. If `db_name` is not provided,
    use an in-memory bucket for rate limiting.

    :param custom_limiter: Optional custom limiter to use for rate limiting.
    :param per_second: Requests per second limit.
    :param per_minute: Requests per minute limit.
    :param per_hour: Requests per hour limit.
    :param calculated_rate: Optional calculated rate for requests per minute.
    :param max_calls: Maximum calls allowed in a specified period.
    :param period: Time period in seconds for max_calls.
    :param db_name: Optional name for the SQLite database file for persistent rate limiting.
    :param use_memory_list: If true, use MemoryListBucket instead of MemoryQueueBucket for in-memory limiting.
    :param limit_statuses: Optional list of status codes to track for rate limiting.
    :param max_delay: Optional maximum delay for rate limiting.
    :return: Dictionary with rate limit configuration.
    """

    # Optimize bucket selection for performance
    if db_name:
        # Use SQLite for persistent rate limiting (longer periods)
        bucket_class = SQLiteBucket
        bucket_kwargs = {"path": data_dir_path / f"{db_name}.db"}
    elif use_memory_list:
        # Use MemoryListBucket for high-frequency, short-term limits (better for live data)
        bucket_class = MemoryListBucket
        bucket_kwargs = {}
    else:
        # Use MemoryQueueBucket for moderate frequency limits
        bucket_class = MemoryQueueBucket
        bucket_kwargs = {}

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

    limiter = custom_limiter or Limiter(*rate_limits, bucket_class=bucket_class, bucket_kwargs=bucket_kwargs)

    return {
        'limiter': limiter,
        'bucket_class': bucket_class,
        'bucket_kwargs': bucket_kwargs,
        'limit_statuses': limit_statuses or [429],
        'max_delay': max_delay,
    }


def get_cache_params(cache_name: str = 'cache', expire_after: Optional[int] = 60) -> dict:
    """Generate cache parameters for a service, ensuring the cache file is in the specified directory.

    :param cache_name: The name of the cache file excluding the extension.
    :param expire_after: The time in seconds to expire the cache.
    :return: Dictionary with cache configuration.
    """
    cache_path = data_dir_path / f"{cache_name}.db"
    return {'cache_name': cache_path, 'expire_after': expire_after}


def get_optimized_rate_limit_params(service_type: str = "default") -> dict:
    """
    Get optimized rate limiting parameters for different service types to maximize throughput.

    :param service_type: Type of service ('scraper', 'debrid', 'indexer', 'api', 'default')
    :return: Optimized rate limit parameters
    """
    # Optimized configurations for maximum live data throughput
    configs = {
        'scraper': {
            # High throughput for scrapers (Torrentio, Mediafusion, etc.)
            'per_second': 10,  # Aggressive rate for live data
            'per_minute': 300,  # Allow bursts
            'use_memory_list': True,  # Faster bucket for short-term limits
            'max_delay': 2,  # Short delays to maintain responsiveness
        },
        'debrid': {
            # Optimized for debrid services (RealDebrid allows 250/min)
            'per_second': 3,    # Allow bursts up to 3/second
            'per_minute': 200,  # Conservative buffer under RealDebrid's 250/min
            'per_hour': 10000,  # Generous hourly limit
            'use_memory_list': True,
            'max_delay': 60,    # Allow longer delays for recovery from rate limits
        },
        'indexer': {
            # Balanced for indexers (Trakt, TVDB, etc.)
            'per_second': 3,  # Conservative for metadata APIs
            'per_minute': 100,
            'per_hour': 3000,  # Respect hourly limits
            'use_memory_list': False,  # Use persistent bucket for longer limits
            'max_delay': 10,
        },
        'api': {
            # General API services
            'per_second': 2,
            'per_minute': 60,
            'per_hour': 1000,
            'use_memory_list': False,
            'max_delay': 15,
        },
        'default': {
            # Conservative default
            'per_second': 1,
            'per_minute': 30,
            'use_memory_list': True,
            'max_delay': 5,
        }
    }

    config = configs.get(service_type, configs['default'])
    return get_rate_limit_params(**config)


def create_service_rate_limiter(service_name: str, service_type: str = "default") -> Dict[str, any]:
    """
    Create optimized rate limiter configuration for specific services.

    :param service_name: Specific service name (e.g., 'realdebrid', 'alldebrid')
    :param service_type: General service type fallback
    :return: Rate limiter configuration with circuit breaker
    """
    # Service-specific configurations based on real API limits
    service_configs = {
        'realdebrid': {
            'per_second': 3,
            'per_minute': 200,    # Conservative under 250/min limit
            'per_hour': 10000,
            'use_memory_list': True,
            'max_delay': 60,
            'circuit_breaker': CircuitBreaker(
                failure_threshold=10,
                recovery_timeout=120,
                service_name='Real-Debrid'
            )
        },
        'alldebrid': {
            'per_second': 5,
            'per_minute': 300,    # AllDebrid is more lenient
            'per_hour': 15000,
            'use_memory_list': True,
            'max_delay': 30,
            'circuit_breaker': CircuitBreaker(
                failure_threshold=8,
                recovery_timeout=90,
                service_name='AllDebrid'
            )
        },
        'torrentio': {
            'per_second': 8,
            'per_minute': 400,
            'use_memory_list': True,
            'max_delay': 10,
            'circuit_breaker': CircuitBreaker(
                failure_threshold=5,
                recovery_timeout=60,
                service_name='Torrentio'
            )
        },
        'trakt': {
            'per_second': 2,
            'per_minute': 60,
            'per_hour': 2000,
            'use_memory_list': False,
            'max_delay': 15,
            'circuit_breaker': CircuitBreaker(
                failure_threshold=5,
                recovery_timeout=180,
                service_name='Trakt'
            )
        }
    }

    # Get service-specific config or fall back to type-based config
    config = service_configs.get(service_name.lower())
    if not config:
        config = get_optimized_rate_limit_params(service_type)
        # Add a generic circuit breaker
        config['circuit_breaker'] = CircuitBreaker(
            failure_threshold=5,
            recovery_timeout=300,
            service_name=service_name
        )
        return config

    # Extract circuit breaker before creating rate limit params
    circuit_breaker = config.pop('circuit_breaker')
    rate_limit_config = get_rate_limit_params(**config)
    rate_limit_config['circuit_breaker'] = circuit_breaker

    return rate_limit_config


def create_adaptive_session(service_name: str, service_type: str = "default", **kwargs) -> Session:
    """
    Create an adaptive session that optimizes rate limiting for maximum live data throughput.

    :param service_name: Name of the service for logging
    :param service_type: Type of service for rate limit optimization
    :param kwargs: Additional session parameters
    :return: Optimized session for the service
    """
    # Get optimized rate limiting parameters
    rate_limit_params = get_optimized_rate_limit_params(service_type)

    # Use deduplication for live data (short TTL to prevent duplicate requests)
    dedup_ttl = 3 if service_type in ['scraper', 'debrid'] else 5

    # Create optimized session
    session = create_service_session(
        rate_limit_params=rate_limit_params,
        use_deduplication=True,
        dedup_ttl=dedup_ttl,
        log_config=False,  # Reduce logging overhead
        **kwargs
    )

    logger.debug(f"Created adaptive session for {service_name} ({service_type}) with optimized rate limiting")
    return session


def get_retry_policy(retries: int = 3, backoff_factor: float = 0.3, status_forcelist: Optional[list[int]] = None) -> Retry:
    """
    Create a retry policy for requests.

    :param retries: The maximum number of retry attempts.
    :param backoff_factor: A backoff factor to apply between attempts.
    :param status_forcelist: A list of HTTP status codes that we should force a retry on.
    :return: Configured Retry object.
    """
    return Retry(total=retries, backoff_factor=backoff_factor, status_forcelist=status_forcelist or [500, 502, 503, 504])


def get_http_adapter(
        retry_policy: Optional[Retry] = None,
        pool_connections: Optional[int] = 100,  # Increased for better connection reuse
        pool_maxsize: Optional[int] = 200,      # Increased for high-throughput live data
        pool_block: Optional[bool] = False      # Don't block to avoid delays with live data
) -> HTTPAdapter:
    """
    Create an HTTP adapter with retry policy and optimized connection pooling for live data.

    :param retry_policy: The retry policy to use for the adapter.
    :param pool_connections: The number of connection pools to allow (increased for live data).
    :param pool_maxsize: The maximum number of connections to keep in the pool (increased for throughput).
    :param pool_block: Boolean indicating if the pool should block when full (disabled for live data).
    """
    adapter_kwargs = {
        'max_retries': retry_policy,
        'pool_connections': pool_connections,
        'pool_maxsize': pool_maxsize,
        'pool_block': pool_block,
    }
    return HTTPAdapter(**adapter_kwargs)


def xml_to_simplenamespace(xml_string: str) -> SimpleNamespace:
    """Convert an XML string to a SimpleNamespace object."""
    root = etree.fromstring(xml_string)
    def element_to_simplenamespace(element):
        children_as_ns = {child.tag: element_to_simplenamespace(child) for child in element}
        attributes = {key: value for key, value in element.attrib.items()}
        attributes.update(children_as_ns)
        return SimpleNamespace(**attributes, text=element.text)
    return element_to_simplenamespace(root)


def _create_and_mount_session_adapter(
        session: Session,
        adapter_instance: Optional[HTTPAdapter] = None,
        retry_policy: Optional[Retry] = None,
        log_config: Optional[bool] = False):
    """
    Create and mount an HTTP adapter to a session with optimized settings for live data.

    :param session: The session to mount the adapter to.
    :param retry_policy: The retry policy to use for the adapter.
    """
    adapter = adapter_instance or get_http_adapter(retry_policy)
    session.mount("https://", adapter)
    session.mount("http://", adapter)

    # Optimize session headers for better connection reuse and live data performance
    session.headers.update({
        'Connection': 'keep-alive',
        'Keep-Alive': 'timeout=30, max=100',  # Keep connections alive longer
        'User-Agent': 'Riven/1.0 (Live Data Optimized)',
    })

    if log_config:
        logger.debug(f"Mounted http adapter with params: {adapter.__dict__} to session.")
