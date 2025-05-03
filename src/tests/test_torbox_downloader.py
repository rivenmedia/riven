import json

import pytest

from program.services.downloaders import torbox
from program.services.downloaders.torbox import (
    TorBoxDownloader,
    add_torrent,
    get_instant_availability,
    get_status,
    get_torrents,
)
from program.settings.manager import settings_manager as settings


@pytest.fixture
def downloader(instant, upload, status, status_all, delete):
    """Instance of TorBoxDownloader with API calls mocked"""
    # mock API calls
    _get = torbox.get
    def get(url, **params):
        match url:
            case "user":
                return {"data": { "user": { "isPremium": True, "premiumUntil": 1735514599, } } }
            case "torrents/checkcached":
                return instant(url, **params)
            case "torrents/createtorrent":
                return upload(url, **params)
            case "torrents/controltorrent":
                return delete(url, **params)
            case "torrents/mylist":
                if params.get("id", False):
                    return status(url, **params)
                else:
                    return status_all(url, **params)
            case _:
                raise Exception("unmatched api call")
    torbox.get = get

    TorBox_settings = settings.settings.downloaders.torbox
    TorBox_settings.enabled = True
    TorBox_settings.api_key = "key"

    downloader = TorBoxDownloader()
    assert downloader.initialized
    yield downloader

    # tear down mock
    torbox.get = get


## Downloader tests
def test_process_hashes(downloader):
    hashes = downloader.process_hashes(["abc"], None, [False, True])
    assert len(hashes) == 1


def test_download_cached(downloader):
    torrent_id = downloader.download_cached({"hash": "abc"})
    assert torrent_id


def test_get_torrent_names(downloader):
    names = downloader.get_torrent_names(123)
    assert names == ("Ubuntu 24.04", None)


## API parsing tests
def test_get_instant_availability(instant):
    torbox.get = instant
    infohashes = [UBUNTU]
    availability = get_instant_availability(infohashes)
    assert len(availability[0].get("files", [])) == 2


def test_get_instant_availability_unavailable(instant_unavailable):
    torbox.get = instant_unavailable
    infohashes = [UBUNTU]
    availability = get_instant_availability(infohashes)
    assert availability[0]["hash"] == UBUNTU


def test_add_torrent(upload):
    torbox.get = upload
    torrent_id = add_torrent(UBUNTU)
    assert torrent_id == 251993753


def test_add_torrent_cached(upload_ready):
    torbox.get = upload_ready
    torrent_id = add_torrent(UBUNTU)
    assert torrent_id == 251993753


def test_get_status(status):
    torbox.get = status
    torrent_status = get_status(251993753)
    assert torrent_status["filename"] == "Ubuntu 24.04"


def test_get_status_unfinished(status_downloading):
    torbox.get = status_downloading
    torrent_status = get_status(251993753)
    assert torrent_status["status"] == "Downloading"


def test_get_torrents(status_all):
    torbox.get = status_all
    torrents = get_torrents()
    assert torrents[0]["status"] == "Ready"


def test_delete(delete):
    torbox.get = delete
    delete(123)


# Example requests - taken from real API calls
UBUNTU = "3648baf850d5930510c1f172b534200ebb5496e6"
@pytest.fixture
def instant():
    """GET /torrents/checkcached?hash=infohash (torrent available)"""
    with open("src/tests/test_data/torbox_magnet_instant.json") as f:
        body = json.load(f)
    return lambda url, **params: body

@pytest.fixture
def instant_unavailable():
    """GET /torrents/checkcached?hash=infohash  (torrent unavailable)"""
    with open("src/tests/test_data/torbox_magnet_instant_unavailable.json") as f:
        body = json.load(f)
    return lambda url, **params: body

@pytest.fixture
def upload():
    """POST /torrents/createtorrent (torrent not ready yet)"""
    with open("src/tests/test_data/torbox_magnet_upload_not_ready.json") as f:
        body = json.load(f)
    return lambda url, **params: body

@pytest.fixture
def upload_ready():
    """GET /torrents/createtorrent (torrent ready)"""
    with open("src/tests/test_data/torbox_magnet_upload_ready.json") as f:
        body = json.load(f)
    return lambda url, **params: body

@pytest.fixture
def status():
    """GET /torrents/mylist?id=123 (debrid links ready)"""
    with open("src/tests/test_data/torbox_magnet_status_one_ready.json") as f:
        body = json.load(f)
    return lambda url, **params: body

@pytest.fixture
def status_downloading():
    """GET /torrents/mylist?id=123 (debrid links not ready yet)"""
    with open("src/tests/test_data/torbox_magnet_status_one_downloading.json") as f:
        body = json.load(f)
    return lambda url, **params: body

@pytest.fixture
def status_all():
    """GET /torrents/mylist (gets a list of all links instead of a single object)"""
    # The body is the same as a single item, but with all your magnets in a list.
    with open("src/tests/test_data/torbox_magnet_status_one_ready.json") as f:
        body = json.load(f)
    return lambda url, **params: {"status": "success", "data": {"magnets": [body["data"]["magnets"]]}}

@pytest.fixture
def delete():
    """POST /torrents/controltorrent (delete torrent)"""
    with open("src/tests/test_data/torbox_magnet_delete.json") as f:
        body = json.load(f)
    return lambda url, **params: body

