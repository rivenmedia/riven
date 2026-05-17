from datetime import datetime, timedelta
from unittest.mock import Mock, patch

import pytest

from program.media.item import Movie
from program.services.downloaders import Downloader
from program.utils.request import CircuitBreakerOpen


@pytest.fixture
def downloader():
    """Create a Downloader with one mocked initialized service."""
    d = Downloader()
    mock_service = Mock()
    mock_service.key = "torbox"
    mock_service.API_RATE_PER_SECOND = 5.0
    mock_service.get_instant_availability = Mock()
    mock_service.add_torrent = Mock()
    mock_service.get_torrent_info = Mock()
    mock_service.select_files = Mock()
    mock_service.delete_torrent = Mock()
    mock_service.get_user_info = Mock(return_value=Mock(premium_status="premium"))
    d.initialized_services = [mock_service]
    d.service = mock_service
    d.initialized = True
    d.min_job_interval_seconds = 0
    return d


@pytest.fixture
def mock_item():
    item = Mock(spec=Movie)
    item.id = "test_item_1"
    item.log_string = "Test Movie (2023)"
    item.active_stream = None
    item.last_state = None
    item.is_parent_blocked = Mock(return_value=False)
    item.streams = [Mock()]
    item.blacklist_stream = Mock()
    return item


def test_service_cooldown_prevents_processing(downloader, mock_item):
    future = datetime.now() + timedelta(minutes=2)
    downloader._service_cooldowns["torbox"] = future

    with patch.object(downloader, "_acquire_job_slot"):
        result = list(downloader.run(mock_item))

    assert len(result) == 1
    assert result[0].media_items == [mock_item]
    assert result[0].run_at == future

    downloader.service.get_instant_availability.assert_not_called()


def test_circuit_breaker_sets_cooldown(downloader, mock_item):
    downloader.service.get_instant_availability.side_effect = CircuitBreakerOpen(
        "api.torbox.app"
    )

    with patch.object(downloader, "_acquire_job_slot"):
        with patch.object(downloader, "_space_after_stream_attempt"):
            result = list(downloader.run(mock_item))

    assert "torbox" in downloader._service_cooldowns
    assert len(result) == 1
    assert result[0].run_at is not None


def test_successful_download_clears_cooldown(downloader, mock_item):
    downloader._service_cooldowns["torbox"] = datetime.now() - timedelta(seconds=1)
    mock_item.streams[0].infohash = "abc123"

    container = Mock()
    container.torrent_id = "tid"
    container.torrent_info = Mock()
    container.files = [Mock()]

    with patch.object(downloader, "_acquire_job_slot"):
        with patch.object(
            downloader, "validate_stream_on_service", return_value=container
        ):
            with patch.object(
                downloader,
                "download_cached_stream_on_service",
                return_value=Mock(id="tid", info=Mock(), infohash="abc123", container=container),
            ):
                with patch.object(downloader, "update_item_attributes", return_value=True):
                    list(downloader.run(mock_item))

    assert downloader._service_cooldowns == {}


def test_pause_until_matches_earliest_cooldown(downloader):
    s1 = Mock(key="a", API_RATE_PER_SECOND=1.0)
    s2 = Mock(key="b", API_RATE_PER_SECOND=1.0)
    downloader.initialized_services = [s1, s2]

    t1 = datetime.now() + timedelta(minutes=5)
    t2 = datetime.now() + timedelta(minutes=2)
    downloader._service_cooldowns = {"a": t1, "b": t2}

    assert downloader.pause_until() == t2
