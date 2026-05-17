from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from program.media.models import ActiveStream
from program.media.state import States
from program.services.downloaders.models import TorrentContainer, DebridFile
from routers.secure.items import _check_active_stream_availability


@pytest.fixture
def downloader():
    d = Mock()
    d.initialized_services = []
    return d


def _movie_with_pin():
    item = Mock()
    item.type = "movie"
    item.active_stream = ActiveStream(infohash="abc123", id="tid-1")
    item.last_state = States.Downloaded
    return item


def test_check_availability_reports_cached_service(downloader):
    item = _movie_with_pin()
    service = Mock()
    service.key = "realdebrid"
    downloader.initialized_services = [service]
    container = TorrentContainer(
        infohash="abc123",
        files=[DebridFile(file_id=1, filename="movie.mkv", filesize=1_000_000)],
    )
    downloader.validate_stream_on_service = Mock(return_value=container)

    result = _check_active_stream_availability(downloader, item)

    assert result.available is True
    assert result.primary_service == "realdebrid"
    assert result.services[0].file_count == 1
    downloader.validate_stream_on_service.assert_called_once()
    probe = downloader.validate_stream_on_service.call_args[0][0]
    assert probe.infohash == "abc123"


def test_check_availability_no_active_stream(downloader):
    item = Mock()
    item.type = "movie"
    item.active_stream = None

    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        _check_active_stream_availability(downloader, item)

    assert exc.value.status_code == 400
