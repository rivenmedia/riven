import asyncio
from datetime import datetime
from unittest.mock import MagicMock, Mock, patch

import pytest

from program.maintenance.tv_scrape_health import analyze_tv_scrape_health
from program.media.item import Episode, Season, Show
from program.media.state import States
from program.services.scrapers.episode_streams import (
    actionable_episodes,
    individually_scraped_episode_counts,
    streamless_episode_counts,
)


def _episode(
    *,
    number: int = 1,
    last_state=States.Indexed,
    scraped: bool = False,
    scraped_at=None,
    on_disk: bool = False,
    released: bool = True,
) -> Episode:
    episode = MagicMock(spec=Episode)
    episode.number = number
    episode.last_state = last_state
    episode.is_released = released
    episode.scraped_at = scraped_at
    episode.filesystem_entry = Mock() if on_disk else None
    episode.available_in_vfs = False
    episode.is_scraped = Mock(return_value=scraped)
    return episode


def _season(
    *,
    number: int = 1,
    episodes: list[Episode] | None = None,
    scraped_at=None,
    last_state=States.Indexed,
    pack_scraped: bool = False,
) -> Season:
    season = MagicMock(spec=Season)
    season.id = 100 + number
    season.number = number
    season.episodes = episodes or []
    season.scraped_at = scraped_at
    season.last_state = last_state
    season.filesystem_entry = None
    season.is_scraped = Mock(return_value=pack_scraped)
    return season


def _show(
    *,
    title: str = "Test Show",
    seasons: list[Season] | None = None,
    pack_scraped: bool = False,
) -> Show:
    show = MagicMock(spec=Show)
    show.id = 1
    show.title = title
    show.seasons = seasons or []
    show.scraped_at = None
    show.last_state = States.Indexed
    show.filesystem_entry = None
    show.is_scraped = Mock(return_value=pack_scraped)
    for season in show.seasons:
        season.parent = show
    return show


def test_actionable_episodes_excludes_on_disk_and_completed():
    season = _season(
        episodes=[
            _episode(number=1, scraped=False),
            _episode(number=2, on_disk=True),
            _episode(number=3, last_state=States.Completed),
        ]
    )
    actionable = actionable_episodes(season)
    assert len(actionable) == 1
    assert actionable[0].number == 1


def test_streamless_episode_counts():
    season = _season(
        episodes=[
            _episode(number=1, scraped=False),
            _episode(number=2, scraped=True),
            _episode(number=3, scraped=False),
        ]
    )
    total, streamless, ratio = streamless_episode_counts(season)
    assert total == 3
    assert streamless == 2
    assert ratio == pytest.approx(2 / 3)


def test_empty_season_recommends_show_reset():
    show = _show(seasons=[_season(number=1, episodes=[])])
    session = MagicMock()
    session.execute.return_value.scalars.return_value.unique.return_value.all.return_value = [
        show
    ]

    candidates = analyze_tv_scrape_health(session)

    assert len(candidates) == 1
    assert candidates[0].reason == "streamless_show"
    assert candidates[0].item_type == "show"
    assert candidates[0].recommended_reset == "show"
    assert candidates[0].item_id == show.id
    assert "empty season" in candidates[0].details.lower()


def test_streamless_majority_season():
    scraped_at = datetime.now()
    season = _season(
        number=2,
        scraped_at=scraped_at,
        episodes=[
            _episode(number=i, scraped=False) for i in range(1, 5)
        ],
    )
    show = _show(seasons=[season])

    session = MagicMock()
    session.execute.return_value.scalars.return_value.unique.return_value.all.return_value = [
        show
    ]

    candidates = analyze_tv_scrape_health(session)

    assert len(candidates) == 1
    assert candidates[0].reason == "streamless_majority"
    assert candidates[0].item_type == "season"
    assert candidates[0].streamless_count == 4


def test_sparse_season():
    scraped_at = datetime.now()
    season = _season(
        number=1,
        scraped_at=scraped_at,
        episodes=[
            _episode(number=1, scraped=False),
            _episode(number=2, scraped=False),
        ],
    )
    show = _show(seasons=[season])

    session = MagicMock()
    session.execute.return_value.scalars.return_value.unique.return_value.all.return_value = [
        show
    ]

    candidates = analyze_tv_scrape_health(session)

    assert len(candidates) == 1
    assert candidates[0].reason == "sparse_season"


