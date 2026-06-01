"""scrape_queue_target pack-first routing."""

from datetime import datetime
from unittest.mock import Mock

from program.media.item import Episode, Season, Show
from program.media.state import States
from program.pipeline.restore_targets import pack_scrape_not_attempted, scrape_queue_target


def _scraping(*, submit: bool = True) -> Mock:
    scraping = Mock()
    scraping.should_submit = Mock(return_value=submit)
    return scraping


def test_pack_scrape_not_attempted_when_never_scraped():
    show = Show({"title": "S", "tvdb_id": "1"})
    show.scraped_at = None
    assert pack_scrape_not_attempted(show) is True


def test_scrape_queue_target_prefers_show_pack():
    show = Show({"title": "S", "tvdb_id": "1"})
    show.last_state = States.Indexed
    show.scraped_at = None
    season = Season({"number": 1, "aired_at": datetime(2020, 1, 1)})
    season.parent = show
    season.last_state = States.Indexed
    episode = Episode({"number": 1, "aired_at": datetime(2020, 1, 2)})
    episode.parent = season
    episode.last_state = States.Indexed
    show.seasons = [season]
    season.episodes = [episode]

    target = scrape_queue_target(episode, _scraping())
    assert target is show


def test_scrape_queue_target_episode_when_overrides():
    show = Show({"title": "S", "tvdb_id": "1"})
    season = Season({"number": 1})
    season.parent = show
    episode = Episode({"number": 1})
    episode.parent = season

    target = scrape_queue_target(episode, _scraping(), overrides={"force": True})
    assert target is episode
