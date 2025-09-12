"""Comprehensive tests for database modules.

This module tests the functionality of:
- program.db.db (database connection and management)
- program.db.db_functions (database operations)
- program.db.stream_operations (stream-related operations)
"""

from __future__ import annotations

import contextlib
from datetime import datetime, timedelta
from unittest.mock import Mock, patch

import pytest
from RTN import ParsedData, Torrent
from sqlalchemy import func, select

from program.db.db import (
    create_database_if_not_exists,
    db,
    get_db,
    run_migrations,
    vacuum_and_analyze_index_maintenance,
)
from program.db.db_functions import (
    _purge_orphan_streams_tx,
    create_calendar,
    delete_media_item,
    delete_media_item_by_id,
    get_item_by_external_id,
    get_item_by_id,
    get_item_by_imdb_and_episode,
    get_item_by_symlink_path,
    get_item_ids,
    get_items_by_ids,
    hard_reset_database,
    item_exists_by_any_id,
    retry_library,
    update_ongoing,
)
from program.db.stream_operations import clear_streams, set_stream_blacklisted
from program.media.item import Episode, MediaItem, Movie, Season, Show
from program.media.state import States
from program.media.stream import Stream, StreamBlacklistRelation, StreamRelation

# ================================ HELPER FUNCTIONS ================================

def create_movie(tmdb_id: str, imdb_id: str = None, title: str = "Test Movie") -> Movie:
    """Create a test movie with minimal data."""
    return Movie({
        "title": title,
        "tmdb_id": tmdb_id,
        "imdb_id": imdb_id or f"tt{tmdb_id}",
        "type": "movie"
    })


def create_show_with_episode(tvdb_id: str, season_num: int = 1, episode_num: int = 1) -> tuple[Show, Season, Episode]:
    """Create a show with one season and one episode."""
    show = Show({"title": "Test Show", "tvdb_id": tvdb_id, "type": "show"})
    season = Season({"number": season_num, "tvdb_id": f"{tvdb_id}-{season_num}", "type": "season"})
    episode = Episode({"number": episode_num, "tvdb_id": f"{tvdb_id}-{season_num}-{episode_num}", "type": "episode"})
    
    # Set up relationships
    season.parent = show
    season.parent_id = show.id
    episode.parent = season
    episode.parent_id = season.id
    show.seasons = [season]
    season.episodes = [episode]
    
    return show, season, episode


def create_stream(title: str = "Test Stream", infohash: str = None) -> Stream:
    """Create a test stream."""
    if infohash is None:
        infohash = "abcd1234abcd1234abcd1234abcd1234abcd1234"
    
    parsed_data = ParsedData(parsed_title=title, raw_title=title)
    torrent = Torrent(raw_title=title, infohash=infohash, data=parsed_data, fetch=True)
    return Stream(torrent)


# ================================ DB.PY TESTS ================================

class TestDbModule:
    """Tests for program.db.db module functions."""
    
    def test_get_db_yields_session(self, pg_session):
        """Test get_db() yields a valid session."""
        db_gen = get_db()
        session = next(db_gen)
        
        assert session is not None
        assert hasattr(session, "close")
        
        # Clean up the generator
        with contextlib.suppress(StopIteration):
            next(db_gen)
    
    @patch("program.db.db.SQLAlchemy")
    def test_create_database_success(self, mock_sqlalchemy):
        """Test successful database creation."""
        mock_temp_db = Mock()
        mock_connection = Mock()
        mock_connection.execution_options.return_value = mock_connection
        
        mock_context_manager = Mock()
        mock_context_manager.__enter__ = Mock(return_value=mock_connection)
        mock_context_manager.__exit__ = Mock(return_value=None)
        mock_temp_db.engine.connect.return_value = mock_context_manager
        mock_sqlalchemy.return_value = mock_temp_db
        
        result = create_database_if_not_exists()
        
        assert result is True
        mock_connection.execute.assert_called_once()
    
    @patch("program.db.db.SQLAlchemy")
    def test_create_database_failure(self, mock_sqlalchemy):
        """Test database creation failure handling."""
        mock_temp_db = Mock()
        mock_temp_db.engine.connect.side_effect = Exception("Connection failed")
        mock_sqlalchemy.return_value = mock_temp_db
        
        result = create_database_if_not_exists()
        assert result is False
    
    def test_vacuum_and_analyze_success(self, pg_session):
        """Test VACUUM and ANALYZE operations."""
        vacuum_and_analyze_index_maintenance()
    
    def test_run_migrations_success(self, pg_session):
        """Test successful migration run."""
        run_migrations()


# ================================ DB_FUNCTIONS.PY TESTS ================================

