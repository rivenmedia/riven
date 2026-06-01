#!/usr/bin/env python3
"""Duplicate handling and MediaItem identity helpers."""

from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.exc import IntegrityError

from program.db.db_functions import item_exists_by_any_id
from program.media.item import Movie, Show


class TestDuplicateHandling:
    """Duplicate handling functionality."""

    def test_item_exists_by_id_non_existent(self, test_scoped_db_session):
        assert not item_exists_by_any_id(
            item_id=999999, session=test_scoped_db_session
        )

    def test_item_exists_by_id_existent(self, test_scoped_db_session):
        from tests.conftest import seed_movie

        seed_movie(test_scoped_db_session, 1001)
        assert item_exists_by_any_id(item_id=1001, session=test_scoped_db_session)

    def test_item_exists_by_external_id_non_existent(self, test_scoped_db_session):
        assert not item_exists_by_any_id(
            imdb_id="tt9999999", session=test_scoped_db_session
        )

    def test_item_exists_by_external_id_existent(self, test_scoped_db_session):
        from tests.conftest import seed_movie

        seed_movie(test_scoped_db_session, 1002, imdb_id="tt1234567")
        assert item_exists_by_any_id(
            imdb_id="tt1234567", session=test_scoped_db_session
        )

    def test_item_exists_by_any_id_no_ids_provided(self):
        with pytest.raises(ValueError, match="At least one ID must be provided"):
            item_exists_by_any_id()

    def test_media_item_creation_movie(self):
        movie_data = {"imdb_id": "tt1234567", "title": "Test Movie", "year": 2023}
        movie = Movie(movie_data)
        assert movie.id is None
        assert movie.imdb_id == "tt1234567"
        assert movie.title == "Test Movie"
        assert movie.type == "movie"

    def test_media_item_creation_show(self):
        show_data = {
            "tvdb_id": "123456",
            "title": "Test Show",
            "year": 2023,
            "type": "show",
        }
        show = Show(show_data)
        assert show.id is None
        assert show.tvdb_id == "123456"
        assert show.title == "Test Show"
        assert show.type == "show"

    def test_media_item_creation_tmdb_movie(self):
        movie_data = {
            "tmdb_id": "51876",
            "title": "Test TMDB Movie",
            "year": 2023,
            "type": "movie",
        }
        movie = Movie(movie_data)
        assert movie.id is None
        assert movie.tmdb_id == "51876"
        assert movie.title == "Test TMDB Movie"
        assert movie.type == "movie"

    def test_duplicate_key_error_handling(self):
        mock_error = IntegrityError(
            "duplicate key value violates unique constraint", None, None
        )
        error_message = str(mock_error)
        assert "duplicate key value violates unique constraint" in error_message

        original_error = (
            '(psycopg2.errors.UniqueViolation) duplicate key value violates unique '
            'constraint "MediaItem_pkey"\nDETAIL:  Key (id)=(1) already exists.'
        )
        assert "duplicate key value violates unique constraint" in original_error

    def test_media_item_id_generation_edge_cases(self):
        movie = Movie({"imdb_id": None, "tmdb_id": None, "title": "Test Movie"})
        assert movie.id is None

    def test_media_item_log_string(self):
        movie = Movie({"imdb_id": "tt1234567", "title": "Test Movie", "year": 2023})
        assert "Test Movie" in movie.log_string

    def test_item_exists_mocked_session(self):
        with patch("program.db.db_functions._maybe_session") as mock_maybe_session:
            mock_session_instance = MagicMock()
            mock_session_instance.execute.return_value.scalar_one.return_value = 1
            mock_maybe_session.return_value.__enter__.return_value = (
                mock_session_instance,
                False,
            )
            assert item_exists_by_any_id(item_id=1)
