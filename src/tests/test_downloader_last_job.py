import threading
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

from program.media.state import States
from program.services.downloaders import (
    Downloader,
    _DownloadRunDiagnostics,
    _JobCompletion,
    _LastJob,
)


def _make_downloader() -> Downloader:
    dl = Downloader.__new__(Downloader)
    dl._recent_jobs = __import__("collections").deque(maxlen=5)
    dl.initialized_services = []
    dl._service_cooldowns = {}
    return dl


def test_build_detail_zero_streams():
    diag = _DownloadRunDiagnostics(streams_total=0)
    assert diag.build_detail() == "0 streams on item"


def test_build_detail_not_cached():
    diag = _DownloadRunDiagnostics(streams_total=2)
    diag.note_not_cached("realdebrid", "abc123")
    diag.note_not_cached("realdebrid", "def456")
    diag.note_stream_tried()
    assert diag.build_detail() == "Tried 1 stream (1 more on item). Not cached on debrid"


def test_build_detail_shows_remaining_streams():
    diag = _DownloadRunDiagnostics(streams_total=10)
    diag.note_not_cached("debridlink", "abc123")
    diag.note_stream_tried()
    assert (
        diag.build_detail()
        == "Tried 1 stream (9 more on item). Not cached on debrid"
    )


def test_build_detail_mixed_reasons():
    diag = _DownloadRunDiagnostics(streams_total=8)
    diag.note_not_cached("torbox", "a")
    diag.note_no_matching_files("realdebrid", "b")
    diag.note_stream_tried()
    diag.note_stream_tried()
    detail = diag.build_detail()
    assert detail == (
        "Tried 2 streams (6 more on item). "
        "Not cached on debrid; no matching files in torrent"
    )


def test_build_detail_api_error_with_last():
    diag = _DownloadRunDiagnostics(streams_total=1)
    diag.note_api_error("torbox", "abc", ValueError("HTTP 403 Forbidden"))
    diag.note_stream_tried()
    detail = diag.build_detail()
    assert detail.startswith("Tried 1 stream. API error (")
    assert "403" in detail


def test_build_detail_length_cap():
    diag = _DownloadRunDiagnostics(streams_total=100)
    for _ in range(50):
        diag.note_not_cached("realdebrid", "x")
    diag.note_api_error("realdebrid", "x", RuntimeError("x" * 200))
    detail = diag.build_detail()
    assert len(detail) <= 480


def test_append_and_get_recent_jobs_newest_first():
    dl = _make_downloader()
    item = MagicMock()
    item.id = 42
    item.log_string = "Test Item"

    with patch.object(dl, "_log_job_completion"):
        dl._append_completed_job(item, _JobCompletion("success", detail="ok", service="torbox"))

    jobs = dl.get_recent_jobs()
    assert len(jobs) == 1
    assert jobs[0]["item_id"] == 42
    assert jobs[0]["outcome"] == "success"
    assert jobs[0]["detail"] == "ok"
    assert jobs[0]["service"] == "torbox"
    assert jobs[0]["completed_at"]


def test_recent_jobs_evict_older_than_two_minutes():
    dl = _make_downloader()
    now = datetime.now(UTC)
    dl._recent_jobs.appendleft(
        _LastJob(item_id=2, completed_at=now, outcome="success"),
    )
    dl._recent_jobs.append(
        _LastJob(
            item_id=1,
            completed_at=now - timedelta(minutes=3),
            outcome="failed",
        )
    )

    jobs = dl.get_recent_jobs()
    assert len(jobs) == 1
    assert jobs[0]["item_id"] == 2
    assert len(dl._recent_jobs) == 1


def test_recent_jobs_deque_max_five():
    dl = _make_downloader()
    with patch.object(dl, "_log_job_completion"):
        for i in range(6):
            item = MagicMock()
            item.id = i
            item.log_string = f"Item {i}"
            dl._append_completed_job(item, _JobCompletion("success"))

    jobs = dl.get_recent_jobs()
    assert len(jobs) == 5
    assert [j["item_id"] for j in jobs] == [5, 4, 3, 2, 1]


def test_run_records_only_after_generator_closed():
    dl = _make_downloader()
    dl.initialized = True
    dl.initialized_services = [MagicMock(key="torbox")]
    dl._service_cooldowns = {"torbox": datetime.now() + timedelta(minutes=1)}
    dl._throttled_logs = MagicMock()
    dl._job_slot_lock = MagicMock()
    dl._next_job_slot_at = 0.0
    dl.min_job_interval_seconds = 0.0
    dl.max_streams_per_job = 3
    dl.subtitles_enabled = False
    dl._acquire_job_slot = MagicMock()
    dl._available_services = MagicMock(return_value=[])

    item = MagicMock()
    item.id = 7
    item.log_string = "Test Movie"
    item.streams = []

    gen = dl.run(item)
    next(gen)
    assert dl.get_recent_jobs() == []

    gen.close()
    jobs = dl.get_recent_jobs()
    assert len(jobs) == 1
    assert jobs[0]["outcome"] == "deferred"
    assert jobs[0]["item_id"] == 7


