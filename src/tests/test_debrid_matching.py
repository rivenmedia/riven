from types import SimpleNamespace

from program.downloaders.realdebrid import _matches_item
from program.media.item import Episode, Movie, Season, Show


def test_matches_item_movie():
    torrent_info = SimpleNamespace(
        files=[
            SimpleNamespace(path="Inception.mkv", selected=1, bytes=2_000_000_000),
        ]
    )
    item = Movie({"imdb_id": "tt1375666", "requested_by": "user", "title": "Inception"})
    assert _matches_item(torrent_info, item) == True

def test_matches_item_episode():
    torrent_info = SimpleNamespace(
        files=[
            SimpleNamespace(path="The Vampire Diaries s01e01.mkv", selected=1, bytes=800_000_000),
        ]
    )
    parent_show = Show({"imdb_id": "tt1405406", "requested_by": "user", "title": "The Vampire Diaries"})
    parent_season = Season({"number": 1})
    episode = Episode({"number": 1})
    parent_season.add_episode(episode)
    parent_show.add_season(parent_season)
    episode.parent = parent_season
    parent_season.parent = parent_show

    assert _matches_item(torrent_info, episode) == True

def test_matches_item_season():
    torrent_info = SimpleNamespace(
        files=[
            SimpleNamespace(path="The Vampire Diaries s01e01.mkv", selected=1, bytes=800_000_000),
            SimpleNamespace(path="The Vampire Diaries s01e02.mkv", selected=1, bytes=800_000_000),
        ]
    )
    show = Show({"imdb_id": "tt1405406", "requested_by": "user", "title": "The Vampire Diaries"})
    season = Season({"number": 1})
    episode1 = Episode({"number": 1})
    episode2 = Episode({"number": 2})
    season.add_episode(episode1)
    season.add_episode(episode2)
    show.add_season(season)

    assert _matches_item(torrent_info, season) == True

def test_matches_item_partial_season():
    torrent_info = SimpleNamespace(
        files=[
            SimpleNamespace(path="show_s01e01.mkv", selected=1, bytes=800_000_000),
        ]
    )
    show = Show({"imdb_id": "tt1405406", "requested_by": "user", "title": "Test Show"})
    season = Season({"number": 1})
    episode1 = Episode({"number": 1})
    episode2 = Episode({"number": 2})
    season.add_episode(episode1)
    season.add_episode(episode2)
    show.add_season(season)

    assert _matches_item(torrent_info, season) == False

def test_matches_item_no_files():
    torrent_info = SimpleNamespace()
    item = Movie({"imdb_id": "tt1375666", "requested_by": "user", "title": "Inception"})
    assert _matches_item(torrent_info, item) == False

def test_matches_item_no_selected_files():
    torrent_info = SimpleNamespace(
        files=[
            SimpleNamespace(path="movie.mp4", selected=0, bytes=2_000_000_000),
        ]
    )
    item = Movie({"imdb_id": "tt1375666", "requested_by": "user", "title": "Inception"})
    assert _matches_item(torrent_info, item) == False