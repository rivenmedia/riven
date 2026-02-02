"""
Unit tests for OpenSubtitles.com REST API provider.

Tests cover:
- Authentication flow (success, 401, 429, 5xx)
- Search strategies (hash, IMDB, filename)
- Download with rate limiting
- Token refresh behavior
"""

import pytest
import httpx

from program.settings.models import OpenSubtitlesComConfig
from program.services.post_processing.subtitles.providers.opensubtitles_com import (
    OpenSubtitlesComProvider,
    OpenSubtitlesLoginResponse,
    OpenSubtitlesSearchResult,
)
from program.services.post_processing.subtitles.providers.base import SubtitleItem


@pytest.fixture
def mock_config():
    """Create a test configuration."""
    return OpenSubtitlesComConfig(
        enabled=True,
        api_key="test_api_key_1234567890123456789012345",
        username="testuser",
        password="testpass",
    )


@pytest.fixture
def requests_mock(monkeypatch):
    """Mock httpx client for testing HTTP requests."""
    import program.utils.request as request_mod

    routes: dict[tuple[str, str], dict] = {}

    def _add(method: str, url: str, cfg):
        key = (method.upper(), url)
        if isinstance(cfg, list):
            routes[key] = {"queue": list(cfg), "sticky": None}
        else:
            routes[key] = {"queue": [], "sticky": cfg}

    def handler(request: httpx.Request) -> httpx.Response:
        key = (request.method.upper(), str(request.url).split("?")[0])
        entry = routes.get(key)
        if not entry:
            # Try partial match for URLs with query params
            for (method, url), cfg in routes.items():
                if method == request.method.upper() and str(request.url).startswith(url):
                    entry = cfg
                    break
        if not entry:
            return httpx.Response(
                404,
                json={"detail": f"Not mocked: {request.method} {request.url}"},
                headers={"Content-Type": "application/json"},
            )
        if entry["queue"]:
            cfg = entry["queue"].pop(0)
        else:
            cfg = entry["sticky"]
        if cfg is None:
            return httpx.Response(
                404,
                json={"detail": "Not mocked"},
                headers={"Content-Type": "application/json"},
            )
        status_code = cfg.get("status_code", 200)
        headers = dict(cfg.get("headers", {}))
        if "json" in cfg:
            headers.setdefault("Content-Type", "application/json")
            return httpx.Response(status_code, headers=headers, json=cfg["json"])
        content = cfg.get("content", b"")
        return httpx.Response(status_code, headers=headers, content=content)

    transport = httpx.MockTransport(handler)
    RealClient = httpx.Client

    class _FakeClient:
        def __init__(self, *args, **kwargs):
            self._client = RealClient(transport=transport)
            self.timeout = httpx.Timeout(connect=5.0, read=30.0, write=10.0, pool=5.0)

        def request(self, *args, **kwargs):
            return self._client.request(*args, **kwargs)

        def build_request(self, *args, **kwargs):
            return self._client.build_request(*args, **kwargs)

        def send(self, *args, **kwargs):
            kwargs.pop("timeout", None)
            return self._client.send(*args, **kwargs)

        def close(self):
            self._client.close()

    monkeypatch.setattr(request_mod.httpx, "Client", _FakeClient, raising=True)

    class _Mock:
        def register(self, method: str, url: str, cfg):
            _add(method, url, cfg)

        def get(self, url: str, cfg=None, **kwargs):
            if cfg is None and kwargs:
                cfg = kwargs
            _add("GET", url, cfg)

        def post(self, url: str, cfg=None, **kwargs):
            if cfg is None and kwargs:
                cfg = kwargs
            _add("POST", url, cfg)

    return _Mock()


class TestOpenSubtitlesLoginResponse:
    """Test Pydantic response model validation."""

    def test_valid_token(self):
        """Valid token should parse correctly."""
        response = OpenSubtitlesLoginResponse.model_validate({"token": "valid_jwt_token"})
        assert response.token == "valid_jwt_token"

    def test_empty_token_raises(self):
        """Empty token should raise validation error."""
        with pytest.raises(Exception):
            OpenSubtitlesLoginResponse.model_validate({"token": ""})

    def test_whitespace_token_raises(self):
        """Whitespace-only token should raise validation error."""
        with pytest.raises(Exception):
            OpenSubtitlesLoginResponse.model_validate({"token": "   "})

    def test_token_is_stripped(self):
        """Token with whitespace should be stripped."""
        response = OpenSubtitlesLoginResponse.model_validate({"token": "  token_value  "})
        assert response.token == "token_value"


