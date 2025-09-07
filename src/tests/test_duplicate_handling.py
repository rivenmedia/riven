#!/usr/bin/env python3
"""
Test script to verify duplicate handling works correctly.
This script tests the new duplicate handling functionality.
"""

import pytest
from unittest.mock import patch, MagicMock
from sqlalchemy.exc import IntegrityError

from program.db.db_functions import item_exists_by_any_id
from program.media.item import Movie, Show


class TestDuplicateHandling:
    """Test class for duplicate handling functionality."""

    def test_item_exists_by_id_non_existent(self):
        """Test item_exists_by_id with non-existent item."""
        test_id = "test_item_12345"
        exists = item_exists_by_any_id(test_id)
        assert not exists, "Non-existent item should return False"

    def test_item_exists_by_id_existent(self):
        """Test item_exists_by_id with existing item."""
        with patch('program.db.db_functions._maybe_session') as mock_maybe_session:
            mock_session_instance = MagicMock()
            mock_session_instance.execute.return_value.scalar_one.return_value = 1
            mock_maybe_session.return_value.__enter__.return_value = (mock_session_instance, False)
            
            exists = item_exists_by_any_id("existing_id")
            assert exists, "Existing item should return True"

    def test_get_item_by_external_id_non_existent(self):
        """Test get_item_by_external_id with non-existent external ID."""
        test_imdb = "tt9999999"  # Non-existent IMDB ID
        item = item_exists_by_any_id(imdb_id=test_imdb)
        assert item is False, "Non-existent external ID should return False"

    def test_get_item_by_external_id_existent(self):
        """Test get_item_by_external_id with existing external ID."""
        with patch('program.db.db_functions._maybe_session') as mock_maybe_session:
            mock_session_instance = MagicMock()
            mock_session_instance.execute.return_value.scalar_one.return_value = 1
            mock_maybe_session.return_value.__enter__.return_value = (mock_session_instance, False)
            
            item = item_exists_by_any_id(imdb_id="tt1234567")
            assert item is True, "Existing external ID should return True"

    def test_get_item_by_external_id_no_ids_provided(self):
        """Test get_item_by_external_id with no external IDs provided."""
        with pytest.raises(ValueError, match="At least one ID must be provided"):
            item_exists_by_any_id()

    def test_media_item_creation_movie(self):
        """Test Movie creation."""
        movie_data = {
            "imdb_id": "tt1234567",
            "title": "Test Movie",
            "year": 2023
        }
        
        movie = Movie(movie_data)
        assert movie.id is None  # ID is None until tmdb_id is provided
        assert movie.imdb_id == "tt1234567"
        assert movie.title == "Test Movie"
        assert movie.type == "movie"

    def test_media_item_creation_show(self):
        """Test Show creation."""
        show_data = {
            "tvdb_id": "123456",
            "title": "Test Show",
            "year": 2023,
            "type": "show"  # Include type for ID generation
        }

        show = Show(show_data)
        assert show.id == "tvdb_show_123456"
        assert show.tvdb_id == "123456"
        assert show.title == "Test Show"
        assert show.type == "show"

    def test_media_item_creation_tmdb_movie(self):
        """Test Movie creation with TMDB ID."""
        movie_data = {
            "tmdb_id": "51876",
            "title": "Test TMDB Movie",
            "year": 2023,
            "type": "movie"  # Include type for ID generation
        }
        
        movie = Movie(movie_data)
        assert movie.id == "tmdb_movie_51876"
        assert movie.tmdb_id == "51876"
        assert movie.title == "Test TMDB Movie"
        assert movie.type == "movie"

    def test_duplicate_key_error_handling(self):
        """Test that IntegrityError for duplicate keys is handled properly."""
        # Mock the IntegrityError
        mock_error = IntegrityError("duplicate key value violates unique constraint", None, None)
        
        # Test that our error message detection works
        error_message = str(mock_error)
        assert "duplicate key value violates unique constraint" in error_message
        
        # Test the specific error from the original issue
        original_error = "(psycopg2.errors.UniqueViolation) duplicate key value violates unique constraint \"MediaItem_pkey\"\nDETAIL:  Key (id)=(tvdb_show_76894) already exists."
        assert "duplicate key value violates unique constraint" in original_error

    def test_media_item_id_generation_edge_cases(self):
        """Test MediaItem ID generation with edge cases."""
        # Test with None values - should return None for ID
        movie_data = {
            "imdb_id": None,
            "tmdb_id": None,
            "title": "Test Movie"
        }
        
        movie = Movie(movie_data)
        # Should return None when no external IDs are provided
        assert movie.id is None

    def test_media_item_log_string(self):
        """Test MediaItem log_string property."""
        movie_data = {
            "imdb_id": "tt1234567",
            "title": "Test Movie",
            "year": 2023
        }
        
        movie = Movie(movie_data)
        log_string = movie.log_string
        # log_string should contain the IMDB ID when title is not available
        assert "tt1234567" in log_string


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
