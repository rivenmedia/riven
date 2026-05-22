from datetime import datetime
from unittest.mock import MagicMock, Mock, patch

from program.managers.event_manager import EventManager
from program.media.item import Episode, Season
from program.media.state import States
from program.pipeline.restore_targets import scrape_queue_target
from program.state_transition import process_event


def _mock_scraping(*, should_submit: bool = True):
    scraping = Mock()
    scraping.initialized = True
    scraping.should_submit = Mock(return_value=should_submit)
    return scraping


def _episode_chain(*, season_scraped_at=None, show_scraped_at=None):
    show = Mock()
    show.last_state = States.Indexed
    show.scraped_at = show_scraped_at
    show.id = 100

    season = MagicMock(spec=Season)
    season.last_state = States.Indexed
    season.scraped_at = season_scraped_at
    season.id = 200
    season.parent = show

    episode = MagicMock(spec=Episode)
    episode.last_state = States.Indexed
    episode.scraped_at = None
    episode.id = 300
    episode.parent = season

    return episode, season, show


def test_scrape_queue_target_prefers_show_when_show_pack_not_attempted():
    episode, _, show = _episode_chain()
    target = scrape_queue_target(episode, _mock_scraping())
    assert target is show


def test_scrape_queue_target_prefers_season_when_show_pack_attempted():
    episode, season, _ = _episode_chain(show_scraped_at=datetime.now())
    target = scrape_queue_target(episode, _mock_scraping())
    assert target is season


def test_scrape_queue_target_episode_when_season_pack_attempted():
    episode, _, _ = _episode_chain(
        show_scraped_at=datetime.now(), season_scraped_at=datetime.now()
    )
    target = scrape_queue_target(episode, _mock_scraping())
    assert target is episode


def test_scrape_queue_target_honors_overrides():
    episode, _, _ = _episode_chain()
    target = scrape_queue_target(episode, _mock_scraping(), overrides={"manual": True})
    assert target is episode


def test_process_event_episode_redirects_to_season():
    episode, season, _ = _episode_chain(show_scraped_at=datetime.now())

    program = Mock()
    program.services = Mock()
    program.services.scraping = _mock_scraping()

    with patch("program.state_transition.di") as di:
        di.__getitem__.return_value = program
        processed = process_event("StateTransition", episode, None, None)

    assert processed.related_media_items == [season]
    assert processed.service is program.services.scraping


def test_restore_coalesces_indexed_episodes_to_season():
    em = EventManager()
    scraping = _mock_scraping()
    scraping.__class__.__name__ = "Scraping"

    program = Mock()
    program.services = Mock()
    program.services.updater = Mock()
    program.services.updater.initialized = False
    program.services.filesystem = Mock()
    program.services.filesystem.initialized = False
    program.services.downloader = Mock()
    program.services.downloader.initialized = False
    program.services.scraping = scraping
    program.services.indexer = Mock()
    program.services.indexer.initialized = False

    session = MagicMock()
    query_result = MagicMock()
    query_result.all.return_value = [
        (301, States.Indexed, "episode"),
        (302, States.Indexed, "episode"),
    ]
    session.execute.return_value = query_result

    season_item = Mock()
    season_item.last_state = States.Indexed

    with (
        patch(
            "program.managers.event_manager.db_session",
            return_value=MagicMock(
                __enter__=MagicMock(return_value=session), __exit__=MagicMock()
            ),
        ),
        patch.object(em, "_item_id_in_pipeline", return_value=False),
        patch(
            "program.pipeline.restore_targets.scrape_restore_target_id",
            return_value=200,
        ),
        patch(
            "program.managers.event_manager.db_functions.get_item_ids",
            return_value=(200, []),
        ),
        patch(
            "program.managers.event_manager.db_functions.get_item_by_id",
            return_value=season_item,
        ),
    ):
        restored = em.restore_pipeline_from_db(program, source="startup")

    assert restored == [200]
    assert em._queue.get(200) is not None
    assert em._queue.get(301) is None
    assert em._queue.get(302) is None


def test_restore_does_not_coalesce_scraped_episodes():
    em = EventManager()
    scraping = _mock_scraping()
    scraping.__class__.__name__ = "Scraping"

    program = Mock()
    program.services = Mock()
    program.services.updater = Mock()
    program.services.updater.initialized = False
    program.services.filesystem = Mock()
    program.services.filesystem.initialized = False
    program.services.downloader = Mock()
    program.services.downloader.initialized = False
    program.services.scraping = scraping
    program.services.indexer = Mock()
    program.services.indexer.initialized = False

    session = MagicMock()
    query_result = MagicMock()
    query_result.all.return_value = [(42, States.Scraped, "episode")]
    session.execute.return_value = query_result

    with (
        patch(
            "program.managers.event_manager.db_session",
            return_value=MagicMock(
                __enter__=MagicMock(return_value=session), __exit__=MagicMock()
            ),
        ),
        patch.object(em, "_item_id_in_pipeline", return_value=False),
        patch(
            "program.pipeline.restore_targets.scrape_restore_target_id",
        ) as coalesce,
        patch(
            "program.managers.event_manager.db_functions.get_item_ids",
            return_value=(42, []),
        ),
    ):
        restored = em.restore_pipeline_from_db(program, source="startup")

    coalesce.assert_not_called()
    assert restored == [42]