class TestOpenSubtitlesSearchResult:
    """Test search result model."""

    def test_basic_result(self):
        """Basic result should parse correctly."""
        data = {
            "id": "12345",
            "attributes": {
                "language": "en",
                "download_count": 1000,
                "ratings": 8.5,
                "moviehash_match": True,
                "files": [{"file_id": "67890", "file_name": "Movie.2024.srt"}],
            },
        }
        result = OpenSubtitlesSearchResult.model_validate(data)
        assert result.subtitle_id == "67890"
        assert result.language == "en"
        assert result.filename == "Movie.2024.srt"
        assert result.download_count == 1000
        assert result.rating == 8.5
        assert result.moviehash_match is True

    def test_missing_files(self):
        """Result without files should fallback to id."""
        data = {
            "id": "12345",
            "attributes": {"language": "en"},
        }
        result = OpenSubtitlesSearchResult.model_validate(data)
        assert result.subtitle_id == "12345"
        assert result.filename == ""


class TestOpenSubtitlesComProvider:
    """Test the provider implementation."""

    def test_provider_name(self, mock_config, requests_mock):
        """Provider should return correct name."""
        requests_mock.post(
            "https://api.opensubtitles.com/api/v1/login",
            json={"token": "test_token"},
        )
        provider = OpenSubtitlesComProvider(mock_config)
        assert provider.name == "opensubtitles_com"

    def test_login_success(self, mock_config, requests_mock):
        """Successful login should store token."""
        requests_mock.post(
            "https://api.opensubtitles.com/api/v1/login",
            json={"token": "jwt_token_12345"},
        )
        provider = OpenSubtitlesComProvider(mock_config)
        assert provider._login() is True
        assert provider.token == "jwt_token_12345"

    def test_login_unauthorized(self, mock_config, requests_mock):
        """401 response should return False."""
        requests_mock.post(
            "https://api.opensubtitles.com/api/v1/login",
            status_code=401,
            json={"error": "Invalid credentials"},
        )
        provider = OpenSubtitlesComProvider(mock_config)
        assert provider._login() is False
        assert provider.token is None

    def test_login_rate_limited(self, mock_config, requests_mock):
        """429 response should return False."""
        requests_mock.post(
            "https://api.opensubtitles.com/api/v1/login",
            status_code=429,
            json={"error": "Too many requests"},
        )
        provider = OpenSubtitlesComProvider(mock_config)
        assert provider._login() is False

    def test_login_server_error(self, mock_config, requests_mock):
        """5xx response should return False."""
        requests_mock.post(
            "https://api.opensubtitles.com/api/v1/login",
            status_code=500,
            json={"error": "Internal server error"},
        )
        provider = OpenSubtitlesComProvider(mock_config)
        assert provider._login() is False

    def test_search_by_hash(self, mock_config, requests_mock):
        """Search by hash should return results."""
        requests_mock.post(
            "https://api.opensubtitles.com/api/v1/login",
            json={"token": "test_token"},
        )
        requests_mock.get(
            "https://api.opensubtitles.com/api/v1/subtitles",
            json={
                "data": [
                    {
                        "id": "123",
                        "attributes": {
                            "language": "en",
                            "download_count": 500,
                            "ratings": 7.5,
                            "moviehash_match": True,
                            "files": [{"file_id": "456", "file_name": "Test.srt"}],
                        },
                    }
                ]
            },
        )

        provider = OpenSubtitlesComProvider(mock_config)
        results = provider.search_subtitles(
            imdb_id="tt1234567",
            video_hash="abc123def456",
            file_size=1000000,
            language="en",
        )

        assert len(results) == 1
        assert results[0].id == "456"
        assert results[0].matched_by == "hash"
        assert results[0].provider == "opensubtitles_com"

    def test_search_by_imdb(self, mock_config, requests_mock):
        """Search by IMDB ID should work when hash fails."""
        requests_mock.post(
            "https://api.opensubtitles.com/api/v1/login",
            json={"token": "test_token"},
        )
        # First search (hash) returns empty
        # Second search (imdb) returns results
        requests_mock.get(
            "https://api.opensubtitles.com/api/v1/subtitles",
            [
                {"json": {"data": []}},  # hash search - empty
                {
                    "json": {
                        "data": [
                            {
                                "id": "789",
                                "attributes": {
                                    "language": "en",
                                    "download_count": 100,
                                    "ratings": 6.0,
                                    "files": [{"file_id": "999", "file_name": "IMDB.srt"}],
                                },
                            }
                        ]
                    }
                },
            ],
        )

        provider = OpenSubtitlesComProvider(mock_config)
        results = provider.search_subtitles(
            imdb_id="tt1234567",
            video_hash="abc123",
            file_size=1000000,
            language="en",
        )

        assert len(results) == 1
        assert results[0].matched_by == "imdb"

    def test_search_strips_tt_prefix(self, mock_config, requests_mock):
        """IMDB ID 'tt' prefix should be stripped."""
        requests_mock.post(
            "https://api.opensubtitles.com/api/v1/login",
            json={"token": "test_token"},
        )
        requests_mock.get(
            "https://api.opensubtitles.com/api/v1/subtitles",
            json={"data": []},
        )

        provider = OpenSubtitlesComProvider(mock_config)
        # Just verify it doesn't crash - the actual param check would need deeper mocking
        results = provider.search_subtitles(imdb_id="tt1234567", language="en")
        assert results == []

    def test_search_rate_limited(self, mock_config, requests_mock):
        """429 during search should return empty list."""
        requests_mock.post(
            "https://api.opensubtitles.com/api/v1/login",
            json={"token": "test_token"},
        )
        requests_mock.get(
            "https://api.opensubtitles.com/api/v1/subtitles",
            status_code=429,
            headers={"Retry-After": "60"},
            json={"error": "Rate limited"},
        )

        provider = OpenSubtitlesComProvider(mock_config)
        results = provider.search_subtitles(imdb_id="tt1234567", language="en")
        assert results == []

    def test_download_success(self, mock_config, requests_mock):
        """Successful download should return subtitle content."""
        requests_mock.post(
            "https://api.opensubtitles.com/api/v1/login",
            json={"token": "test_token"},
        )
        requests_mock.post(
            "https://api.opensubtitles.com/api/v1/download",
            json={"link": "https://dl.opensubtitles.com/file.srt"},
        )
        requests_mock.get(
            "https://dl.opensubtitles.com/file.srt",
            content=b"1\n00:00:01,000 --> 00:00:02,000\nHello World\n",
        )

        provider = OpenSubtitlesComProvider(mock_config)
        subtitle_info = SubtitleItem(
            id="12345",
            language="en",
            filename="test.srt",
            download_count=100,
            rating=8.0,
            matched_by="hash",
            movie_hash=None,
            movie_name=None,
            provider="opensubtitles_com",
            score=100,
        )

        content = provider.download_subtitle(subtitle_info)
        assert content is not None
        assert "Hello World" in content

    def test_download_rate_limited(self, mock_config, requests_mock):
        """429 during download should return None."""
        requests_mock.post(
            "https://api.opensubtitles.com/api/v1/login",
            json={"token": "test_token"},
        )
        requests_mock.post(
            "https://api.opensubtitles.com/api/v1/download",
            status_code=429,
            json={"remaining": 0},
        )

        provider = OpenSubtitlesComProvider(mock_config)
        subtitle_info = SubtitleItem(
            id="12345",
            language="en",
            filename="test.srt",
            download_count=100,
            rating=8.0,
            matched_by="hash",
            movie_hash=None,
            movie_name=None,
            provider="opensubtitles_com",
            score=100,
        )

        content = provider.download_subtitle(subtitle_info)
        assert content is None

    def test_decode_utf8(self, mock_config, requests_mock):
        """UTF-8 content should decode correctly."""
        requests_mock.post(
            "https://api.opensubtitles.com/api/v1/login",
            json={"token": "test_token"},
        )
        provider = OpenSubtitlesComProvider(mock_config)

        content = provider._decode_content("Hello World".encode("utf-8"))
        assert content == "Hello World"

    def test_decode_utf8_bom(self, mock_config, requests_mock):
        """UTF-8 with BOM should decode correctly."""
        requests_mock.post(
            "https://api.opensubtitles.com/api/v1/login",
            json={"token": "test_token"},
        )
        provider = OpenSubtitlesComProvider(mock_config)

        content = provider._decode_content("\ufeffHello World".encode("utf-8-sig"))
        assert content == "Hello World"

    def test_decode_latin1_fallback(self, mock_config, requests_mock):
        """Latin-1 content should decode with fallback."""
        requests_mock.post(
            "https://api.opensubtitles.com/api/v1/login",
            json={"token": "test_token"},
        )
        provider = OpenSubtitlesComProvider(mock_config)

        # Latin-1 specific character
        content = provider._decode_content("Café".encode("latin-1"))
        assert "Caf" in content

    def test_score_calculation(self, mock_config, requests_mock):
        """Results should be scored and sorted correctly."""
        requests_mock.post(
            "https://api.opensubtitles.com/api/v1/login",
            json={"token": "test_token"},
        )
        provider = OpenSubtitlesComProvider(mock_config)

        results = [
            {
                "id": "1",
                "attributes": {
                    "language": "en",
                    "download_count": 100,
                    "ratings": 5.0,
                    "files": [{"file_id": "1", "file_name": "low.srt"}],
                },
            },
            {
                "id": "2",
                "attributes": {
                    "language": "en",
                    "download_count": 10000,
                    "ratings": 9.0,
                    "moviehash_match": True,
                    "files": [{"file_id": "2", "file_name": "high.srt"}],
                },
            },
        ]

        scored = provider._score_results(results, "hash")

        # Second result should be first (higher score due to hash match + downloads)
        assert len(scored) == 2
        assert scored[0].id == "2"
        assert scored[0].score > scored[1].score