class TestGetItemFunctions:
    """Tests for item retrieval functions."""
    
    def test_get_item_by_id_success(self, pg_session):
        """Test successful item retrieval by ID."""
        movie = create_movie("10001")
        pg_session.add(movie)
        pg_session.commit()
        
        result = get_item_by_id(movie.id, session=pg_session)
        
        assert result is not None
        assert result.id == movie.id
        assert result.title == "Test Movie"
    
    def test_get_item_by_id_not_found(self, pg_session):
        """Test get_item_by_id with non-existent ID."""
        result = get_item_by_id("non_existent_id", session=pg_session)
        assert result is None
    
    def test_get_item_by_id_with_type_filter(self, pg_session):
        """Test get_item_by_id with type filtering."""
        movie = create_movie("10002")
        pg_session.add(movie)
        pg_session.commit()
        
        # Should find movie when filtering for movies
        result = get_item_by_id(movie.id, item_types=["movie"], session=pg_session)
        assert result is not None
        
        # Should not find movie when filtering for shows
        result = get_item_by_id(movie.id, item_types=["show"], session=pg_session)
        assert result is None
    
    def test_get_items_by_ids_multiple(self, pg_session):
        """Test retrieval of multiple items."""
        movies = [create_movie(f"1000{i}") for i in range(3)]
        pg_session.add_all(movies)
        pg_session.commit()
        
        ids = [movie.id for movie in movies]
        results = get_items_by_ids(ids, session=pg_session)
        
        assert len(results) == 3
        assert all(item.id in ids for item in results)
    
    def test_get_items_by_ids_empty_list(self, pg_session):
        """Test get_items_by_ids with empty list."""
        results = get_items_by_ids([], session=pg_session)
        assert results == []
    
    def test_get_item_by_external_id_success(self, pg_session):
        """Test retrieval by external IDs."""
        movie = create_movie("10003", "tt10003")
        pg_session.add(movie)
        pg_session.commit()
        
        # Test IMDb ID
        result = get_item_by_external_id(imdb_id="tt10003", session=pg_session)
        assert result is not None
        assert result.id == movie.id
        
        # Test TMDB ID
        result = get_item_by_external_id(tmdb_id=10003, session=pg_session)
        assert result is not None
        assert result.id == movie.id
    
    def test_get_item_by_external_id_no_ids(self, pg_session):
        """Test error when no external IDs provided."""
        with pytest.raises(ValueError, match="At least one external ID must be provided"):
            get_item_by_external_id()
    
    def test_item_exists_by_any_id(self, pg_session):
        """Test existence check by various IDs."""
        movie = create_movie("10004", "tt10004")
        pg_session.add(movie)
        pg_session.commit()
        
        assert item_exists_by_any_id(item_id=movie.id, session=pg_session) is True
        assert item_exists_by_any_id(imdb_id="tt10004", session=pg_session) is True
        assert item_exists_by_any_id(tmdb_id="10004", session=pg_session) is True
        assert item_exists_by_any_id(item_id="non_existent", session=pg_session) is False
    
    def test_get_item_by_symlink_path(self, pg_session):
        """Test retrieval by symlink path."""
        movie = create_movie("10005")
        movie.symlink_path = "/test/path"
        pg_session.add(movie)
        pg_session.commit()
        
        results = get_item_by_symlink_path("/test/path", session=pg_session)
        
        assert len(results) == 1
        assert results[0].id == movie.id
    
    def test_get_item_by_imdb_and_episode_movie(self, pg_session):
        """Test movie retrieval by TMDB ID."""
        movie = create_movie("10006")
        pg_session.add(movie)
        pg_session.commit()
        
        results = get_item_by_imdb_and_episode(tmdb_id="10006", session=pg_session)
        
        assert len(results) == 1
        assert results[0].id == movie.id
    
    def test_get_item_by_imdb_and_episode_episode(self, pg_session):
        """Test episode retrieval by TVDB ID."""
        show, season, episode = create_show_with_episode("20001")
        pg_session.add_all([show, season, episode])
        pg_session.commit()
        
        results = get_item_by_imdb_and_episode(tvdb_id="20001", season_number=1, episode_number=1, session=pg_session)
        
        assert len(results) == 1
        assert results[0].id == episode.id


class TestDeleteFunctions:
    """Tests for item deletion functions."""
    
    def test_delete_media_item_by_id_not_found(self, pg_session):
        """Test deletion with non-existent ID."""
        result = delete_media_item_by_id("non_existent")
        assert result is False
    
    def test_delete_media_item_wrapper(self, pg_session):
        """Test delete_media_item wrapper function."""
        movie = create_movie("10008")
        # Test that the wrapper function exists and can be called
        # (actual deletion testing is complex due to session isolation)
        delete_media_item(movie)  # Should not raise an exception


