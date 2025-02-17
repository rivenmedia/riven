import pytest
from datetime import datetime, timedelta

from program.db.db_functions import ItemFilter, get_items_from_filter
from program.media.state import States

class TestItemFilter:
    def test_basic_id_filter(self):
        """Test filtering by a single ID"""
        filter = ItemFilter(id="episode_167008")
        items = get_items_from_filter(filter=filter)
        assert len(items) == 1
        assert items[0].id == "episode_167008"

    def test_multiple_ids_filter(self):
        """Test filtering by multiple IDs"""
        filter = ItemFilter(id=["episode_167008", "episode_167009"])
        items = get_items_from_filter(filter=filter)
        assert len(items) == 2
        assert items[0].id == "episode_167008"
        assert items[1].id == "episode_167009"

    def test_type_filter(self):
        """
        Test filtering by media type.
        
        This test verifies that the ItemFilter correctly filters items based on the media type. It creates an ItemFilter instance with the type set to "movie", retrieves the items using the get_items_from_filter function, and asserts that every returned item's type attribute is "movie".
        
        Raises:
            AssertionError: If any item in the result does not have its type equal to "movie".
        """
        filter = ItemFilter(type="movie")
        items = get_items_from_filter(filter=filter)
        assert all(item.type == "movie" for item in items)

    def test_multiple_types_filter(self):
        """Test filtering by multiple media types"""
        filter = ItemFilter(type=["movie", "show"])
        items = get_items_from_filter(filter=filter)
        assert all(item.type in ["movie", "show"] for item in items)

    def test_title_filter(self):
        """Test filtering by title"""
        filter = ItemFilter(title="Test Movie")
        items = get_items_from_filter(filter=filter)
        assert all("Test Movie" in item.title for item in items)

    def test_state_filter(self):
        """
        Test filtering by state.
        
        This test verifies that the ItemFilter properly returns items whose last_state is set to States.Completed.
        It creates a filter with States.Completed, retrieves items using get_items_from_filter, and asserts that every
        item's last_state matches the expected state.
        
        Raises:
            AssertionError: If any item does not have States.Completed as its last_state.
        """
        filter = ItemFilter(states=[States.Completed])
        items = get_items_from_filter(filter=filter)
        assert all(item.last_state == States.Completed for item in items)

    def test_date_range_filter(self):
        """
        Test filtering of items by a specified date range.
        
        This unit test verifies that the filtering functionality of the ItemFilter class works correctly for date ranges. It computes a time window from one week ago until the current moment and initializes an ItemFilter with these boundaries (requested_after and requested_before). The test then retrieves items using get_items_from_filter and asserts that each item's requested_at timestamp lies within the specified range.
        """
        now = datetime.now()
        week_ago = now - timedelta(days=7)
        
        filter = ItemFilter(
            requested_after=week_ago,
            requested_before=now
        )
        items = get_items_from_filter(filter=filter)
        assert all(week_ago <= item.requested_at <= now for item in items)

    def test_year_filter(self):
        """Test filtering by year"""
        filter = ItemFilter(year=2023)
        items = get_items_from_filter(filter=filter)
        assert all(item.year == 2023 for item in items)

    def test_multiple_years_filter(self):
        """
        Test filtering items by multiple years.
        
        This test creates an ItemFilter with the years [2022, 2023] and retrieves items using the
        get_items_from_filter function. It verifies that every returned item has its 'year' attribute
        set to either 2022 or 2023.
        
        Raises:
            AssertionError: If any item’s year is not in [2022, 2023].
        """
        filter = ItemFilter(year=[2022, 2023])
        items = get_items_from_filter(filter=filter)
        assert all(item.year in [2022, 2023] for item in items)

    def test_file_status_filter(self):
        """
        Test that filtering by file status returns only items with a non-null file attribute.
        
        This test sets up an ItemFilter with has_file=True to ensure that only items with an associated file are retrieved.
        It then calls get_items_from_filter and verifies that every item in the returned list has a non-None value for the 'file' attribute.
        """
        filter = ItemFilter(has_file=True)
        items = get_items_from_filter(filter=filter)
        assert all(item.file is not None for item in items)

    def test_season_episode_filter(self):
        """
        Test filtering by season and episode numbers.
        
        This test creates an ItemFilter with type set to ["episode"], a season_number of 1, and an episode_number of 1. It then retrieves items using the get_items_from_filter function and verifies that at least one item is returned. Additionally, it asserts that every returned item satisfies the following conditions:
            - The item's type is "episode".
            - The parent object's number (representing the season) is 1.
            - The item's own number (representing the episode) is 1.
        """
        filter = ItemFilter(
            type=["episode"],
            season_number=1,
            episode_number=1
        )
        items = get_items_from_filter(filter=filter)
        assert len(items) >= 1
        assert all(
            item.type == "episode" and 
            item.parent.number == 1 and 
            item.number == 1 
            for item in items
        )

    @pytest.mark.parametrize("load_option", [
        ("load_streams", True),
        ("load_blacklisted_streams", True),
        ("load_subtitles", True),
        ("load_children", False)
    ])
    def test_load_options(self, load_option):
        """
        Test various load options on ItemFilter to ensure that retrieving items returns a list without errors.
        
        Parameters:
            load_option (tuple): A tuple with two elements:
                - option_name (str): The name of the filter option.
                - option_value (Any): The value corresponding to the filter option.
        
        This test unpacks the provided load_option to construct keyword arguments for an ItemFilter instance.
        It then retrieves items using get_items_from_filter and asserts that the returned value is a list.
        An AssertionError is raised if the items are not returned as a list.
        """
        option_name, option_value = load_option
        filter_kwargs = {option_name: option_value}
        filter = ItemFilter(**filter_kwargs)
        items = get_items_from_filter(filter=filter)
        # Just verify we get results without errors
        assert isinstance(items, list)

    def test_combined_filters(self):
        """Test combining multiple filter criteria"""
        filter = ItemFilter(
            type="movie",
            year=2023,
            has_file=True,
            is_scraped=True
        )
        items = get_items_from_filter(filter=filter)
        assert all(
            item.type == "movie" and
            item.year == 2023 and
            item.file is not None and
            item.is_scraped
            for item in items
        )

    def test_empty_results(self):
        """Test filter that should return no results"""
        filter = ItemFilter(id="non_existent_id")
        items = get_items_from_filter(filter=filter)
        assert len(items) == 0

    def test_filter_post_init_conversion(self):
        """
        Verify that the __post_init__ method correctly converts single-value fields to lists.
        
        This test ensures that when the ItemFilter is initialized with non-list values for the 'type', 'id', and 'year' fields,
        the __post_init__ method converts these values into singleton lists. The test asserts both the type and the exact content
        of each field after conversion.
        """
        filter = ItemFilter(
            type="movie",  # Should be converted to list
            id="test_id",  # Should be converted to list
            year=2023     # Should be converted to list
        )
        assert isinstance(filter.type, list)
        assert isinstance(filter.id, list)
        assert isinstance(filter.year, list)
        assert filter.type == ["movie"]
        assert filter.id == ["test_id"]
        assert filter.year == [2023]
