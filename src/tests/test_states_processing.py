"""MediaItem state derivation and pipeline state_transition routing."""

from unittest.mock import Mock, patch

import pytest

from program.media.item import Episode, MediaItem, Movie, Season, Show
from program.media.state import States
from program.program import Program
from program.services.downloaders.realdebrid import RealDebridDownloader
from program.services.filesystem import FilesystemService
from program.services.indexers import IndexerService
from program.services.scrapers import Scraping
from program.services.post_processing import PostProcessing
from program.services.updaters.plex import PlexUpdater
from program.state_transition import process_event


@pytest.fixture
def movie():
    return Movie(
        {
            "imdb_id": "tt1375666",
            "requested_by": "Iceberg",
            "title": "Inception",
            "aired_at": __import__("datetime").datetime(2010, 7, 16),
        }
    )


@pytest.fixture
def show():
    show = Show(
        {
            "imdb_id": "tt0903747",
            "requested_by": "Iceberg",
            "title": "Breaking Bad",
            "aired_at": __import__("datetime").datetime(2008, 1, 20),
        }
    )
    season = Season({"number": 1, "aired_at": __import__("datetime").datetime(2008, 1, 20)})
    episode = Episode({"number": 1, "aired_at": __import__("datetime").datetime(2008, 1, 20)})
    season.add_episode(episode)
    show.add_season(season)
    return show


@pytest.fixture
def media_item_movie():
    return MediaItem(
        {"imdb_id": "tt1375666", "requested_by": "Iceberg", "title": "Inception"}
    )


@pytest.fixture
def media_item_show():
    show = MediaItem(
        {
            "imdb_id": "tt0903747",
            "requested_by": "Iceberg",
            "title": "Breaking Bad",
        }
    )
    season = MediaItem({"number": 1})
    episode = MediaItem({"number": 1})
    season.add_episode(episode)
    show.add_season(season)
    return show


@pytest.fixture
def season(show):
    return show.seasons[0]


@pytest.fixture
def episode(season):
    return season.episodes[0]


def _mock_program() -> Mock:
    services = Mock()
    services.indexer = Mock(spec=IndexerService)
    services.scraping = Mock(spec=Scraping)
    services.scraping.should_submit = Mock(return_value=True)
    services.downloader = Mock(spec=RealDebridDownloader)
    services.filesystem = Mock(spec=FilesystemService)
    services.updater = Mock(spec=PlexUpdater)
    services.post_processing = Mock()
    program = Mock(spec=Program)
    program.services = services
    return program


def test_initial_state(movie, show, season, episode):
    assert movie.state == States.Indexed
    assert show.state == States.Unknown
    assert season.state == States.Unknown
    assert episode.state == States.Unknown


def test_requested_state():
    movie = Movie({"imdb_id": "tt1375666", "requested_by": "Iceberg"})
    assert movie.state == States.Requested


def test_indexed_state(movie):
    assert movie.state == States.Indexed


def test_scraped_state_requires_streams(episode):
    # Streams must be Stream ORM objects for is_scraped(); empty set is not scraped
    assert episode.state != States.Scraped


def test_downloaded_state(episode):
    from unittest.mock import PropertyMock, patch

    with patch.object(
        type(episode),
        "filesystem_entry",
        new_callable=PropertyMock,
        return_value=object(),
    ):
        assert episode.state == States.Downloaded


def test_completed_state(movie):
    movie.updated = True
    assert movie.state == States.Completed


def test_show_state_transitions(show):
    show.seasons[0].episodes[0].updated = True
    show.tvdb_status = "Ended"
    assert show.state == States.Completed


@pytest.mark.parametrize(
    "state, emitted_by, next_service",
    [
        (States.Unknown, "StateTransition", IndexerService),
        (States.Indexed, "IndexerService", Scraping),
        (States.Scraped, "Scraping", RealDebridDownloader),
        (States.Downloaded, "Downloader", FilesystemService),
        (States.Symlinked, "FilesystemService", PlexUpdater),
        (States.Completed, "PlexUpdater", PostProcessing),
    ],
)
def _assert_next_service(result, program, expected):
    if expected is None:
        assert result.service is None
    elif expected is IndexerService:
        assert result.service is program.services.indexer
    elif expected is Scraping:
        assert result.service is program.services.scraping
    elif expected is RealDebridDownloader:
        assert result.service is program.services.downloader
    elif expected is FilesystemService:
        assert result.service is program.services.filesystem
    elif expected is PlexUpdater:
        assert result.service is program.services.updater
    elif expected is PostProcessing:
        assert result.service is program.services.post_processing


@pytest.mark.parametrize(
    "state, emitted_by, next_service",
    [
        (States.Unknown, "StateTransition", IndexerService),
        (States.Indexed, "IndexerService", Scraping),
        (States.Scraped, "Scraping", RealDebridDownloader),
        (States.Downloaded, "Downloader", FilesystemService),
        (States.Symlinked, "FilesystemService", PlexUpdater),
        (States.Completed, "PlexUpdater", PostProcessing),
    ],
)
def test_process_event_transitions_movie(state, emitted_by, next_service, movie):
    movie.last_state = state
    program = _mock_program()

    with patch("program.state_transition.di") as mock_di:
        mock_di.__getitem__.return_value = program
        result = process_event(emitted_by, movie, None, None)

    _assert_next_service(result, program, next_service)


@pytest.mark.parametrize(
    "state, emitted_by, next_service",
    [
        (States.Unknown, "StateTransition", IndexerService),
        (States.Indexed, "IndexerService", Scraping),
        (States.Scraped, "Scraping", RealDebridDownloader),
        (States.Downloaded, "Downloader", FilesystemService),
        (States.Symlinked, "FilesystemService", PlexUpdater),
        (States.Completed, "PlexUpdater", PostProcessing),
    ],
)
def test_process_event_transition_shows(state, emitted_by, next_service, show):
    show.last_state = state
    program = _mock_program()

    with patch("program.state_transition.di") as mock_di:
        mock_di.__getitem__.return_value = program
        result = process_event(emitted_by, show, None, None)

    _assert_next_service(result, program, next_service)