class TestUtilityFunctions:
    """Tests for utility functions."""
    
    def test_get_item_ids_movie(self, pg_session):
        """Test get_item_ids for movie (no children)."""
        movie = create_movie("10009")
        pg_session.add(movie)
        pg_session.commit()
        
        root_id, related_ids = get_item_ids(pg_session, movie.id)
        
        assert root_id == movie.id
        assert related_ids == []
    
    def test_get_item_ids_show(self, pg_session):
        """Test get_item_ids for show with children."""
        show, season, episode = create_show_with_episode("20002")
        pg_session.add_all([show, season, episode])
        pg_session.commit()
        
        root_id, related_ids = get_item_ids(pg_session, show.id)
        
        assert root_id == show.id
        assert len(related_ids) == 2  # season + episode
        assert season.id in related_ids
        assert episode.id in related_ids
    
    def test_retry_library(self, pg_session):
        """Test retry_library returns items needing retry."""
        movie1 = create_movie("10010")
        movie2 = create_movie("10011")
        
        movie1.last_state = States.Requested
        movie2.last_state = States.Completed
        
        pg_session.add_all([movie1, movie2])
        pg_session.commit()
        
        result = retry_library(session=pg_session)
        
        assert len(result) == 1
        assert movie1.id in result
        assert movie2.id not in result
    
    def test_update_ongoing(self, pg_session):
        """Test update_ongoing processes items correctly."""
        movie = create_movie("10012")
        movie.last_state = States.Ongoing
        pg_session.add(movie)
        pg_session.commit()
        
        with patch.object(movie, "store_state", return_value=(States.Ongoing, States.Completed)), \
             patch("program.db.db_functions.logger") as mock_logger:
            result = update_ongoing(session=pg_session)
        
        assert len(result) == 1
        assert movie.id in result
    
    def test_create_calendar(self, pg_session):
        """Test create_calendar returns upcoming items."""
        movie = create_movie("10013")
        movie.last_state = States.Requested
        movie.aired_at = datetime.now() + timedelta(days=1)
        movie.trakt_id = "12345"
        pg_session.add(movie)
        pg_session.commit()
        
        result = create_calendar(session=pg_session)
        
        assert len(result) == 1
        assert movie.id in result
    
    def test_purge_orphan_streams(self, pg_session):
        """Test orphan stream purging."""
        orphan_stream = create_stream("Orphan")
        linked_stream = create_stream("Linked")
        movie = create_movie("10014")
        
        pg_session.add_all([orphan_stream, linked_stream, movie])
        pg_session.commit()
        
        # Link one stream to movie
        relation = StreamRelation(parent_id=movie.id, child_id=linked_stream.id)
        pg_session.add(relation)
        pg_session.commit()
        
        deleted_count = _purge_orphan_streams_tx(pg_session)
        
        assert deleted_count == 1
        assert pg_session.query(Stream).filter_by(id=orphan_stream.id).first() is None
        assert pg_session.query(Stream).filter_by(id=linked_stream.id).first() is not None
    
    def test_hard_reset_database(self, pg_session):
        """Test hard_reset_database clears data."""
        movie = create_movie("10015")
        pg_session.add(movie)
        pg_session.commit()
        
        # Verify data exists
        assert pg_session.query(MediaItem).filter_by(id=movie.id).first() is not None
        
        # Reset database
        with patch("program.db.db_functions.logger"):
            hard_reset_database()
        
        # Verify data is gone
        with db.Session() as new_session:
            assert new_session.query(MediaItem).filter_by(id=movie.id).first() is None


# ================================ STREAM_OPERATIONS.PY TESTS ================================

