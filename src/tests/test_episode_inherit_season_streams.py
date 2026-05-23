from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch

from program.media.item import Episode, Season, Show
from program.media.state import States
from program.services.scrapers import Scraping
from program.services.scrapers.episode_streams import (
    _resolve_parents,
    episode_should_skip_scrape,
    inherit_parent_streams_for_episode,
)
from program.services.scrapers.shared import torrent_covers_episode
from program.state_transition import process_event


def _episode(*, number=3, absolute_number=None, season_number=1):
    show = MagicMock(spec=Show)
    season = MagicMock(spec=Season)
    season.number = season_number
    season.parent = show
    season.streams = []
    season.blacklisted_streams = []
    season.is_scraped = Mock(return_value=False)

    episode = MagicMock(spec=Episode)
    episode.number = number
    episode.absolute_number = absolute_number
    episode.parent = season
    episode.top_parent = show
    episode.streams = []
    episode.blacklisted_streams = []
    episode.log_string = f"S{season_number}E{number}"
    episode.is_scraped = Mock(
        side_effect=lambda: len(episode.streams) > 0
    )
    episode.filesystem_entry = None
    episode.available_in_vfs = False

    show.streams = []
    show.blacklisted_streams = []
    show.is_scraped = Mock(return_value=False)

    return episode, season, show


def test_torrent_covers_episode_by_episode_number():
    episode, _, _ = _episode(number=5)
    parsed = SimpleNamespace(episodes=[5], seasons=[])
    assert torrent_covers_episode(parsed, episode) is True


def test_torrent_covers_episode_by_season_number():
    episode, _, _ = _episode(number=3, season_number=2)
    parsed = SimpleNamespace(episodes=[], seasons=[2])
    assert torrent_covers_episode(parsed, episode) is True


def test_torrent_covers_episode_junk_without_seasons_or_episodes():
    episode, _, _ = _episode()
    parsed = SimpleNamespace(episodes=[], seasons=[])
    assert torrent_covers_episode(parsed, episode) is False


def test_resolve_parents_uses_parent_id_when_parent_not_loaded(monkeypatch):
    episode, season, show = _episode(number=1, season_number=1)
    episode.parent = None
    episode.parent_id = 99
    season.id = 99
    show.id = 7
    season.parent_id = 7

    monkeypatch.setattr(
        "program.db.db_functions.get_item_by_id",
        lambda item_id, **_: season if item_id == 99 else show,
    )

    resolved_season, resolved_show = _resolve_parents(episode)

    assert resolved_season is season
    assert resolved_show is show


def test_inherit_from_show_only_streams():
    episode, season, show = _episode(number=1, season_number=1)
    stream = Mock()
    stream.infohash = "aa" * 20
    stream.raw_title = "Show.Complete.S01"
    show.streams = [stream]
    show.is_scraped = Mock(return_value=True)
    season.is_scraped = Mock(return_value=False)

    parsed = SimpleNamespace(episodes=[], seasons=[1])

    with patch(
        "program.services.scrapers.episode_streams.parse_filename",
        return_value=parsed,
    ):
        linked = inherit_parent_streams_for_episode(episode)

    assert linked == 1
    assert stream in episode.streams


def test_inherit_from_season_dedupes_show_duplicate():
    episode, season, show = _episode(number=2, season_number=1)
    stream = Mock()
    stream.infohash = "bb" * 20
    stream.raw_title = "Season.Pack.S01"
    show.streams = [stream]
    season.streams = [stream]
    show.is_scraped = Mock(return_value=True)
    season.is_scraped = Mock(return_value=True)

    parsed = SimpleNamespace(episodes=[2], seasons=[1])

    with patch(
        "program.services.scrapers.episode_streams.parse_filename",
        return_value=parsed,
    ):
        linked = inherit_parent_streams_for_episode(episode)

    assert linked == 1
    assert episode.streams.count(stream) == 1


def test_episode_should_skip_scrape_when_filesystem_entry():
    episode, _, _ = _episode()
    episode.filesystem_entry = Mock()
    assert episode_should_skip_scrape(episode) is True


def test_scraping_run_skips_apis_when_show_streams_inherited():
    episode, season, show = _episode(number=1, season_number=1)
    stream = Mock()
    stream.infohash = "cc" * 20
    stream.raw_title = "Pack.S01"
    show.streams = [stream]
    show.is_scraped = Mock(return_value=True)
    season.is_scraped = Mock(return_value=False)
    episode.failed_attempts = 0
    episode.scraped_times = 0
    episode.set = Mock()

    parsed = SimpleNamespace(episodes=[], seasons=[1])

    scraping = Scraping.__new__(Scraping)
    scraping.max_failed_attempts = 0

    with (
        patch(
            "program.services.scrapers.episode_streams.parse_filename",
            return_value=parsed,
        ),
        patch.object(Scraping, "scrape") as scrape_mock,
        patch(
            "program.services.scrapers.report_pipeline_activity_for_item",
            create=True,
        ),
        patch(
            "program.managers.pipeline_activity.report_pipeline_activity_for_item",
        ),
    ):
        results = list(scraping.run(episode))

    scrape_mock.assert_not_called()
    assert len(results) == 1
    assert stream in episode.streams


def test_scraping_run_skips_when_already_on_disk():
    episode, _, _ = _episode()
    episode.filesystem_entry = Mock()
    episode.store_state = Mock()
    episode.set = Mock()
    episode.scraped_times = 0

    scraping = Scraping.__new__(Scraping)
    scraping.max_failed_attempts = 0

    with (
        patch.object(Scraping, "scrape") as scrape_mock,
        patch(
            "program.managers.pipeline_activity.report_pipeline_activity_for_item",
        ),
    ):
        list(scraping.run(episode))

    scrape_mock.assert_not_called()
    episode.store_state.assert_called_once()


def test_season_fan_out_omits_inherited_episode():
    episode, season, show = _episode(number=4, season_number=2)
    stream = Mock()
    stream.infohash = "dd" * 20
    stream.raw_title = "S02"
    season.streams = [stream]
    season.is_scraped = Mock(return_value=True)
    show.is_scraped = Mock(return_value=False)
    season.episodes = [episode]
    season.last_state = States.Indexed
    season.log_string = "Season 2"

    parsed = SimpleNamespace(episodes=[4], seasons=[2])

    program = Mock()
    program.services = Mock()
    program.services.scraping = Mock()
    program.services.scraping.should_submit = Mock(return_value=True)

    with (
        patch("program.state_transition.di") as di,
        patch(
            "program.services.scrapers.episode_streams.parse_filename",
            return_value=parsed,
        ),
    ):
        di.__getitem__.return_value = program
        processed = process_event(program.services.scraping, season, None, None)

    assert processed.related_media_items == []
