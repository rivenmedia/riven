import time
from datetime import datetime, timedelta
from unittest.mock import Mock, patch

import pytest

from program.media.item import Movie
from program.services.downloaders import Downloader


@pytest.fixture
def downloader():
    d = Downloader()
    d.initialized = True
    d.initialized_services = [Mock(key="torbox", API_RATE_PER_SECOND=10.0)]
    d.min_job_interval_seconds = 0.15
    d._next_job_slot_at = 0.0
    return d


def test_acquire_job_slot_enforces_interval(downloader):
    downloader._acquire_job_slot()
    first = downloader._next_job_slot_at

    downloader._acquire_job_slot()
    second = downloader._next_job_slot_at

    assert second - first >= downloader.min_job_interval_seconds * 0.95


def test_compute_min_job_interval_uses_override():
    with patch(
        "program.services.downloaders.settings_manager.settings.downloaders.min_job_interval_seconds",
        2.5,
    ):
        d = Downloader()
        assert d._compute_min_job_interval() == 2.5


def test_pause_until_when_all_services_cooling(downloader):
    future = datetime.now() + timedelta(minutes=2)
    downloader._service_cooldowns["torbox"] = future

    assert downloader.pause_until() == future


def test_pause_until_none_when_service_available(downloader):
    downloader._service_cooldowns["torbox"] = datetime.now() - timedelta(seconds=1)

    assert downloader.pause_until() is None
