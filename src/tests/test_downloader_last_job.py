from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

from program.services.downloaders import Downloader


def _make_downloader() -> Downloader:
    dl = Downloader.__new__(Downloader)
    dl._last_job = None
    dl.initialized_services = []
    dl._service_cooldowns = {}
    return dl


def test_record_and_get_last_job():
    dl = _make_downloader()
    item = MagicMock()
    item.id = 42

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
