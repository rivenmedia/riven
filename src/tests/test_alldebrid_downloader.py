import json

import pytest
from unittest.mock import patch

from program.services.downloaders import alldebrid
from program.services.downloaders.alldebrid import (
    AllDebridDownloader,
)
from program.services.downloaders.models import (
    VIDEO_EXTENSIONS,
    DebridFile,
    TorrentContainer,
    TorrentInfo,
    DownloadStatus,
)
from program.settings.manager import settings_manager as settings
from program.utils.request import HttpMethod


@pytest.fixture
def downloader(user, upload, status, status_all, files, delete):
    """Instance of AllDebridDownloader with API calls mocked"""

    def execute(self, method: HttpMethod, endpoint: str, **kwargs) -> dict:
        params = kwargs.get("params", {})
        match endpoint:
            case "user":
                return user()["data"]
            case "magnet/upload":
                return upload(endpoint, **params)["data"]
            case "magnet/delete":
                return delete(endpoint, **params)["data"]
            case "magnet/status":
                if params.get("id", False):
                    return status(endpoint, **params)["data"]
                else:
                    return status_all(endpoint, **params)["data"]
            case "magnet/files":
                return files(endpoint, **params)["data"]
            case _:
                raise Exception("unmatched api call %s" % endpoint)

    with patch.object(alldebrid.AllDebridRequestHandler, 'execute', execute):
        alldebrid_settings = settings.settings.downloaders.all_debrid
        alldebrid_settings.enabled = True
        alldebrid_settings.api_key = "key"

        downloader = AllDebridDownloader()
        assert downloader.initialized
        yield downloader


## DownloaderBase tests
def test_validate(downloader):
    assert downloader.validate() == True


def test_get_instant_availability(downloader):
    assert downloader.get_instant_availability(MAGNET, "movie") == TorrentContainer(
        infohash=MAGNET,
        files=[DebridFile.create(filename="", filesize_bytes=123, filetype="movie")],
    )


def test_add_torrent(downloader):
    assert downloader.add_torrent(MAGNET) == ID


def test_select_files(downloader):
    assert downloader.select_files(ID, [1, 2, 3]) is None


def test_get_torrent_info(downloader):
    torrent_info = downloader.get_torrent_info(ID)
    assert torrent_info.id == int(ID)
    assert torrent_info.name == "Big Buck Bunny"
    assert torrent_info.status == DownloadStatus.READY
    assert torrent_info.bytes == 276445467
    assert torrent_info.progress == 100


def test_delete_torrent(downloader):
    assert downloader.delete_torrent(ID) is None  # TODO: assert that delete was called


# MAGNET is the infohash of the torrent.
MAGNET = "dd8255ecdc7ca55fb0bbf81323d87062db1f6d1c"
# ID is AllDebrid's internal ID for this torrent.
ID = "264640947"


@pytest.fixture
def user():
    """GET /user"""
    with open("src/tests/test_data/alldebrid_user.json") as f:
        body = json.load(f)
    return lambda: body


@pytest.fixture
def upload():
    """GET /magnet/upload?magnets[]=infohash (torrent not ready yet)"""
    with open("src/tests/test_data/alldebrid_magnet_upload_not_ready.json") as f:
        body = json.load(f)
    return lambda url, **params: body


@pytest.fixture
def upload_ready():
    """GET /magnet/upload?magnets[]=infohash (torrent ready)"""
    with open("src/tests/test_data/alldebrid_magnet_upload_ready.json") as f:
        body = json.load(f)
    return lambda url, **params: body


@pytest.fixture
def status():
    """GET /magnet/status?id=123 (debrid links ready)"""
    with open("src/tests/test_data/alldebrid_magnet_status_one_ready.json") as f:
        body = json.load(f)
    return lambda url, **params: body


@pytest.fixture
def status_downloading():
    """GET /magnet/status?id=123 (debrid links not ready yet)"""
    with open("src/tests/test_data/alldebrid_magnet_status_one_downloading.json") as f:
        body = json.load(f)
    return lambda url, **params: body


@pytest.fixture
def status_all():
    """GET /magnet/status (gets a list of all links instead of a single object)"""
    # The body is the same as a single item, but with all your magnets in a list.
    with open("src/tests/test_data/alldebrid_magnet_status_one_ready.json") as f:
        body = json.load(f)
    return lambda url, **params: {
        "status": "success",
        "data": {"magnets": [body["data"]["magnets"]]},
    }


@pytest.fixture
def files():
    """GET /magnet/files?id[]=123 (gets files and links for a magnet)"""
    with open("src/tests/test_data/alldebrid_magnet_files.json") as f:
        body = json.load(f)
    return lambda url, **params: body


@pytest.fixture
def delete():
    """GET /delete?id=123"""
    with open("src/tests/test_data/alldebrid_magnet_delete.json") as f:
        body = json.load(f)
    return lambda url, **params: body
