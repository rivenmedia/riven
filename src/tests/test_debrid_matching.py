"""Downloader.match_file_to_item file-to-media matching."""

from types import SimpleNamespace
from unittest.mock import Mock

from RTN import ParsedData
from program.media.item import Episode, Movie, Season, Show
from program.services.downloaders import Downloader
from program.services.downloaders.models import (
    DebridFile,
    DownloadedTorrent,
    TorrentContainer,
    TorrentInfo,
)


def _downloader() -> Downloader:
    dl = Downloader.__new__(Downloader)
    dl.service = Mock()
    dl._update_attributes = Mock()
    return dl


def _file(path: str) -> DebridFile:
    return DebridFile(
        filename=path,
        file_id=1,
        filesize=800_000_000,
    )


def _parsed(raw: str, *, seasons: list[int] | None = None, episodes: list[int] | None = None) -> ParsedData:
    return ParsedData(
        parsed_title=raw,
        raw_title=raw,
        seasons=seasons or [],
        episodes=episodes or [],
    )


def _download() -> DownloadedTorrent:
    return DownloadedTorrent(
        id="tid",
        infohash="abc",
        info=TorrentInfo(id="tid", name="n"),
        container=TorrentContainer(infohash="abc"),
    )


def test_match_file_to_item_movie():
    dl = _downloader()
    item = Movie({"imdb_id": "tt1375666", "requested_by": "user", "title": "Inception"})
    file_data = _parsed("Inception 2010 1080p")
    assert (
        dl.match_file_to_item(
            item, file_data, _file("Inception.mkv"), _download(), service=dl.service
        )
        is True
    )
    dl._update_attributes.assert_called_once()


def test_match_file_to_item_episode():
    dl = _downloader()
    parent_show = Show(
        {"imdb_id": "tt1405406", "requested_by": "user", "title": "The Vampire Diaries"}
    )
    parent_season = Season({"number": 1})
    episode = Episode({"number": 1})
    parent_season.add_episode(episode)
    parent_show.add_season(parent_season)
    episode.parent = parent_season
    parent_season.parent = parent_show

    file_data = _parsed(
        "The Vampire Diaries S01E01",
        seasons=[1],
        episodes=[1],
    )
    assert (
        dl.match_file_to_item(
            episode,
            file_data,
            _file("The Vampire Diaries s01e01.mkv"),
            _download(),
            show=parent_show,
            service=dl.service,
        )
        is True
    )


def test_match_file_to_item_season():
    dl = _downloader()
    show = Show(
        {"imdb_id": "tt1405406", "requested_by": "user", "title": "The Vampire Diaries"}
    )
    season = Season({"number": 1})
    episode1 = Episode({"number": 1})
    episode2 = Episode({"number": 2})
    season.add_episode(episode1)
    season.add_episode(episode2)
    show.add_season(season)

    file_data = _parsed("pack", seasons=[1], episodes=[1])
    assert (
        dl.match_file_to_item(
            season,
            file_data,
            _file("The Vampire Diaries s01e01.mkv"),
            _download(),
            show=show,
            service=dl.service,
        )
        is True
    )


def test_match_file_to_item_partial_season():
    dl = _downloader()
    show = Show({"imdb_id": "tt1405406", "requested_by": "user", "title": "Test Show"})
    season = Season({"number": 1})
    episode1 = Episode({"number": 1})
    episode2 = Episode({"number": 2})
    season.add_episode(episode1)
    season.add_episode(episode2)
    show.add_season(season)

    file_data = _parsed("e1", seasons=[1], episodes=[1])
    # Only one episode file for a 2-episode season — still matches that episode
    assert (
        dl.match_file_to_item(
            season,
            file_data,
            _file("show_s01e01.mkv"),
            _download(),
            show=show,
            service=dl.service,
        )
        is True
    )


def test_match_file_to_item_movie_wrong_type():
    dl = _downloader()
    item = Movie({"imdb_id": "tt1375666", "requested_by": "user", "title": "Inception"})
    file_data = _parsed("ep", seasons=[1], episodes=[1])
    assert (
        dl.match_file_to_item(
            item, file_data, _file("Inception.mkv"), _download(), service=dl.service
        )
        is False
    )
