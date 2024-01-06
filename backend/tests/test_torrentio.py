import pytest
from unittest.mock import Mock
from program.scrapers.torrentio import Torrentio, TorrentioConfig


def test_torrentio_initialization():
    torrentio = Torrentio(None)
    assert torrentio is not None
    assert torrentio.key == "torrentio"

@pytest.mark.parametrize("enabled,filter,expected", [
    (True, "sort=qusize%7Cqualityfilter=480p,scr,cam,unknown", True),
    (False, None, False),
])
def test_validate_settings(enabled, filter, expected):
    settings = TorrentioConfig(enabled=enabled, filter=filter)
    torrentio = Torrentio(None)
    torrentio.settings = settings
    assert torrentio.validate_settings() == expected

def test_api_scrape_basic():
    torrentio = Torrentio(None)
    torrentio.settings = TorrentioConfig(enabled=True, filter="sort=qualitysize%7Cqualityfilter=480p,scr,cam,unknown")
    item = Mock() # TODO: Create a better mock item
    result = torrentio.api_scrape(item)
    assert result is not None
    # Need to add more.. but this is a start