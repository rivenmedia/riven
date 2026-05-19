from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

from program.services.downloaders import Downloader, _DownloadRunDiagnostics


def _make_downloader() -> Downloader:
    dl = Downloader.__new__(Downloader)
    dl._last_job = None
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
    detail = diag.build_detail()
    assert "2 not cached" in detail
    assert "realdebrid" in detail


def test_build_detail_mixed_with_prefix():
    diag = _DownloadRunDiagnostics(streams_total=3)
    diag.note_not_cached("torbox", "a")
    diag.note_no_matching_files("realdebrid", "b")
    diag.note_stream_tried()
    diag.note_stream_tried()
    detail = diag.build_detail(prefix="Stopped after 3 stream attempts")
    assert detail.startswith("Stopped after 3 stream attempts:")
    assert "not cached" in detail
    assert "no matching files" in detail


def test_build_detail_api_error_with_last():
    diag = _DownloadRunDiagnostics(streams_total=1)
    diag.note_api_error("torbox", "abc", ValueError("HTTP 403 Forbidden"))
    diag.note_stream_tried()
    detail = diag.build_detail()
    assert "API error" in detail
    assert "last:" in detail
    assert "403" in detail


def test_build_detail_length_cap():
    diag = _DownloadRunDiagnostics(streams_total=100)
    for _ in range(50):
        diag.note_not_cached("realdebrid", "x")
    diag.note_api_error("realdebrid", "x", RuntimeError("x" * 200))
    detail = diag.build_detail()
    assert len(detail) <= 480


def test_record_and_get_last_job():
    dl = _make_downloader()
    item = MagicMock()
    item.id = 42
    item.log_string = "Test Item"

    with patch.object(dl, "_log_job_completion"):
        dl._record_last_job(item, "success", detail="ok", service="torbox")
    raw = dl.get_last_job()

    assert raw is not None
    assert raw["item_id"] == 42
    assert raw["outcome"] == "success"
    assert raw["detail"] == "ok"
    assert raw["service"] == "torbox"
    assert raw["completed_at"]


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
    dl.subtitles_enabled = False
    dl._last_job = None

    dl._acquire_job_slot = MagicMock()
    dl._available_services = MagicMock(return_value=[])

    item = MagicMock()
    item.id = 7
    item.log_string = "Test Movie"
    item.streams = []

    results = list(dl.run(item))

    assert len(results) == 1
    assert results[0].run_at is not None
    job = dl.get_last_job()
    assert job is not None
    assert job["outcome"] == "deferred"
    assert job["item_id"] == 7


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
    dl.subtitles_enabled = False
    dl._last_job = None

    dl._acquire_job_slot = MagicMock()
    dl._available_services = MagicMock(return_value=[svc])
    dl._any_service_subscription_active = MagicMock(return_value=True)
    dl._log_job_completion = MagicMock()

    item = MagicMock()
    item.id = 99
    item.log_string = "Empty Movie"
    item.streams = []

    list(dl.run(item))

    job = dl.get_last_job()
    assert job is not None
    assert job["outcome"] == "failed"
    assert "0 streams" in (job["detail"] or "")
