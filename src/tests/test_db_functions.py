# tests/test_db_functions.py
from __future__ import annotations

import pytest
from RTN import ParsedData, Torrent

from program.db.db_functions import (
    get_item_by_external_id,
    item_exists_by_any_id,
)
from program.media.item import Episode, MediaItem, Movie, Season, Show
from program.media.stream import Stream, StreamBlacklistRelation, StreamRelation


def _torrent(rt: str, ih: str, pt: str, rank=100, lev=0.9) -> Torrent:
    pd = ParsedData(parsed_title=pt, raw_title=rt)
    return Torrent(
        raw_title=rt, infohash=ih, data=pd, fetch=True, rank=rank, lev_ratio=lev
    )


def _movie(tmdb_id: str, imdb_id: str | None = None, title="Movie") -> Movie:
    return Movie(
        {"title": title, "tmdb_id": tmdb_id, "imdb_id": imdb_id, "type": "movie"}
    )


def _show_tree(
    tvdb: str, seasons: list[int], eps: int
) -> tuple[Show, list[Season], list[Episode]]:
    show = Show({"title": "Show", "tvdb_id": tvdb, "type": "show"})
    all_s, all_e = [], []
    for s in seasons:
        season = Season({"number": s, "tvdb_id": f"{tvdb}-{s}", "type": "season"})
        season.parent = show
        season.parent_id = show.id
        all_s.append(season)
        for e in range(1, eps + 1):
            ep = Episode({"number": e, "tvdb_id": f"{tvdb}-{s}-{e}", "type": "episode"})
            ep.parent = season
            ep.parent_id = season.id
            all_e.append(ep)
    show.seasons = all_s
    for s in all_s:
        s.episodes = [e for e in all_e if e.parent_id == s.id]
    return show, all_s, all_e


def test_item_exists_by_any_id_paths(test_scoped_db_session):
    mov = _movie("30002", "tt30002", title="Exists Check")
    test_scoped_db_session.add(mov)
    test_scoped_db_session.commit()

    assert item_exists_by_any_id(
        item_id=mov.id,
        tvdb_id=None,
        tmdb_id=None,
        imdb_id=None,
        session=test_scoped_db_session,
    )
    assert item_exists_by_any_id(
        item_id=None,
        tvdb_id=None,
        tmdb_id=30002,
        imdb_id=None,
        session=test_scoped_db_session,
    )
    assert item_exists_by_any_id(
        item_id=None,
        tvdb_id=None,
        tmdb_id=None,
        imdb_id="tt30002",
        session=test_scoped_db_session,
    )


def test_item_exists_by_any_id_negative(test_scoped_db_session):
    assert not item_exists_by_any_id(
        item_id=999999,
        tvdb_id=None,
        tmdb_id=None,
        imdb_id=None,
        session=test_scoped_db_session,
    )


def test_get_item_by_external_id_movie(test_scoped_db_session):
    mov = _movie("42", "tt0000042", title="Lookup Movie")
    test_scoped_db_session.add(mov)
    test_scoped_db_session.commit()

    found = get_item_by_external_id(imdb_id="tt0000042", session=test_scoped_db_session)
    assert found is not None
    assert found.title == "Lookup Movie"


def test_get_item_by_external_id_requires_id():
    with pytest.raises(ValueError, match="At least one"):
        get_item_by_external_id()
