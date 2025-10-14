from datetime import datetime, timedelta
from unittest.mock import Mock, patch

import pytest

from program.media.item import Movie
from program.services.downloaders import Downloader
from program.utils.request import CircuitBreakerOpen


@pytest.fixture
def downloader():
    """Create a Downloader instance with mocked service"""
    downloader = Downloader()
    # Mock the service to simulate circuit breaker behavior
    downloader.service = Mock()
    downloader.service.get_instant_availability = Mock()
    downloader.service.add_torrent = Mock()
    downloader.service.get_torrent_info = Mock()
    downloader.service.select_files = Mock()
    downloader.service.delete_torrent = Mock()
    downloader.initialized = True
    return downloader


@pytest.fixture
def mock_item():
    """Create a mock MediaItem for testing"""
    item = Mock(spec=Movie)
    item.id = "test_item_1"
    item.log_string = "Test Movie (2023)"
    item.file = None
    item.active_stream = None
    item.last_state = None
    item.is_parent_blocked = Mock(return_value=False)
    item.streams = [Mock()]
    item.blacklist_stream = Mock()
    return item


def test_service_cooldown_prevents_processing(downloader, mock_item):
    """Test that service cooldown prevents processing items"""
    # Set service in cooldown
    downloader._service_cooldown_until = datetime.now() + timedelta(minutes=2)

    # Run the downloader
    result = list(downloader.run(mock_item))

    # Should yield (item, next_attempt) tuple
    assert len(result) == 1
    assert isinstance(result[0], tuple)
    item, next_attempt = result[0]
    assert item == mock_item
    assert isinstance(next_attempt, datetime)

    # Service methods should not be called
    downloader.service.get_instant_availability.assert_not_called()
    downloader.service.add_torrent.assert_not_called()


def test_circuit_breaker_sets_cooldown(downloader, mock_item):
    """Test that circuit breaker exception sets service cooldown"""
    # Mock circuit breaker exception
    downloader.service.get_instant_availability.side_effect = CircuitBreakerOpen(
        "Circuit breaker OPEN"
    )

    # Run the downloader
    result = list(downloader.run(mock_item))

    # Should set cooldown and yield (item, next_attempt)
    assert downloader._service_cooldown_until is not None
    assert len(result) == 1
    assert isinstance(result[0], tuple)
    item, next_attempt = result[0]
    assert item == mock_item
    assert isinstance(next_attempt, datetime)

    # Cooldown should be approximately 2 minutes from now
    expected_cooldown = datetime.now() + timedelta(minutes=2)
    time_diff = abs(
        (downloader._service_cooldown_until - expected_cooldown).total_seconds()
    )
    assert time_diff < 5  # Allow 5 second tolerance


def test_successful_download_clears_cooldown(downloader, mock_item):
    """Test that successful download clears service cooldown"""
    # Set initial cooldown
    downloader._service_cooldown_until = datetime.now() + timedelta(minutes=2)

    # Mock successful download
    downloader.service.get_instant_availability.return_value = Mock()
    downloader.service.add_torrent.return_value = "torrent_id"
    downloader.service.get_torrent_info.return_value = Mock()
    downloader.service.select_files.return_value = None
    downloader.service.delete_torrent.return_value = None

    # Mock the update_item_attributes to return True (successful)
    with patch.object(downloader, "update_item_attributes", return_value=True):
        result = list(downloader.run(mock_item))

    # Should clear cooldown
    assert downloader._service_cooldown_until is None

    # Should yield the item
    assert len(result) == 1
    assert result[0] == mock_item


def test_max_retries_reached(downloader, mock_item):
    """Test that max retries are respected"""
    # Set retry count to max
    downloader._circuit_breaker_retries[mock_item.id] = 6

    # Mock circuit breaker exception
    downloader.service.get_instant_availability.side_effect = CircuitBreakerOpen(
        "Circuit breaker OPEN"
    )

    # Run the downloader
    result = list(downloader.run(mock_item))

    # Should yield just the item (not reschedule)
    assert len(result) == 1
    assert result[0] == mock_item

    # Retry count should be cleared
    assert mock_item.id not in downloader._circuit_breaker_retries


def test_cooldown_expires_naturally(downloader, mock_item):
    """Test that cooldown expires naturally"""
    # Set cooldown in the past
    downloader._service_cooldown_until = datetime.now() - timedelta(minutes=1)

    # Mock successful download
    downloader.service.get_instant_availability.return_value = Mock()
    downloader.service.add_torrent.return_value = "torrent_id"
    downloader.service.get_torrent_info.return_value = Mock()
    downloader.service.select_files.return_value = None
    downloader.service.delete_torrent.return_value = None

    # Mock the update_item_attributes to return True (successful)
    with patch.object(downloader, "update_item_attributes", return_value=True):
        result = list(downloader.run(mock_item))

    # Should process normally (not reschedule)
    assert len(result) == 1
    assert result[0] == mock_item

    # Service methods should be called
    downloader.service.get_instant_availability.assert_called_once()
