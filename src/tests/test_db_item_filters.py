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
        """Test filtering by media type"""
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
        """Test filtering by state"""
        filter = ItemFilter(states=[States.Completed])
        items = get_items_from_filter(filter=filter)
        assert all(item.last_state == States.Completed for item in items)

    def test_date_range_filter(self):
        """Test filtering by date ranges"""
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
        """Test filtering by multiple years"""
        filter = ItemFilter(year=[2022, 2023])
        items = get_items_from_filter(filter=filter)
        assert all(item.year in [2022, 2023] for item in items)

    def test_file_status_filter(self):
        """Test filtering by file status"""
        filter = ItemFilter(has_file=True)
        items = get_items_from_filter(filter=filter)
        assert all(item.file is not None for item in items)

    def test_season_episode_filter(self):
        """Test filtering by season and episode numbers"""
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
        """Test different load options"""
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
        """Test the __post_init__ conversions"""
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