@patch.object(Downloader, "validate", return_value=False)
@patch.object(Downloader, "_compute_min_job_interval", return_value=0.2)
def test_run_all_cooldown_records_deferred(_interval, _validate):
    dl = Downloader.__new__(Downloader)
    dl.initialized = True
    dl.initialized_services = [MagicMock(key="torbox")]
    dl._service_cooldowns = {"torbox": datetime.now() + timedelta(minutes=1)}
    dl._throttled_logs = MagicMock()
    dl._job_slot_lock = MagicMock()
    dl._next_job_slot_at = 0.0
    dl.min_job_interval_seconds = 0.0
    dl.max_streams_per_job = 3
    dl.subtitles_enabled = False
    dl._recent_jobs = __import__("collections").deque(maxlen=5)

    dl._acquire_job_slot = MagicMock()
    dl._available_services = MagicMock(return_value=[])

    item = MagicMock()
    item.id = 7
    item.log_string = "Test Movie"
    item.streams = []

    list(dl.run(item))

    jobs = dl.get_recent_jobs()
    assert len(jobs) == 1
    assert jobs[0]["outcome"] == "deferred"
    assert jobs[0]["item_id"] == 7


@patch.object(Downloader, "validate", return_value=False)
@patch.object(Downloader, "_compute_min_job_interval", return_value=0.2)
def test_run_empty_streams_records_failed_detail(_interval, _validate):
    dl = Downloader.__new__(Downloader)
    dl.initialized = True
    svc = MagicMock(key="torbox")
    dl.initialized_services = [svc]
    dl._service_cooldowns = {}
    dl._throttled_logs = MagicMock()
    dl._job_slot_lock = MagicMock()
    dl._next_job_slot_at = 0.0
    dl.min_job_interval_seconds = 0.0
    dl.max_streams_per_job = 3
    dl.subtitles_enabled = False
    dl._recent_jobs = __import__("collections").deque(maxlen=5)

    dl._acquire_job_slot = MagicMock()
    dl._available_services = MagicMock(return_value=[svc])
    dl._any_service_subscription_active = MagicMock(return_value=True)
    dl._log_job_completion = MagicMock()

    item = MagicMock()
    item.id = 99
    item.log_string = "Empty Movie"
    item.streams = []

    list(dl.run(item))

    jobs = dl.get_recent_jobs()
    assert len(jobs) == 1
    assert jobs[0]["outcome"] == "failed"
    assert "0 streams" in (jobs[0]["detail"] or "")
    item.store_state.assert_called_once_with(States.Failed)


def _stream(infohash: str, rank: int = 1) -> MagicMock:
    s = MagicMock()
    s.infohash = infohash
    s.rank = rank
    s.resolution = "1080p"
    s.raw_title = infohash
    return s


@patch.object(Downloader, "validate", return_value=False)
@patch.object(Downloader, "_compute_min_job_interval", return_value=0.2)
def test_run_requeues_when_more_streams_remain_after_per_job_cap(
    _interval, _validate
):
    dl = Downloader.__new__(Downloader)
    dl.initialized = True
    svc = MagicMock(key="torbox")
    dl.initialized_services = [svc]
    dl._service_cooldowns = {}
    dl._throttled_logs = MagicMock()
    dl._job_slot_lock = MagicMock()
    dl._next_job_slot_at = 0.0
    dl.min_job_interval_seconds = 0.0
    dl.max_streams_per_job = 3
    dl.subtitles_enabled = False
    dl._recent_jobs = __import__("collections").deque(maxlen=5)

    dl._acquire_job_slot = MagicMock()
    dl._available_services = MagicMock(return_value=[svc])
    dl._any_service_subscription_active = MagicMock(return_value=True)
    dl._fail_download = MagicMock()
    dl._download_retry_run_at = MagicMock(
        return_value=datetime.now(UTC) + timedelta(seconds=5)
    )
    dl._active_jobs = {}
    dl._active_jobs_lock = threading.Lock()
    dl.validate_stream_on_service = MagicMock(return_value=None)
    dl._space_after_stream_attempt = MagicMock()

    streams = [_stream(f"h{i}") for i in range(5)]
    item = MagicMock()
    item.id = 12
    item.log_string = "Show S01E01"
    item.streams = streams

    def blacklist(stream):
        if stream in item.streams:
            item.streams.remove(stream)

    item.blacklist_stream = MagicMock(side_effect=blacklist)

    results = list(dl.run(item))

    assert len(results) == 1
    assert results[0].run_at is not None
    dl._fail_download.assert_not_called()
    item.store_state.assert_not_called()


@patch.object(Downloader, "validate", return_value=False)
@patch.object(Downloader, "_compute_min_job_interval", return_value=0.2)
def test_run_fails_when_all_streams_exhausted(_interval, _validate):
    dl = Downloader.__new__(Downloader)
    dl.initialized = True
    svc = MagicMock(key="torbox")
    dl.initialized_services = [svc]
    dl._service_cooldowns = {}
    dl._throttled_logs = MagicMock()
    dl._job_slot_lock = MagicMock()
    dl._next_job_slot_at = 0.0
    dl.min_job_interval_seconds = 0.0
    dl.max_streams_per_job = 10
    dl.subtitles_enabled = False
    dl._recent_jobs = __import__("collections").deque(maxlen=5)

    dl._acquire_job_slot = MagicMock()
    dl._available_services = MagicMock(return_value=[svc])
    dl._any_service_subscription_active = MagicMock(return_value=True)
    dl._fail_download = MagicMock()
    dl._active_jobs = {}
    dl._active_jobs_lock = threading.Lock()
    dl.validate_stream_on_service = MagicMock(return_value=None)
    dl._space_after_stream_attempt = MagicMock()

    streams = [_stream("only")]
    item = MagicMock()
    item.id = 13
    item.log_string = "Movie"
    item.streams = list(streams)

    def blacklist(stream):
        if stream in item.streams:
            item.streams.remove(stream)

    item.blacklist_stream = MagicMock(side_effect=blacklist)

    list(dl.run(item))

    dl._fail_download.assert_called_once()
