import time
from unittest.mock import patch

import pytest
import responses
from requests.exceptions import HTTPError

from program.utils.request import (
    BaseRequestHandler,
    HttpMethod,
    RateLimitExceeded,
    ResponseType,
    create_service_session,
    get_http_adapter,
    get_rate_limit_params,
    get_retry_policy,
)


@responses.activate
def test_rate_limiter_with_base_request_handler():
    # Setup: Define the URL and rate-limiting parameters
    url = "https://api.example.com/endpoint"
    rate_limit_params = get_rate_limit_params(per_second=1)  # 1 request per second as an example
    session = create_service_session(rate_limit_params=rate_limit_params)

    # Initialize the BaseRequestHandler with the rate-limited session
    request_handler = BaseRequestHandler(session=session, response_type=ResponseType.DICT, base_url=url)

    for _ in range(3):
        responses.add(responses.GET, url, json={"message": "OK"}, status=200)

    for _ in range(5):
        responses.add(responses.GET, url, json={"error": "Rate limit exceeded"}, status=429)

    success_count = 0
    rate_limited_count = 0

    for i in range(8):
        try:
            # Use BaseRequestHandler's _request method
            response_obj = request_handler._request(HttpMethod.GET, "")
            print(f"Request {i + 1}: Status {response_obj.status_code} - Success")
            success_count += 1
        except RateLimitExceeded as e:
            print(f"Request {i + 1}: Rate limit hit - {e}")
            rate_limited_count += 1
        except HTTPError as e:
            print(f"Request {i + 1}: Failed with error - {e}")
        time.sleep(0.1)  # Interval shorter than rate limit threshold

    # Assertions
    assert success_count == 3, "Expected 3 successful requests before rate limiting"
    assert rate_limited_count == 5, "Expected 5 rate-limited requests after threshold exceeded"


@responses.activate
def test_successful_requests_within_limit():
    """Test that requests succeed if within the rate limit."""
    url = "https://api.example.com/endpoint"
    rate_limit_params = get_rate_limit_params(per_second=2)  # 2 requests per second
    session = create_service_session(rate_limit_params=rate_limit_params)
    request_handler = BaseRequestHandler(session=session, response_type=ResponseType.DICT, base_url=url)

    # Mock responses for the first 2 requests
    responses.add(responses.GET, url, json={"message": "OK"}, status=200)
    responses.add(responses.GET, url, json={"message": "OK"}, status=200)

    success_count = 0

    for i in range(2):
        response_obj = request_handler._request(HttpMethod.GET, "")
        print(f"Request {i + 1}: Status {response_obj.status_code} - Success")
        success_count += 1

    assert success_count == 2, "Expected both requests to succeed within the rate limit"


@responses.activate
def test_rate_limit_exceeded():
    """Test that requests are blocked after rate limit is reached."""
    url = "https://api.example.com/endpoint"
    rate_limit_params = get_rate_limit_params(per_second=1)  # 1 request per second
    session = create_service_session(rate_limit_params=rate_limit_params)
    request_handler = BaseRequestHandler(session=session, response_type=ResponseType.DICT, base_url=url)

    # First request is mocked as 200 OK, subsequent as 429
    responses.add(responses.GET, url, json={"message": "OK"}, status=200)
    responses.add(responses.GET, url, json={"error": "Rate limit exceeded"}, status=429)

    # First request should succeed
    success_count = 0
    rate_limited_count = 0

    try:
        response_obj = request_handler._request(HttpMethod.GET, "")
        print(f"Request 1: Status {response_obj.status_code} - Success")
        success_count += 1
    except RateLimitExceeded:
        rate_limited_count += 1

    # Second request should be rate-limited
    try:
        request_handler._request(HttpMethod.GET, "")
    except RateLimitExceeded as e:
        print("Request 2: Rate limit hit -", e)
        rate_limited_count += 1

    assert success_count == 1, "Expected the first request to succeed"
    assert rate_limited_count == 1, "Expected the second request to be rate-limited"


@responses.activate
def test_rate_limit_reset():
    """Test that requests succeed after waiting for the rate limit to reset."""
    url = "https://api.example.com/endpoint"
    rate_limit_params = get_rate_limit_params(per_second=1)  # 1 request per second
    session = create_service_session(rate_limit_params=rate_limit_params)
    request_handler = BaseRequestHandler(session=session, response_type=ResponseType.DICT, base_url=url)

    # Mock the first request with 200 OK
    responses.add(responses.GET, url, json={"message": "OK"}, status=200)

    # Mock the second request with 429 to simulate rate limit
    responses.add(responses.GET, url, json={"error": "Rate limit exceeded"}, status=429)

    # Mock the third request after rate limit reset with 200 OK
    responses.add(responses.GET, url, json={"message": "OK"}, status=200)

    success_count = 0
    rate_limited_count = 0

    # First request should succeed
    try:
        response_obj = request_handler._request(HttpMethod.GET, "")
        print(f"Request 1: Status {response_obj.status_code} - Success")
        success_count += 1
    except RateLimitExceeded:
        rate_limited_count += 1

    # Second request immediately should be rate-limited
    try:
        request_handler._request(HttpMethod.GET, "")
    except RateLimitExceeded as e:
        print("Request 2: Rate limit hit -", e)
        rate_limited_count += 1

    # Wait for the rate limit to reset, then try again
    time.sleep(1.1)
    try:
        response_obj = request_handler._request(HttpMethod.GET, "")
        print(f"Request 3: Status {response_obj.status_code} - Success after reset")
        success_count += 1
    except RateLimitExceeded:
        rate_limited_count += 1

    assert success_count == 2, "Expected two successful requests (first and after reset)"
    assert rate_limited_count == 1, "Expected one rate-limited request (second request)"