def test_streamless_show_collapses_multiple_seasons():
    scraped_at = datetime.now()
    season1 = _season(
        number=1,
        scraped_at=scraped_at,
        episodes=[_episode(number=i, scraped=False) for i in range(1, 4)],
    )
    season2 = _season(
        number=2,
        scraped_at=scraped_at,
        episodes=[_episode(number=i, scraped=False) for i in range(1, 4)],
    )
    show = _show(seasons=[season1, season2])

    session = MagicMock()
    session.execute.return_value.scalars.return_value.unique.return_value.all.return_value = [
        show
    ]

    candidates = analyze_tv_scrape_health(session)

    assert len(candidates) == 1
    assert candidates[0].reason == "streamless_show"
    assert candidates[0].item_type == "show"
    assert candidates[0].item_id == show.id


def test_skips_when_pack_not_attempted_and_no_individual_scrape():
    season = _season(
        episodes=[_episode(number=1, scraped=False) for _ in range(4)],
    )
    show = _show(seasons=[season])

    session = MagicMock()
    session.execute.return_value.scalars.return_value.unique.return_value.all.return_value = [
        show
    ]

    candidates = analyze_tv_scrape_health(session)
    assert candidates == []


def test_individually_scraped_episode_counts():
    season = _season(
        episodes=[
            _episode(number=1, scraped=True, last_state=States.Scraped),
            _episode(number=2, scraped=False),
            _episode(number=3, scraped=True, last_state=States.Scraped),
        ]
    )
    total, scraped, ratio = individually_scraped_episode_counts(season)
    assert total == 3
    assert scraped == 2
    assert ratio == pytest.approx(2 / 3)


def test_incomplete_pack_scrape_when_episodes_scraped_without_season_pack():
    season = _season(
        number=1,
        episodes=[
            _episode(number=i, scraped=True, last_state=States.Scraped)
            for i in range(1, 5)
        ],
    )
    show = _show(seasons=[season], pack_scraped=True)

    session = MagicMock()
    session.execute.return_value.scalars.return_value.unique.return_value.all.return_value = [
        show
    ]

    candidates = analyze_tv_scrape_health(session)

    assert len(candidates) == 1
    assert candidates[0].reason == "incomplete_pack_scrape"
    assert candidates[0].item_type == "season"
    assert candidates[0].recommended_reset == "season"
    assert candidates[0].streamless_count == 4


def test_incomplete_pack_show_when_show_pack_missing():
    season = _season(
        number=1,
        episodes=[
            _episode(number=i, scraped=True, last_state=States.Scraped)
            for i in range(1, 5)
        ],
    )
    show = _show(seasons=[season])

    session = MagicMock()
    session.execute.return_value.scalars.return_value.unique.return_value.all.return_value = [
        show
    ]

    candidates = analyze_tv_scrape_health(session)

    assert len(candidates) == 1
    assert candidates[0].reason == "incomplete_pack_show"
    assert candidates[0].recommended_reset == "show"


def test_skips_incomplete_pack_when_season_has_pack_streams():
    season = _season(
        number=1,
        pack_scraped=True,
        episodes=[
            _episode(number=i, scraped=True, last_state=States.Scraped)
            for i in range(1, 5)
        ],
    )
    show = _show(seasons=[season], pack_scraped=True)

    session = MagicMock()
    session.execute.return_value.scalars.return_value.unique.return_value.all.return_value = [
        show
    ]

    assert analyze_tv_scrape_health(session) == []


def test_apply_endpoint_resets_and_requeues():
    from routers.secure.maintenance import (
        TvScrapeApplyPayload,
        apply_tv_scrape_health_endpoint,
    )

    show = MagicMock(spec=Show)
    show.id = 42
    show.media_entry = None

    program = MagicMock()
    program.services = MagicMock()
    program.services.updater = None
    program.em.restore_pipeline_from_db.return_value = [42, 99]

    session = MagicMock()
    session.execute.return_value.scalar_one_or_none.return_value = show

    with (
        patch("routers.secure.maintenance.di") as di,
        patch("routers.secure.maintenance.db_session") as db_session_mock,
        patch("routers.secure.maintenance._reset_item") as reset_mock,
    ):
        di.__getitem__.return_value = program
        db_session_mock.return_value.__enter__.return_value = session
        db_session_mock.return_value.__exit__.return_value = None

        result = asyncio.run(
            apply_tv_scrape_health_endpoint(
                TvScrapeApplyPayload(item_ids=[42], requeue=True)
            )
        )

    reset_mock.assert_called_once()
    program.em.restore_pipeline_from_db.assert_called_once_with(
        program, source="maintenance"
    )
    assert result.reset_ids == [42]
    assert result.requeued_count == 2
