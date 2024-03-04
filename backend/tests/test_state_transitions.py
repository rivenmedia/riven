from copy import deepcopy
from datetime import datetime
from pathlib import Path
from unittest.mock import PropertyMock, patch

import pytest
from program.media import Show, Season, Episode, Movie
from program.state_transition import process_event
from program.libaries import SymlinkLibrary
from program.settings.manager import settings_manager
from program.media.state import States
from program.indexers import TraktIndexer
from program.scrapers import Scraping


@pytest.fixture
def test_show():
    return Show({'imdb_id': 'tt1405406'})

@pytest.fixture
def test_library_items():
    settings_manager.settings.symlink.library_path = Path(__file__).parent / "library"
    library = SymlinkLibrary()
    return [item for item in library.run()]

def test_symlink_library_output(test_library_items):
    assert all(i.state == States.Completed for i in test_library_items)
    assert len([i for i in test_library_items if isinstance(i, Movie)]) == 5
    assert len([i for i in test_library_items if isinstance(i, Show)]) == 1
    show = next(i for i in test_library_items if isinstance(i, Show))
    assert len(show.seasons) == 8

def test_library_to_index(test_show):
    media_item, service, output_items = process_event(None, SymlinkLibrary, test_show)
    assert service == TraktIndexer
    assert len(output_items) == 1
    assert output_items[0] == test_show

def test_index_to_scrape_fills_in_existing_when_empty(test_show):
    assert len(test_show.seasons) == 0
    # add some content so we can fill in the test show
    indexed_show = deepcopy(test_show)
    season = Season({"number": 1})
    season.add_episode(Episode({"number": 1}))
    season.add_episode(Episode({"number": 2}))
    indexed_show.add_season(season)
    # indexed_show will have Unknown state so we need to override it
    with patch.object(indexed_show, '_determine_state', return_value=States.Indexed):
        update_item, service, output_items = process_event(test_show, TraktIndexer, indexed_show)
        # check that the test show had its content filled in and returned to be updated in the container
        assert len(update_item.seasons) == 1
        assert len(update_item.seasons[0].episodes) == 2

def test_index_to_scrape_fills_in_existing_when_complete_but_missing_seasons(test_show, test_library_items):
    full_show = next(i for i in test_library_items if isinstance(i, Show))
    incomplete_show = deepcopy(full_show)
    incomplete_show.seasons.pop()
    assert len(incomplete_show.seasons) == 7
    # make sure that the missing season looks like its freshly indexed
    with patch.object(full_show.seasons[7], '_determine_state', return_value=States.Indexed):
        update_item, service, output_items = process_event(incomplete_show, TraktIndexer, full_show)
        # that way when its added it causes the updated show to no longer be Complete
        assert update_item.state == States.PartiallyCompleted
        assert len(update_item.seasons) == 8 

def test_index_to_scrape_does_nothing_when_already_scraped(test_show, test_library_items):
    full_show = next(i for i in test_library_items if isinstance(i, Show))
    with patch.object(test_show, '_determine_state', return_value=States.Completed):
        test_show.indexed_at = datetime.now()
        update_item, service, output_items = process_event(test_show, TraktIndexer, full_show)
        assert len(update_item.seasons) == 0