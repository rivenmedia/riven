from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from program.media.state import States
from program.services.downloaders import Downloader
from program.services.downloaders.models import (
    DebridFile,
    DownloadedTorrent,
    InfringingTorrentException,
    TorrentContainer,
    TorrentInfo,
)
from program.services.downloaders.realdebrid import (
    RealDebridDownloader,
    RealDebridErrorCode,
)


def _blacklist_removes_stream(item: MagicMock, stream: MagicMock) -> None:
    if stream in item.streams:
        item.streams.remove(stream)


def _stream(infohash: str) -> MagicMock:
    s = MagicMock()
    s.infohash = infohash
    s.rank = 1
    s.resolution = "1080p"
    s.raw_title = infohash
    return s


def _make_run_downloader(
    services: list[MagicMock],
    *,
    max_streams_per_job: int = 10,
) -> Downloader:
    dl = Downloader.__new__(Downloader)
    dl.initialized = True
    dl.initialized_services = services
    dl._service_cooldowns = {}
    dl._throttled_logs = MagicMock()
    dl._job_slot_lock = MagicMock()
    dl._next_job_slot_at = 0.0
    dl.min_job_interval_seconds = 0.0
    dl.max_streams_per_job = max_streams_per_job
    dl.subtitles_enabled = False
    dl._recent_jobs = __import__("collections").deque(maxlen=5)
    dl._active_jobs = {}
    dl._active_jobs_lock = __import__("threading").Lock()

    dl._acquire_job_slot = MagicMock()
    dl._available_services = MagicMock(return_value=services)
    dl._any_service_subscription_active = MagicMock(return_value=True)
    dl._fail_download = MagicMock()
    dl._space_after_stream_attempt = MagicMock()
    return dl


def _valid_container(infohash: str) -> TorrentContainer:
    return TorrentContainer(
        infohash=infohash,
        files=[
            DebridFile(
                file_id=1,
                filename="movie.mkv",
                filesize=1_000_000_000,
                download_url="http://example.com/file",
            )
        ],
        torrent_id="tid-1",
    )


@pytest.mark.parametrize(
    ("status_code", "json_payload", "expected"),
    [
        (451, None, True),
        (400, {"error_code": int(RealDebridErrorCode.INFRINGING_FILE)}, True),
        (400, {"error_code": RealDebridErrorCode.INFRINGING_FILE}, True),
        (404, {"error_code": 7}, False),
    ],
)
def test_is_infringing_response(status_code, json_payload, expected):
    response = MagicMock()
    response.status_code = status_code
    if json_payload is None:
        response.json.side_effect = Exception("no json")
    else:
        response.json.return_value = json_payload

    assert RealDebridDownloader._is_infringing_response(response) is expected


def test_raise_for_response_infringing():
    dl = RealDebridDownloader.__new__(RealDebridDownloader)
    dl.key = "realdebrid"

    response = MagicMock()
    response.status_code = 451
    response.reason = "Unavailable For Legal Reasons"
    response.json.side_effect = Exception("no json")

    with pytest.raises(InfringingTorrentException) as exc_info:
        dl._raise_for_response(response, infohash="abc123")

    assert "[451]" in str(exc_info.value)
    assert exc_info.value.provider == "realdebrid"
    assert exc_info.value.infohash == "abc123"


@patch.object(Downloader, "validate", return_value=False)
@patch.object(Downloader, "_compute_min_job_interval", return_value=0.0)
def test_single_provider_infringing_blacklists(_interval, _validate):
    rd = MagicMock(key="realdebrid")
    dl = _make_run_downloader([rd])

    stream = _stream("deadbeef")
    item = MagicMock()
    item.id = 1
    item.log_string = "Movie"
    item.streams = [stream]
    item.type = "movie"
    item.blacklist_stream = MagicMock(
        side_effect=lambda s: _blacklist_removes_stream(item, s)
    )

    dl.validate_stream_on_service = MagicMock(
        side_effect=InfringingTorrentException(
            "[451] Infringing Torrent",
            provider="realdebrid",
            infohash="deadbeef",
        )
    )

    list(dl.run(item))

    item.blacklist_stream.assert_called_once_with(stream)
    dl._fail_download.assert_called_once()


@patch.object(Downloader, "validate", return_value=False)
@patch.object(Downloader, "_compute_min_job_interval", return_value=0.0)
def test_multi_provider_fallback_after_infringing(_interval, _validate):
    rd = MagicMock(key="realdebrid")
    dl_svc = MagicMock(key="debridlink")
    dl = _make_run_downloader([rd, dl_svc])

    stream = _stream("cafebabe")
    item = MagicMock()
    item.id = 2
    item.log_string = "Movie"
    item.streams = [stream]
    item.type = "movie"

    container = _valid_container("cafebabe")

    def validate(stream_arg, item_arg, service):
        if service.key == "realdebrid":
            raise InfringingTorrentException(
                "[451] Infringing Torrent",
                provider="realdebrid",
            )
        return container

    dl.validate_stream_on_service = MagicMock(side_effect=validate)
    torrent_info = TorrentInfo(id="tid-1", name="movie.mkv", infohash="cafebabe")
    dl.download_cached_stream_on_service = MagicMock(
        return_value=DownloadedTorrent(
            id="tid-1",
            info=torrent_info,
            infohash="cafebabe",
            container=container,
        )
    )
    dl.update_item_attributes = MagicMock(return_value=True)

    results = list(dl.run(item))

    item.blacklist_stream.assert_not_called()
    dl._fail_download.assert_not_called()
    assert len(results) == 1
    dl.download_cached_stream_on_service.assert_called_once()
    dl.validate_stream_on_service.assert_any_call(stream, item, rd)
    dl.validate_stream_on_service.assert_any_call(stream, item, dl_svc)


@patch.object(Downloader, "validate", return_value=False)
@patch.object(Downloader, "_compute_min_job_interval", return_value=0.0)
def test_all_providers_infringing_blacklists(_interval, _validate):
    rd = MagicMock(key="realdebrid")
    dl_svc = MagicMock(key="debridlink")
    dl = _make_run_downloader([rd, dl_svc])

    stream = _stream("badhash")
    item = MagicMock()
    item.id = 3
    item.log_string = "Movie"
    item.streams = [stream]
    item.type = "movie"
    item.blacklist_stream = MagicMock(
        side_effect=lambda s: _blacklist_removes_stream(item, s)
    )

    def validate(_s, _i, service):
        raise InfringingTorrentException(
            "[451] Infringing Torrent",
            provider=service.key,
        )

    dl.validate_stream_on_service = MagicMock(side_effect=validate)

    list(dl.run(item))

    item.blacklist_stream.assert_called_once_with(stream)
    dl._fail_download.assert_called_once()
    assert dl.validate_stream_on_service.call_count == 2
