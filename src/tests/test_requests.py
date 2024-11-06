from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from requests import Session
from requests.exceptions import ConnectTimeout

from program.utils.request import (
    CachedLimiterSession,
    CachedSession,
    LimiterSession,
    MemoryQueueBucket,
    RateLimitExceeded,
    RequestException,
    Response,
    ResponseObject,
    _make_request,
    create_service_session,
    delete,
    get,
    get_cache_params,
    get_rate_limit_params,
    ping,
    post,
    put,
)


class TestCodeUnderTest:
    def test_create_service_session_default(self):
        session = create_service_session()
        assert isinstance(session, Session)

    def test_handle_empty_response_content(self, mocker):
        mock_response = mocker.Mock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.content = b""
        mock_response.headers = {"Content-Type": "application/json"}
        response_object = ResponseObject(mock_response)
        assert response_object.data == {}

    def test_handle_json_response(self, mocker):
        mock_session = mocker.MagicMock()
        mock_response = MagicMock()
        mock_response.content = b'{"key": "value"}'
        mock_response.headers = {"Content-Type": "application/json"}
        mock_response.ok = True
        mock_response.status_code = 200
        mock_session.request.return_value = mock_response
        response_object = get(mock_session, "https://example.com")
        assert response_object.is_ok is True
        assert response_object.status_code == 200
        assert response_object.data.key == "value"

    def test_handle_xml_response(self, mocker):
        mock_session = mocker.MagicMock()
        mock_response = MagicMock()
        mock_response.content = b'<root><key>value</key></root>'
        mock_response.headers = {"Content-Type": "application/xml"}
        mock_response.ok = True
        mock_response.status_code = 200
        mock_session.request.return_value = mock_response
        response_object = get(mock_session, "https://example.com")
        assert response_object.is_ok is True
        assert response_object.status_code == 200
        assert response_object.data.key.text == "value"

    def test_create_service_session_without_cache_params_raises_error(self):
        mock_rate_limit_params = get_rate_limit_params(per_minute=60)
        with pytest.raises(ValueError, match="Cache parameters must be provided if use_cache is True."):
            create_service_session(rate_limit_params=mock_rate_limit_params, use_cache=True)

    def test_apply_rate_limiting_valid_parameters(self, mocker):
        mock_rate_limit_params = {'per_minute': 60, 'bucket_class': MemoryQueueBucket, 'bucket_kwargs': {}}
        session = create_service_session(rate_limit_params=mock_rate_limit_params)
        assert isinstance(session, LimiterSession)

    def test_apply_caching_valid_parameters(self, mocker):
        mock_cache_params = {'cache_name': 'test_cache', 'expire_after': 60}
        session = create_service_session(use_cache=True, cache_params=mock_cache_params)
        assert isinstance(session, CachedSession)

    def test_apply_rate_limiting_and_caching_valid_parameters(self, mocker):
        mock_rate_limit_params = {'per_minute': 60, 'bucket_class': MemoryQueueBucket, 'bucket_kwargs': {}}
        mock_cache_params = {'cache_name': 'test_cache', 'expire_after': 60}
        session = create_service_session(rate_limit_params=mock_rate_limit_params, use_cache=True, cache_params=mock_cache_params)
        assert isinstance(session, CachedLimiterSession)

    def test_make_get_request_valid_response(self, mocker):
        url = "https://api.example.com"
        expected_response = ResponseObject(SimpleNamespace(ok=True, status_code=200, content={}, headers={}))
        mocker.patch('program.utils.request.Session')
        session_instance = Session()
        mocker.patch('program.utils.request._make_request', return_value=expected_response)
        response = get(session_instance, url)
        assert response.is_ok is True
        assert response.status_code == 200

    def test_make_post_request_valid_response(self, mocker):
        url = "https://api.example.com"
        expected_response = ResponseObject(SimpleNamespace(ok=True, status_code=201, content={}, headers={}))
        mocker.patch('program.utils.request.Session')
        session_instance = Session()
        mocker.patch('program.utils.request._make_request', return_value=expected_response)
        response = post(session_instance, url)
        assert response.is_ok is True
        assert response.status_code == 201

    def test_put_request_valid_response(self, mocker):
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_session = mocker.Mock()
        mocker.patch('program.utils.request._make_request', return_value=ResponseObject(mock_response))
        response = put(mock_session, "https://example.com")
        assert response.is_ok
        assert response.status_code == 200


    def test_delete_request_valid_response(self, mocker):
        url = "https://example.com"
        expected_response = ResponseObject(SimpleNamespace(ok=True, status_code=200, content={}, headers={}))
        mocker.patch('program.utils.request._make_request', return_value=expected_response)
        mock_session = mocker.Mock()
        response = delete(mock_session, url)
        assert response.is_ok is True
        assert response.status_code == 200

    def test_handle_unsupported_content_types(self, mocker):
        mock_response = mocker.Mock()
        mock_response.headers.get.return_value = "unsupported/type"
        mock_response.content = b"Unsupported content"
        mock_session = mocker.Mock()
        mock_session.request.return_value = mock_response
        response_object = _make_request(mock_session, "GET", "https://example.com")
        assert response_object.data == {}

    def test_raise_exceptions_timeout_status_codes(self, mocker):
        mock_response = mocker.Mock()
        mock_response.ok = False
        mock_response.status_code = 504
        mock_session = mocker.Mock()
        mock_session.request.return_value = mock_response
        with pytest.raises(ConnectTimeout):
            _make_request(mock_session, "GET", "https://example.com")

    def test_raise_rate_limit_exceptions(self, mocker):
        mock_response = mocker.Mock()
        mock_response.ok = False
        mock_response.status_code = 429
        mock_response.headers = {"Content-Type": "application/json", "Connection": "keep-alive"}
        mocker.patch('program.utils.request.Session.request', return_value=mock_response)
        rate_limit_params = get_rate_limit_params(per_second=10, period=1)
        cache_params = {'cache_name': 'test_cache', 'expire_after': 60}
        session = create_service_session(rate_limit_params=rate_limit_params, use_cache=True, cache_params=cache_params)
        with pytest.raises(RateLimitExceeded):
            get(session, "https://api.example.com/data")

    def test_raise_client_error_exceptions(self, mocker):
        mock_response = mocker.Mock()
        mock_response.ok = False
        mock_response.status_code = 400
        mock_response.headers = {"Content-Type": "application/json", "Connection": "keep-alive"}
        mocker.patch('program.utils.request.Session.request', return_value=mock_response)
        cache_params = {'cache_name': 'test_cache', 'expire_after': 60}
        session = create_service_session(rate_limit_params=None, use_cache=True, cache_params=cache_params)
        with pytest.raises(RequestException):
            post(session, "https://api.example.com/data", data={"key": "value"})

    def test_raise_exceptions_server_error_status_codes(self, mocker):
        mocker.patch('program.utils.request._make_request',
                     side_effect=RequestException("Server error with status 500"))
        mock_session = mocker.Mock()
        with pytest.raises(RequestException, match="Server error with status 500"):
            ping(mock_session, "https://example.com")


    def test_log_errors_when_parsing_response_content_fails(self, mocker):
        mock_logger = mocker.patch('logging.Logger.error')
        response = Response()
        response._content = b"invalid json content"
        response.headers = {"Content-Type": "application/json"}
        response.status_code = 200
        ResponseObject(response)
        mock_logger.assert_called_with("Failed to parse response content: Expecting value: line 1 column 1 (char 0)", exc_info=True)