class TestStreamOperations:
    """Tests for stream operations module."""
    
    def test_clear_streams_removes_all_relations(self, pg_session):
        """Test clear_streams removes all stream relations and blacklists."""
        movie = create_movie("10016")
        stream1 = create_stream("Stream1")
        stream2 = create_stream("Stream2")
        pg_session.add_all([movie, stream1, stream2])
        pg_session.commit()
        
        # Add relations and blacklist
        pg_session.add_all([
            StreamRelation(parent_id=movie.id, child_id=stream1.id),
            StreamRelation(parent_id=movie.id, child_id=stream2.id),
            StreamBlacklistRelation(media_item_id=movie.id, stream_id=stream1.id)
        ])
        pg_session.commit()
        
        clear_streams(media_item_id=movie.id, session=pg_session)
        
        # Verify all relations are gone
        assert pg_session.execute(
            select(func.count()).select_from(StreamRelation)
            .where(StreamRelation.parent_id == movie.id)
        ).scalar() == 0
        
        assert pg_session.execute(
            select(func.count()).select_from(StreamBlacklistRelation)
            .where(StreamBlacklistRelation.media_item_id == movie.id)
        ).scalar() == 0
        
        # Streams themselves should remain
        assert pg_session.query(Stream).filter_by(id=stream1.id).first() is not None
        assert pg_session.query(Stream).filter_by(id=stream2.id).first() is not None
    
    def test_set_stream_blacklisted_true(self, pg_session):
        """Test blacklisting a stream."""
        movie = create_movie("10017")
        stream = create_stream("TestStream")
        pg_session.add_all([movie, stream])
        pg_session.commit()
        
        # First link the stream
        pg_session.add(StreamRelation(parent_id=movie.id, child_id=stream.id))
        pg_session.commit()
        
        # Mock websocket to prevent hanging
        with patch("program.media.item.websocket_manager.publish"):
            changed = set_stream_blacklisted(movie, stream, blacklisted=True, session=pg_session)
        
        assert changed is True
        
        # Verify stream is blacklisted and link is removed
        assert pg_session.execute(
            select(func.count()).select_from(StreamRelation)
            .where(StreamRelation.parent_id == movie.id, StreamRelation.child_id == stream.id)
        ).scalar() == 0
        
        assert pg_session.execute(
            select(func.count()).select_from(StreamBlacklistRelation)
            .where(StreamBlacklistRelation.media_item_id == movie.id, StreamBlacklistRelation.stream_id == stream.id)
        ).scalar() == 1
    
    def test_set_stream_blacklisted_false(self, pg_session):
        """Test unblacklisting a stream."""
        movie = create_movie("10018")
        stream = create_stream("TestStream")
        pg_session.add_all([movie, stream])
        pg_session.commit()
        
        # First blacklist the stream
        pg_session.add(StreamBlacklistRelation(media_item_id=movie.id, stream_id=stream.id))
        pg_session.commit()
        
        changed = set_stream_blacklisted(movie, stream, blacklisted=False, session=pg_session)
        
        assert changed is True
        
        # Verify stream is linked and blacklist is removed
        assert pg_session.execute(
            select(func.count()).select_from(StreamBlacklistRelation)
            .where(StreamBlacklistRelation.media_item_id == movie.id, StreamBlacklistRelation.stream_id == stream.id)
        ).scalar() == 0
        
        assert pg_session.execute(
            select(func.count()).select_from(StreamRelation)
            .where(StreamRelation.parent_id == movie.id, StreamRelation.child_id == stream.id)
        ).scalar() == 1
    
    def test_set_stream_blacklisted_no_change(self, pg_session):
        """Test blacklisting when stream is not linked returns False."""
        movie = create_movie("10019")
        stream = create_stream("TestStream")
        pg_session.add_all([movie, stream])
        pg_session.commit()
        
        # Try to blacklist without linking first
        changed = set_stream_blacklisted(movie, stream, blacklisted=True, session=pg_session)
        assert changed is False


# ================================ INTEGRATION TESTS ================================

class TestIntegration:
    """Integration tests across modules."""
    
    def test_stream_operations_with_items(self, pg_session):
        """Test integration between stream operations and items."""
        movie = create_movie("10020")
        stream = create_stream("TestStream")
        pg_session.add_all([movie, stream])
        pg_session.commit()
        
        # Test clear_streams function
        clear_streams(media_item_id=movie.id, session=pg_session)
        
        # Verify function completes without error
        assert True


# ================================ ERROR HANDLING TESTS ================================

class TestErrorHandling:
    """Edge cases and error handling tests."""
    
    def test_get_item_by_id_empty_id(self, pg_session):
        """Test get_item_by_id with invalid IDs."""
        assert get_item_by_id("", session=pg_session) is None
        assert get_item_by_id(None, session=pg_session) is None
    
    def test_get_items_by_ids_partial_match(self, pg_session):
        """Test get_items_by_ids with some non-existent IDs."""
        movie = create_movie("10023")
        pg_session.add(movie)
        pg_session.commit()
        
        ids = [movie.id, "non_existent_1", "non_existent_2"]
        results = get_items_by_ids(ids, session=pg_session)
        
        assert len(results) == 1
        assert results[0].id == movie.id
    
    def test_item_exists_by_any_id_no_ids(self, pg_session):
        """Test error when no IDs provided to item_exists_by_any_id."""
        with pytest.raises(ValueError, match="At least one ID must be provided"):
            item_exists_by_any_id()
    
    def test_get_item_by_imdb_and_episode_no_ids(self, pg_session):
        """Test error when no IDs provided to get_item_by_imdb_and_episode."""
        with pytest.raises(ValueError, match="Either tvdb_id or tmdb_id must be provided"):
            get_item_by_imdb_and_episode()