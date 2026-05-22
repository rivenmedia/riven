"""Tests for stale CDN URL recovery (HTTP 400 refresh + rescrape path)."""

from __future__ import annotations

from http import HTTPStatus
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
import trio

from program.services.streaming.exceptions import (
    DebridServiceLinkUnavailable,
    DebridServiceUnableToConnectException,
)
from program.services.streaming.media_stream import MediaStream
from program.utils.debrid_cdn_url import DebridCDNUrl, RefreshedURLIdenticalException


def _make_stream_response(*, status_code: int, content_length: str = "100") -> MagicMock:
    request = httpx.Request("GET", "https://cdn.example/file.mkv")
    response = MagicMock()
    response.status_code = status_code
    response.headers = httpx.Headers(
        {"Content-Length": content_length, "Accept-Ranges": "bytes"}
    )
    response.http_version = "HTTP/1.1"
    response.request = request

    def raise_for_status() -> None:
        if status_code >= 400:
            raise httpx.HTTPStatusError(
                f"{status_code}",
                request=request,
                response=httpx.Response(status_code, request=request),
            )

    response.raise_for_status = raise_for_status
    return response


def _mock_stream_client(status_codes: list[int]) -> MagicMock:
    """Return a mock async client whose .stream() yields responses in order."""

    calls: list[int] = []

    def stream(**_kwargs):
        idx = len(calls)
        calls.append(idx)
        status = status_codes[min(idx, len(status_codes) - 1)]

        class _Ctx:
            async def __aenter__(self):
                return _make_stream_response(status_code=status)

            async def __aexit__(self, *_args):
                return None

        return _Ctx()

    client = MagicMock()
    client.stream = stream
    return client


@pytest.fixture
def media_stream_kwargs():
    return dict(
        fh=1,
        file_size=1_000_000,
        path="/movies/Test.mkv",
        original_filename="Test.mkv",
        provider="torbox",
        initial_url="https://cdn.example/old?token=abc",
    )


async def _create_media_stream(nursery: trio.Nursery, **kwargs) -> MediaStream:
    with patch("program.services.streaming.media_stream.shutting_down", return_value=False):
        stream = MediaStream(nursery=nursery, **kwargs)
    stream.async_client = _mock_stream_client(
        [HTTPStatus.BAD_REQUEST, HTTPStatus.PARTIAL_CONTENT]
    )
    return stream


def test_establish_connection_400_refreshes_and_retries(media_stream_kwargs):
    async def _run() -> None:
        async with trio.open_nursery() as nursery:
            stream = await _create_media_stream(nursery, **media_stream_kwargs)
            refresh = AsyncMock(return_value=True)
            backoff = AsyncMock(return_value=True)

            with (
                patch.object(stream, "_refresh_download_url", refresh),
                patch.object(stream, "_retry_with_backoff", backoff),
            ):
                async with stream.establish_connection(start=0, end=99) as response:
                    assert response.status_code == HTTPStatus.PARTIAL_CONTENT

            refresh.assert_awaited_once()
            backoff.assert_awaited_once()
            assert stream.target_url.value == media_stream_kwargs["initial_url"]

    trio.run(_run)


def test_establish_connection_400_refresh_fails_raises_unable_to_connect(
    media_stream_kwargs,
):
    async def _run() -> None:
        async with trio.open_nursery() as nursery:
            stream = await _create_media_stream(nursery, **media_stream_kwargs)
            stream.async_client = _mock_stream_client([HTTPStatus.BAD_REQUEST])

            with patch.object(
                stream, "_refresh_download_url", AsyncMock(return_value=False)
            ):
                with pytest.raises(DebridServiceUnableToConnectException) as exc:
                    async with stream.establish_connection(start=0, end=99):
                        pass

            assert exc.value.provider == "torbox"

    trio.run(_run)


def test_debrid_cdn_url_validate_400_calls_refresh():
    entry = SimpleNamespace(
        original_filename="Test.mkv",
        unrestricted_url="https://cdn.example/stale",
        provider="torbox",
    )
    cdn = DebridCDNUrl(entry)  # type: ignore[arg-type]

    request = httpx.Request("GET", cdn.url)
    responses = [
        httpx.Response(HTTPStatus.BAD_REQUEST, request=request),
        httpx.Response(HTTPStatus.OK, request=request, headers={"Content-Length": "1"}),
    ]
    response_idx = {"i": 0}

    class _FakeStream:
        def __init__(self, *_args, **_kwargs):
            pass

        def __enter__(self):
            resp = responses[response_idx["i"]]
            response_idx["i"] += 1
            if resp.status_code >= 400:
                raise httpx.HTTPStatusError(
                    "bad", request=request, response=resp
                )
            return resp

        def __exit__(self, *_args):
            return False

        def iter_bytes(self, **_kwargs):
            yield b"x"

    fake_client = MagicMock()
    fake_client.stream.return_value = _FakeStream()

    refresh_mock = MagicMock(return_value="https://cdn.example/fresh")

    with (
        patch("program.utils.debrid_cdn_url.httpx.Client") as client_cls,
        patch.object(cdn, "_refresh", refresh_mock),
    ):
        client_cls.return_value.__enter__.return_value = fake_client
        result = cdn.validate()

    assert result == "https://cdn.example/fresh"
    refresh_mock.assert_called_once()


def test_debrid_cdn_url_validate_400_identical_refresh_raises_link_unavailable():
    entry = SimpleNamespace(
        original_filename="Test.mkv",
        unrestricted_url="https://cdn.example/stale",
        provider="torbox",
    )
    cdn = DebridCDNUrl(entry)  # type: ignore[arg-type]

    request = httpx.Request("GET", cdn.url)

    class _FakeStream:
        def __enter__(self):
            raise httpx.HTTPStatusError(
                "bad",
                request=request,
                response=httpx.Response(HTTPStatus.BAD_REQUEST, request=request),
            )

        def __exit__(self, *_args):
            return False

    fake_client = MagicMock()
    fake_client.stream.return_value = _FakeStream()

    def _refresh_identical() -> str:
        raise RefreshedURLIdenticalException()

    with (
        patch("program.utils.debrid_cdn_url.httpx.Client") as client_cls,
        patch.object(cdn, "_refresh", side_effect=_refresh_identical),
    ):
        client_cls.return_value.__enter__.return_value = fake_client
        with pytest.raises(DebridServiceLinkUnavailable) as exc:
            cdn.validate()

    assert exc.value.provider == "torbox"
