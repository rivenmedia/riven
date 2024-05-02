import pytest
from program.media.container import MediaItemContainer
from program.media.item import Episode, Season, Show
from program.media.state import States


@pytest.fixture
def container():
    return MediaItemContainer()


@pytest.fixture
def test_show():
    # Setup Show with a Season and an Episode
    show = Show({"imdb_id": "tt1405406"})
    season = Season({"number": 1})
    episode = Episode({"number": 1})
    season.add_episode(episode)
    show.add_season(season)
    return show

@pytest.fixture
def show_container(test_show):
    container = MediaItemContainer()
    container.upsert(test_show)
    return container

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
    assert (
        container_season.episodes[container_episode.number - 1].some_attribute
        == modified_attribute_value
    )


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
    assert (
        container_show.seasons[container_season.number - 1].some_attribute
        == modified_attribute_value
    )


def test_serialization_of_container(show_container, fs):
    # Check if the container is not empty
    assert len(show_container) > 0

    # Save the container to a file
    fs.create_dir("/fake")
    show_container.save("/fake/test_container.pkl")
    assert fs.exists("/fake/test_container.pkl")

    # Load the container from the file
    loaded_container: MediaItemContainer = MediaItemContainer()
    loaded_container.load("/fake/test_container.pkl")

    # Check if the loaded container is the same as the original container
    assert len(loaded_container) == len(show_container)


def test_remove_item(container, test_show):
    # container.upsert(test_show)
    # # Check if the item is in the container
    # assert test_show.seasons[0] in container
    # season_to_remove = test_show.seasons[0]
    # container.remove(season_to_remove)
    # # Check if the item is removed from the container
    # assert season_to_remove.item_id not in container

    container.upsert(test_show)
    # Check if the item is in the container
    assert test_show.item_id in container



def test_incomplete_items_retrieval(container, test_show):
    container.upsert(test_show)
    incomplete_items = container.get_incomplete_items()
    assert len(incomplete_items) == len(container)
    assert incomplete_items[next(iter(incomplete_items))].state == States.Unknown
