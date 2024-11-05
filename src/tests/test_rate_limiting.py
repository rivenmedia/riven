import time
import responses
from requests.exceptions import HTTPError
from program.utils.request import create_service_session, get_rate_limit_params, HttpMethod, BaseRequestHandler, ResponseType, RateLimitExceeded

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