def test_direct_rate_limiter():
    """Test the Limiter directly to confirm it enforces rate limiting."""
    from pyrate_limiter import Duration, Limiter, RequestRate

    rate_limits = []
    rate_limits.append(RequestRate(1, Duration.SECOND))
    rate_limits.append(RequestRate(60, Duration.MINUTE))
    limiter = Limiter(*rate_limits)  # 1 request per second and 60 requests per minute

    success_count = 0
    rate_limited_count = 0

    # First request should succeed
    try:
        limiter.try_acquire("test_key")
        print("Request 1: Success")
        success_count += 1
    except Exception as e:
        print("Request 1: Rate limit hit")
        rate_limited_count += 1

    # Additional requests should be rate-limited
    for i in range(4):
        try:
            limiter.try_acquire("test_key")
            print(f"Request {i + 2}: Success")
            success_count += 1
        except Exception as e:
            print(f"Request {i + 2}: Rate limit hit")
            rate_limited_count += 1
        time.sleep(0.2)  # Short interval to exceed rate limit

    # Assertions
    assert success_count == 1, "Expected only one successful request within the rate limit"
    assert rate_limited_count >= 1, "Expected at least one rate-limited request after hitting the limit"


def test_limiter_session_with_basic_rate_limit():
    """Test a basic LimiterSession that enforces a rate limit of 5 requests per second."""
    rate_limit_params = get_rate_limit_params(per_second=1)
    session = create_service_session(rate_limit_params=rate_limit_params)
    start = time.time()
    request_count = 20
    interval_limit = 5
    buffer_time = 0.8

    # Store timestamps to analyze intervals
    request_timestamps = []

    # Send 20 requests, observing the time intervals to confirm rate limiting
    for i in range(request_count):
        response = session.get('https://httpbin.org/get')
        current_time = time.time()
        request_timestamps.append(current_time)
        print(f'[t+{current_time - start:.2f}] Sent request {i + 1} - Status code: {response.status_code}')

        # Check time intervals every 5 requests to confirm rate limiting is applied
        if (i + 1) % interval_limit == 0:
            elapsed_time = request_timestamps[-1] - request_timestamps[-interval_limit]
            assert elapsed_time >= 1 - buffer_time, (
                f"Rate limit exceeded: {interval_limit} requests in {elapsed_time:.2f} seconds"
            )

    # Final assertion to ensure all requests respected the rate limit
    total_elapsed_time = request_timestamps[-1] - request_timestamps[0]
    expected_min_time = (request_count / interval_limit) - buffer_time
    assert total_elapsed_time >= expected_min_time, (
        f"Test failed: Expected at least {expected_min_time:.2f} seconds "
        f"for {request_count} requests, got {total_elapsed_time:.2f} seconds"
    )

@pytest.fixture
def retry_policy():
    return get_retry_policy(retries=5, backoff_factor=0.5, status_forcelist=[500, 502, 503, 504])

@pytest.fixture
def connection_pool_params():
    return {
        'pool_connections': 20,
        'pool_maxsize': 50,
        'pool_block': True
    }


def test_session_adapter_configuration(retry_policy, connection_pool_params):
    with patch("program.utils.request.HTTPAdapter") as MockAdapter:
        session = create_service_session(
            retry_policy=retry_policy,
            session_adapter=get_http_adapter(
                retry_policy=retry_policy,
                pool_connections=connection_pool_params["pool_connections"],
                pool_maxsize=connection_pool_params["pool_maxsize"],
                pool_block=connection_pool_params["pool_block"]
            )
        )

        MockAdapter.assert_called_with(
            max_retries=retry_policy,
            **connection_pool_params
        )

        assert session.adapters["http://"] == MockAdapter.return_value
        assert session.adapters["https://"] == MockAdapter.return_value


def test_session_adapter_pool_configuration_and_request(retry_policy, connection_pool_params):
    # Mock an HTTP endpoint to test request functionality
    url = "https://api.example.com/test"
    with responses.RequestsMock() as rsps:
        rsps.add(rsps.GET, url, json={"message": "success"}, status=200)

        session = create_service_session(
            retry_policy=retry_policy,
            session_adapter=get_http_adapter(
                retry_policy=retry_policy,
                pool_connections=connection_pool_params["pool_connections"],
                pool_maxsize=connection_pool_params["pool_maxsize"],
                pool_block=connection_pool_params["pool_block"]
            )
        )

        adapter_http = session.adapters["http://"]
        adapter_https = session.adapters["https://"]

        assert adapter_http == adapter_https, "HTTP and HTTPS adapters should be the same instance"
        assert adapter_http._pool_connections == connection_pool_params["pool_connections"], \
            f"Expected pool_connections to be {connection_pool_params['pool_connections']}, got {adapter_http._pool_connections}"
        assert adapter_http._pool_maxsize == connection_pool_params["pool_maxsize"], \
            f"Expected pool_maxsize to be {connection_pool_params['pool_maxsize']}, got {adapter_http._pool_maxsize}"
        assert adapter_http._pool_block == connection_pool_params["pool_block"], \
            f"Expected pool_block to be {connection_pool_params['pool_block']}, got {adapter_http._pool_block}"
        assert adapter_http.max_retries == retry_policy, \
            f"Expected max_retries to be {retry_policy}, got {adapter_http.max_retries}"

        response = session.get(url)
        assert response.status_code == 200
        assert response.json() == {"message": "success"}