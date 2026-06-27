import json
from pathlib import Path
from unittest.mock import MagicMock

from program.services.downloaders.alldebrid import (
    AllDebridAPI,
    AllDebridDirectory,
    AllDebridDownloader,
    AllDebridFile,
    AllDebridMagnet,
    AllDebridMagnetStatusResponse,
    AllDebridResponse,
)

TEST_DATA = Path(__file__).parent / "test_data"


def load_fixture(name: str) -> dict:
    with open(TEST_DATA / name) as f:
        return json.load(f)


def make_mock_response(json_body: dict, status_code: int = 200) -> MagicMock:
    resp = MagicMock()
    resp.ok = status_code < 400
    resp.status_code = status_code
    resp.json.return_value = json_body
    return resp


def make_downloader() -> AllDebridDownloader:
    """Construct an AllDebridDownloader without triggering __init__ settings validation."""
    downloader = object.__new__(AllDebridDownloader)
    downloader.key = "alldebrid"
    downloader.api = MagicMock()
    return downloader


# --- Model parsing ---


def test_status_response_parses_files():
    """MagnetInfo.files is populated from the v4.1 API 'files' field."""
    body = load_fixture("alldebrid_magnet_status_one_ready.json")
    parsed = AllDebridResponse[AllDebridMagnetStatusResponse].model_validate(
        {"data": body}
    )
    magnets = parsed.data.data.magnets
    assert len(magnets) == 1
    magnet = magnets[0]
    assert isinstance(magnet, AllDebridMagnetStatusResponse.MagnetInfo)
    assert magnet.files is not None
    assert len(magnet.files) == 2
    assert isinstance(magnet.files[0], AllDebridFile)
    assert magnet.files[0].n == "ubuntu-24.04-desktop-amd64.iso"
    assert magnet.files[0].l == "https://alldebrid.com/f/REDACTED"


def test_status_response_normalizes_single_magnet_dict_to_list():
    """normalize_magnets wraps a bare dict (single magnet) into a list."""
    body = load_fixture("alldebrid_magnet_status_one_ready.json")
    parsed = AllDebridResponse[AllDebridMagnetStatusResponse].model_validate(
        {"data": body}
    )
    assert len(parsed.data.data.magnets) == 1


def test_status_response_downloading_has_no_files():
    body = load_fixture("alldebrid_magnet_status_one_downloading.json")
    parsed = AllDebridResponse[AllDebridMagnetStatusResponse].model_validate(
        {"data": body}
    )
    magnet = parsed.data.data.magnets[0]
    assert isinstance(magnet, AllDebridMagnetStatusResponse.MagnetInfo)
    assert magnet.status == "Downloading"
    assert magnet.files is None


def test_upload_response_parses_error_entry():
    """AllDebridMagnet.MagnetErrorInfo is parsed when AllDebrid rejects a magnet."""
    body = {
        "status": "success",
        "data": {
            "magnets": [
                {
                    "magnet": "magnet:?xt=urn:btih:invalid",
                    "error": "This is not a valid torrent",
                }
            ]
        },
    }
    parsed = AllDebridResponse[AllDebridMagnet].model_validate({"data": body})
    magnets = parsed.data.data.magnets
    assert len(magnets) == 1
    assert isinstance(magnets[0], AllDebridMagnet.MagnetErrorInfo)
    assert magnets[0].error == "This is not a valid torrent"


# --- _get_magnet_files ---


def test_get_magnet_files_extracts_flat_ready_magnet():
    downloader = make_downloader()
    body = load_fixture("alldebrid_magnet_status_one_ready.json")
    downloader.api.session.post.return_value = make_mock_response(body)

    result = downloader._get_magnet_files(251993753)

    assert result is not None
    assert len(result) == 2
    assert result[0].n == "ubuntu-24.04-desktop-amd64.iso"
    assert result[0].s == 6114656256
    assert result[0].l == "https://alldebrid.com/f/REDACTED"


def test_get_magnet_files_extracts_nested_directory():
    """Files inside a directory in files[] are extracted recursively with their own links."""
    downloader = make_downloader()
    body = {
        "status": "success",
        "data": {
            "magnets": {
                "id": 3,
                "filename": "Show.S01",
                "size": 3_000_000_000,
                "status": "Ready",
                "statusCode": 4,
                "uploadDate": 1727454272,
                "completionDate": 1727454803,
                "files": [
                    {
                        "n": "Show Season 1",
                        "e": [
                            {
                                "n": "Show.S01E01.mkv",
                                "s": 1_500_000_000,
                                "l": "https://alldebrid.com/f/EP1",
                            },
                            {
                                "n": "Show.S01E02.mkv",
                                "s": 1_500_000_000,
                                "l": "https://alldebrid.com/f/EP2",
                            },
                        ],
                    }
                ],
            }
        },
    }
    downloader.api.session.post.return_value = make_mock_response(body)

    result = downloader._get_magnet_files(3)

    assert result is not None
    assert len(result) == 2
    assert result[0].n == "Show.S01E01.mkv"
    assert result[0].l == "https://alldebrid.com/f/EP1"
    assert result[1].n == "Show.S01E02.mkv"
    assert result[1].l == "https://alldebrid.com/f/EP2"


def test_get_magnet_files_returns_none_when_not_ready():
    """Returns None when the magnet has no files (still downloading)."""
    downloader = make_downloader()
    body = load_fixture("alldebrid_magnet_status_one_downloading.json")
    downloader.api.session.post.return_value = make_mock_response(body)

    result = downloader._get_magnet_files(251993753)

    assert result is None


def test_get_magnet_files_returns_none_on_http_error():
    downloader = make_downloader()
    downloader.api.session.post.return_value = make_mock_response({}, status_code=500)

    result = downloader._get_magnet_files(999)

    assert result is None


# --- get_torrent_info ---


def test_get_torrent_info_ready():
    downloader = make_downloader()
    body = load_fixture("alldebrid_magnet_status_one_ready.json")
    downloader.api.session.post.return_value = make_mock_response(body)

    info = downloader.get_torrent_info(251993753)

    assert info.name == "Ubuntu 24.04"
    assert info.status == "Ready"
    assert info.bytes == 8869638144
    assert info.progress == 100.0


def test_get_torrent_info_downloading():
    downloader = make_downloader()
    body = load_fixture("alldebrid_magnet_status_one_downloading.json")
    downloader.api.session.post.return_value = make_mock_response(body)

    info = downloader.get_torrent_info(251993753)

    assert info.status == "Downloading"
    assert info.progress == 0.0
