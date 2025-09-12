"""Tests for indexer cache functionality."""
import tempfile
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

from program.services.indexers.cache import IndexerCache


class TestIndexerCache:
    """Test cases for IndexerCache functionality."""
    
    @pytest.fixture
    def temp_cache_dir(self):
        """Create a temporary directory for cache files."""
        with tempfile.TemporaryDirectory() as temp_dir:
            yield temp_dir
    
    @pytest.fixture
    def cache(self, temp_cache_dir):
        """Create a cache instance with temporary directory."""
        return IndexerCache(temp_cache_dir)

    def test_cache_set_and_get(self, cache):
        """Test basic cache set and get functionality."""
        # Test movie data
        movie_data = {"title": "Test Movie", "year": 2020, "status": "Released"}
        cache.set("tmdb", "get_movie_details", {"movie_id": 123}, movie_data, "movie", 2020, "Released")
        
        # Should be able to retrieve the data
        retrieved = cache.get("tmdb", "get_movie_details", {"movie_id": 123})
        assert retrieved == movie_data
        
        # Test show data
        show_data = {"title": "Test Show", "year": 2020, "status": "Ended"}
        cache.set("tvdb", "get_series", {"series_id": 456}, show_data, "show", 2020, "Ended")
        
        retrieved = cache.get("tvdb", "get_series", {"series_id": 456})
        assert retrieved == show_data
    
    def test_cache_expiration(self, cache):
        """Test that cache entries expire correctly."""
        # Set a movie in production (should expire in 7 days)
        movie_data = {"title": "In Production Movie"}
        cache.set("tmdb", "get_movie_details", {"movie_id": 789}, movie_data, "movie", 2020, "In Production")
        
        # Should be retrievable initially
        retrieved = cache.get("tmdb", "get_movie_details", {"movie_id": 789})
        assert retrieved == movie_data
        
        # Mock the current time to be 8 days later
        with patch("program.services.indexers.cache.datetime") as mock_datetime:
            mock_datetime.now.return_value = datetime.now() + timedelta(days=8)
            mock_datetime.fromisoformat.side_effect = lambda x: datetime.fromisoformat(x)
            
            # Should not be retrievable after expiration
            retrieved = cache.get("tmdb", "get_movie_details", {"movie_id": 789})
            assert retrieved is None
    
    def test_cache_indefinite_storage(self, cache):
        """Test that indefinite cache entries don't expire."""
        # Set a released movie (should never expire)
        movie_data = {"title": "Released Movie"}
        cache.set("tmdb", "get_movie_details", {"movie_id": 999}, movie_data, "movie", 2020, "Released")
        
        # Mock the current time to be 1 year later
        with patch("program.services.indexers.cache.datetime") as mock_datetime:
            mock_datetime.now.return_value = datetime.now() + timedelta(days=365)
            mock_datetime.fromisoformat.side_effect = lambda x: datetime.fromisoformat(x)
            
            # Should still be retrievable after 1 year
            retrieved = cache.get("tmdb", "get_movie_details", {"movie_id": 999})
            assert retrieved == movie_data
    
    def test_cache_clear_expired(self, cache):
        """Test clearing expired cache entries."""
        # Set some data that will expire
        movie_data = {"title": "Expiring Movie"}
        cache.set("tmdb", "get_movie_details", {"movie_id": 111}, movie_data, "movie", 2020, "In Production")
        
        # Set some data that won't expire
        show_data = {"title": "Ended Show"}
        cache.set("tvdb", "get_series", {"series_id": 222}, show_data, "show", 2020, "Ended")
        
        # Mock time to expire the movie
        with patch("program.services.indexers.cache.datetime") as mock_datetime:
            mock_datetime.now.return_value = datetime.now() + timedelta(days=8)
            mock_datetime.fromisoformat.side_effect = lambda x: datetime.fromisoformat(x)
            
            # Clear expired entries
            cleared_count = cache.clear_expired()
            
            # Should have cleared 1 expired entry
            assert cleared_count == 1
            
            # Movie should be gone
            retrieved = cache.get("tmdb", "get_movie_details", {"movie_id": 111})
            assert retrieved is None
            
            # Show should still be there
            retrieved = cache.get("tvdb", "get_series", {"series_id": 222})
            assert retrieved == show_data
    
    def test_cache_stats(self, cache):
        """Test cache statistics functionality."""
        # Initially should have no entries
        stats = cache.get_stats()
        assert stats["active_entries"] == 0
        assert stats["total_entries"] == 0
        assert stats["cache_size_bytes"] == 0

        large_movie_data = {
            "title": "Test Movie",
            "overview": "A" * 1000,  # 1KB of data
            "genres": [{"name": "Action"}, {"name": "Drama"}],
            "cast": [{"name": f"Actor {i}"} for i in range(50)]
        }
        large_show_data = {
            "title": "Test Show", 
            "overview": "B" * 1000,  # 1KB of data
            "seasons": [{"season_number": i, "episode_count": 10} for i in range(5)]
        }

        cache.set("tmdb", "get_movie_details", {"movie_id": 1}, large_movie_data, "movie", 2020, "Released")
        cache.set("tvdb", "get_series", {"series_id": 1}, large_show_data, "show", 2020, "Ended")
        
        stats = cache.get_stats()
        assert stats["active_entries"] == 2
        assert stats["total_entries"] == 2
        assert stats["cache_size_bytes"] > 0
        assert stats["cache_size_mb"] >= 0
    
    def test_cache_clear_all(self, cache):
        """Test clearing all cache entries."""
        # Add some entries
        cache.set("tmdb", "get_movie_details", {"movie_id": 1}, {"title": "Movie 1"}, "movie", 2020, "Released")
        cache.set("tvdb", "get_series", {"series_id": 1}, {"title": "Show 1"}, "show", 2020, "Ended")
        
        # Verify they exist
        assert cache.get("tmdb", "get_movie_details", {"movie_id": 1}) is not None
        assert cache.get("tvdb", "get_series", {"series_id": 1}) is not None
        
        # Clear all
        cache.clear_all()
        
        # Verify they're gone
        assert cache.get("tmdb", "get_movie_details", {"movie_id": 1}) is None
        assert cache.get("tvdb", "get_series", {"series_id": 1}) is None
        
        # Stats should be empty
        stats = cache.get_stats()
        assert stats["active_entries"] == 0
        assert stats["total_entries"] == 0

    def test_movie_cache_ttl_calculations(self, cache):
        """Test TTL calculations for movies (TMDB)."""
        current_year = datetime.now().year
        
        # Released movies should cache indefinitely
        ttl = cache._calculate_ttl("movie", 2020, "Released")
        assert ttl is None
        
        # Canceled movies should cache indefinitely
        ttl = cache._calculate_ttl("movie", 2020, "Canceled")
        assert ttl is None
        
        # Movies in production should cache for 7 days
        ttl = cache._calculate_ttl("movie", 2020, "In Production")
        assert ttl == 7 * 24 * 60 * 60
        
        # Post production movies should cache for 7 days
        ttl = cache._calculate_ttl("movie", 2020, "Post Production")
        assert ttl == 7 * 24 * 60 * 60
        
        # Planned movies should cache for 7 days
        ttl = cache._calculate_ttl("movie", 2020, "Planned")
        assert ttl == 7 * 24 * 60 * 60
        
        # Rumored movies should cache for 7 days
        ttl = cache._calculate_ttl("movie", 2020, "Rumored")
        assert ttl == 7 * 24 * 60 * 60
        
        # Movies without status should cache indefinitely
        ttl = cache._calculate_ttl("movie", 2020, None)
        assert ttl is None
    
    def test_show_cache_ttl_calculations(self, cache):
        """Test TTL calculations for shows (TVDB)."""
        current_year = datetime.now().year
        
        # Ended shows should cache indefinitely
        ttl = cache._calculate_ttl("show", 2020, "Ended")
        assert ttl is None
        
        # Canceled shows should cache indefinitely
        ttl = cache._calculate_ttl("show", 2020, "Canceled")
        assert ttl is None
        
        # Shows older than 3 years should cache indefinitely
        old_year = current_year - 5
        ttl = cache._calculate_ttl("show", old_year, "Continuing")
        assert ttl is None
        
        # Recent ongoing shows should cache for 5 days
        recent_year = current_year - 1
        ttl = cache._calculate_ttl("show", recent_year, "Continuing")
        assert ttl == 5 * 24 * 60 * 60
        
        # Returning series should cache for 5 days
        ttl = cache._calculate_ttl("show", recent_year, "Returning Series")
        assert ttl == 5 * 24 * 60 * 60
        
        # Shows without status should cache for 5 days
        ttl = cache._calculate_ttl("show", recent_year, None)
        assert ttl == 5 * 24 * 60 * 60
    
    def test_season_episode_cache_ttl_calculations(self, cache):
        """Test TTL calculations for seasons and episodes (TVDB)."""
        current_year = datetime.now().year
        
        # Seasons/episodes from ended shows should cache indefinitely
        ttl = cache._calculate_ttl("season", 2020, "Ended")
        assert ttl is None
        
        ttl = cache._calculate_ttl("episode", 2020, "Ended")
        assert ttl is None
        
        # Seasons/episodes from canceled shows should cache indefinitely
        ttl = cache._calculate_ttl("season", 2020, "Canceled")
        assert ttl is None
        
        # Seasons/episodes from old shows should cache indefinitely
        old_year = current_year - 5
        ttl = cache._calculate_ttl("season", old_year, "Continuing")
        assert ttl is None
        
        # Recent seasons should cache for 3 days
        recent_year = current_year - 1
        ttl = cache._calculate_ttl("season", recent_year, "Continuing")
        assert ttl == 3 * 24 * 60 * 60
        
        # Recent episodes should cache for 3 days
        ttl = cache._calculate_ttl("episode", recent_year, "Continuing")
        assert ttl == 3 * 24 * 60 * 60
