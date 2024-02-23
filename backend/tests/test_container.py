import pytest
from program.media.container import MediaItemContainer
from program.media.item import Show, Season, Episode

# Fixture to setup a MediaItemContainer
@pytest.fixture
def container():
    return MediaItemContainer()

@pytest.fixture
def test_show():
    # Setup Show with a Season and an Episode
    show = Show({'imdb_id': 'tt1405406'})
    season = Season({'number': 1}, show.item_id)
    episode = Episode({'number': 1}, season.item_id)
    season.episodes.append(episode)
    show.seasons.append(season)
    return show

def test_upsert_episode_modification_reflects_in_parent_season(container, test_show):
    # Upsert the show with its season and episode
    container.upsert(test_show)

    modified_episode = test_show.seasons[0].episodes[0]

    # Modify an attribute of the copied episode
    modified_attribute_value = "Modified Value"
    modified_episode.some_attribute = modified_attribute_value

    # Upsert the modified episode
    container.upsert(modified_episode)

    # Fetch the season from the container to check if it contains the updated episode data
    container_season = container._items[modified_episode.item_id.parent_id]
    container_episode = container._items[modified_episode.item_id]

    # Verify that the modified episode's attribute is updated in the container
    assert container_episode.some_attribute == modified_attribute_value
    # Verify that the season in the container now points to the updated episode
    assert container_season.episodes[container_episode.number - 1].some_attribute == modified_attribute_value

def test_upsert_season_modification_reflects_in_parent_show(container, test_show):
    container.upsert(test_show)
    # Select a season to modify
    modified_season = test_show.seasons[0]

    # Modify an attribute of the season
    modified_attribute_value = "Modified Season Attribute"
    modified_season.some_attribute = modified_attribute_value

    # Upsert the modified season
    container.upsert(modified_season)

    # Fetch the show from the container to check if it contains the updated season data
    container_show = container._items[test_show.item_id]
    # Since the season was replaced with an ID reference, fetch the season directly from the container
    container_season = container._items[modified_season.item_id]

    # Verify that the modified season's attribute is updated in the container
    assert container_season.some_attribute == modified_attribute_value
    # Verify that the show in the container now references the updated season
    assert container_show.seasons[container_season.number - 1].some_attribute == modified_attribute_value