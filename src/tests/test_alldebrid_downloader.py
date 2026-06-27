import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from program.services.downloaders.alldebrid import (
    AllDebridAPI,
    AllDebridDirectory,
    AllDebridDownloader,
    AllDebridFile,
    AllDebridMagnetLinkEntry,
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
    downloader.api = MagicMock(spec=AllDebridAPI)
    return downloader


# --- Model parsing ---


def test_status_response_parses_links_not_files():
    """MagnetInfo.links is populated from the API 'links' field, not a nonexistent 'files' field."""
    body = load_fixture("alldebrid_magnet_status_one_ready.json")
    parsed = AllDebridResponse[AllDebridMagnetStatusResponse].model_validate(
        {"data": body}
    )
    magnets = parsed.data.data.magnets
    assert len(magnets) == 1
    magnet = magnets[0]
    assert isinstance(magnet, AllDebridMagnetStatusResponse.MagnetInfo)
    assert magnet.links is not None
    assert len(magnet.links) == 2
    assert magnet.links[0].link == "https://alldebrid.com/f/REDACTED"
    assert magnet.links[0].filename == "ubuntu-24.04-desktop-amd64.iso"


def test_status_response_normalizes_single_magnet_dict_to_list():
    """normalize_magnets wraps a bare dict (single magnet) into a list."""
    body = load_fixture("alldebrid_magnet_status_one_ready.json")
    parsed = AllDebridResponse[AllDebridMagnetStatusResponse].model_validate(
        {"data": body}
    )
    assert len(parsed.data.data.magnets) == 1


def test_status_response_downloading_has_empty_links():
    body = load_fixture("alldebrid_magnet_status_one_downloading.json")
    parsed = AllDebridResponse[AllDebridMagnetStatusResponse].model_validate(
        {"data": body}
    )
    magnet = parsed.data.data.magnets[0]
    assert isinstance(magnet, AllDebridMagnetStatusResponse.MagnetInfo)
    assert magnet.status == "Downloading"
    assert magnet.links == []


def test_link_entry_files_without_l_defaults_to_empty_string():
    """Files inside links[].files have no 'l' field; AllDebridFile.l should default to ''."""
    entry = AllDebridMagnetLinkEntry.model_validate(
        {
            "link": "https://alldebrid.com/f/ABC",
            "filename": "movie.mkv",
            "size": 2_000_000_000,
            "files": [{"n": "movie.mkv", "s": 2_000_000_000}],
        }
    )
    assert isinstance(entry.files[0], AllDebridFile)
    assert entry.files[0].l == ""


def test_link_entry_directory_parsed_correctly():
    """A directory entry inside links[].files is parsed as AllDebridDirectory."""
    entry = AllDebridMagnetLinkEntry.model_validate(
        {
            "link": "https://alldebrid.com/f/XYZ",
            "filename": "Show.S01E01.mkv",
            "size": 1_500_000_000,
            "files": [
                {
                    "n": "Show Season 1",
                    "e": [
                        {"n": "Show.S01E01.mkv", "s": 800_000_000},
                        {"n": "Show.S01E02.mkv", "s": 700_000_000},
                    ],
                }
            ],
        }
    )
    assert isinstance(entry.files[0], AllDebridDirectory)
    assert len(entry.files[0].e) == 2


# --- _get_magnet_files ---


def test_get_magnet_files_extracts_multi_link_ready_magnet():
    downloader = make_downloader()
    body = load_fixture("alldebrid_magnet_status_one_ready.json")
    downloader.api.session.post.return_value = make_mock_response(body)

    result = downloader._get_magnet_files(251993753)

    assert result is not None
    assert len(result) == 2
    assert result[0].n == "ubuntu-24.04-desktop-amd64.iso"
    assert result[0].s == 6114656256
    assert result[0].l == "https://alldebrid.com/f/REDACTED"


def test_get_magnet_files_injects_link_url_when_file_has_no_l():
    """Files with no 'l' in links[].files should inherit the link entry's URL."""
    downloader = make_downloader()
    body = {
        "status": "success",
        "data": {
            "magnets": {
                "id": 1,
                "filename": "movie.mkv",
                "size": 2_000_000_000,
                "status": "Ready",
                "statusCode": 4,
                "uploadDate": 1727454272,
                "completionDate": 1727454803,
                "links": [
                    {
                        "link": "https://alldebrid.com/f/MOVIE",
                        "filename": "movie.mkv",
                        "size": 2_000_000_000,
                        "files": [{"n": "movie.mkv", "s": 2_000_000_000}],
                    }
                ],
            }
        },
    }
    downloader.api.session.post.return_value = make_mock_response(body)

    result = downloader._get_magnet_files(1)

    assert result is not None
    assert len(result) == 1
    assert result[0].l == "https://alldebrid.com/f/MOVIE"


def test_get_magnet_files_falls_back_to_link_entry_when_files_absent():
    """When links[].files is None, the link entry itself is used as the file."""
    downloader = make_downloader()
    body = {
        "status": "success",
        "data": {
            "magnets": {
                "id": 2,
                "filename": "movie.mkv",
                "size": 2_000_000_000,
                "status": "Ready",
                "statusCode": 4,
                "uploadDate": 1727454272,
                "completionDate": 1727454803,
                "links": [
                    {
                        "link": "https://alldebrid.com/f/MOVIE",
                        "filename": "movie.mkv",
                        "size": 2_000_000_000,
                        "files": None,
                    }
                ],
            }
        },
    }
    downloader.api.session.post.return_value = make_mock_response(body)

    result = downloader._get_magnet_files(2)

    assert result is not None
    assert len(result) == 1
    assert result[0].n == "movie.mkv"
    assert result[0].s == 2_000_000_000
    assert result[0].l == "https://alldebrid.com/f/MOVIE"


def test_get_magnet_files_extracts_nested_directory():
    """Files inside a directory in links[].files are extracted recursively."""
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
                "links": [
                    {
                        "link": "https://alldebrid.com/f/SEASON",
                        "filename": "Show.S01E01.mkv",
                        "size": 3_000_000_000,
                        "files": [
                            {
                                "n": "Show Season 1",
                                "e": [
                                    {"n": "Show.S01E01.mkv", "s": 1_500_000_000},
                                    {"n": "Show.S01E02.mkv", "s": 1_500_000_000},
                                ],
                            }
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
    assert result[0].l == "https://alldebrid.com/f/SEASON"
    assert result[1].n == "Show.S01E02.mkv"
    assert result[1].l == "https://alldebrid.com/f/SEASON"


def test_get_magnet_files_returns_none_when_not_ready():
    """Returns None when the magnet has empty links (still downloading)."""
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
