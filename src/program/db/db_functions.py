import os
import shutil
import alembic
from contextlib import contextmanager
from functools import wraps
from threading import RLock
from time import time

from loguru import logger
from threading import Event
from typing import TYPE_CHECKING, Optional
from datetime import datetime, timedelta
from sqlalchemy import delete, func, insert, inspect, or_, select, text, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, selectinload

from program.media.stream import Stream, StreamBlacklistRelation, StreamRelation
from program.services.libraries.symlink import fix_broken_symlinks
from program.settings.manager import settings_manager
from program.utils import root_dir
from program.media.state import States

from .db import db

if TYPE_CHECKING:
    from program.media.item import MediaItem


# Simple in-memory cache for static database queries
class SimpleCache:
    """Thread-safe in-memory cache with TTL support for static data only."""

    def __init__(self):
        self._cache = {}
        self._lock = RLock()

    def get(self, key: str):
        """Get value from cache if not expired."""
        with self._lock:
            if key in self._cache:
                value, expiry = self._cache[key]
                if time() < expiry:
                    return value
                else:
                    del self._cache[key]
        return None

    def set(self, key: str, value, ttl: int = 300):  # 5 minute default TTL
        """Set value in cache with TTL."""
        with self._lock:
            self._cache[key] = (value, time() + ttl)

    def clear(self):
        """Clear all cached data."""
        with self._lock:
            self._cache.clear()


# Global cache instance for static data
_static_cache = SimpleCache()


def clear_static_cache():
    """Clear all cached static data. Call this when data is modified."""
    _static_cache.clear()


@contextmanager
def managed_session(auto_commit: bool = True, auto_rollback: bool = True):
    """
    Context manager for database sessions with automatic cleanup and error handling.

    Args:
        auto_commit: Whether to automatically commit on success
        auto_rollback: Whether to automatically rollback on error
    """
    session = db.Session()
    try:
        yield session
        if auto_commit:
            session.commit()
    except SQLAlchemyError as e:
        if auto_rollback:
            session.rollback()
        logger.error(f"Database error in managed session: {e}")
        raise
    except Exception as e:
        if auto_rollback:
            session.rollback()
        logger.error(f"Unexpected error in managed session: {e}")
        raise
    finally:
        # Ensure session is properly closed and resources are freed
        try:
            session.close()
        except Exception as e:
            logger.warning(f"Error closing session: {e}")


def batch_session_operation(operations: list, batch_size: int = 100):
    """
    Execute multiple database operations in batches with optimized session management.

    Args:
        operations: List of callable operations that take a session parameter
        batch_size: Number of operations to execute per batch
    """
    if not operations:
        return

    for i in range(0, len(operations), batch_size):
        batch = operations[i:i + batch_size]

        with managed_session() as session:
            for operation in batch:
                try:
                    operation(session)
                except Exception as e:
                    logger.error(f"Error in batch operation: {e}")
                    # Continue with other operations in the batch
                    continue


def optimize_session_for_bulk_operations(session: Session):
    """
    Optimize a session for bulk operations by adjusting settings.

    Args:
        session: SQLAlchemy session to optimize
    """
    # Disable autoflush for bulk operations
    session.autoflush = False

    # Use bulk operations when possible
    session.bulk_insert_mappings = session.bulk_insert_mappings
    session.bulk_update_mappings = session.bulk_update_mappings
    logger.debug("Cleared static database query cache")


def cache_static_query(ttl: int = 300):
    """
    Decorator to cache static database queries.
    Only use for queries that return static/semi-static data.
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Create cache key from function name and arguments
            cache_key = f"{func.__name__}:{hash(str(args) + str(sorted(kwargs.items())))}"

            # Try to get from cache first
            cached_result = _static_cache.get(cache_key)
            if cached_result is not None:
                return cached_result

            # Execute function and cache result
            result = func(*args, **kwargs)
            if result is not None:  # Only cache non-None results
                _static_cache.set(cache_key, result, ttl)

            return result
        return wrapper
    return decorator


def get_item_by_id(item_id: str, item_types: list[str] = None, session: Session = None) -> "MediaItem":
    """Get a MediaItem by its ID."""
    if not item_id:
        return None

    from program.media.item import MediaItem, Season, Show
    _session = session if session else db.Session()

    with _session:
        query = (select(MediaItem)
            .where(MediaItem.id == item_id)
            .options(
                selectinload(Show.seasons)
                .selectinload(Season.episodes)
            ))
        if item_types:
            query = query.where(MediaItem.type.in_(item_types))

        item = _session.execute(query).unique().scalar_one_or_none()
        if item:
            _session.expunge(item)
        return item

def get_items_by_ids(ids: list, item_types: list[str] = None, session: Session = None) -> list["MediaItem"]:
    """Get a list of MediaItems by their IDs using a single query to avoid N+1 problem."""
    if not ids:
        return []

    from program.media.item import MediaItem, Season, Show
    _session = session if session else db.Session()

    with _session:
        query = (select(MediaItem)
            .where(MediaItem.id.in_(ids))
            .options(
                selectinload(Show.seasons)
                .selectinload(Season.episodes)
            ))
        if item_types:
            query = query.where(MediaItem.type.in_(item_types))

        items = _session.execute(query).unique().scalars().all()
        for item in items:
            _session.expunge(item)
        return items

@cache_static_query(ttl=600)  # Cache for 10 minutes since external IDs are static
def get_item_by_external_id(imdb_id: str = None, tvdb_id: int = None, tmdb_id: int = None, session: Session = None) -> "MediaItem":
    """Get a MediaItem by its external ID with caching for static data."""
    from program.media.item import MediaItem, Season, Show

    _session = session if session else db.Session()
    query = (
        select(MediaItem)
        .options(
            selectinload(Show.seasons)
            .selectinload(Season.episodes)
        )
        .where(or_(MediaItem.type == "movie", MediaItem.type == "show"))
    )

    if imdb_id:
        query = query.where(MediaItem.imdb_id == imdb_id)
    elif tvdb_id:
        query = query.where(MediaItem.tvdb_id == tvdb_id)
    elif tmdb_id:
        query = query.where(MediaItem.tmdb_id == tmdb_id)
    else:
        raise ValueError("One of the external ids must be given")

    with _session:
        item = _session.execute(query).unique().scalar_one_or_none()
        if item:
            _session.expunge(item)
        return item

def delete_media_item(item: "MediaItem"):
    """Delete a MediaItem and all its associated relationships with optimized session management."""
    with managed_session() as session:
        item = session.merge(item)
        session.delete(item)
        # Clear cache since data was modified
        clear_static_cache()

def delete_media_item_by_id(media_item_id: str, batch_size: int = 30) -> bool:
    """Delete a Movie or Show by _id. If it's a Show, delete its Seasons and Episodes in batches, committing after each batch."""
    from sqlalchemy.exc import IntegrityError
    from program.media.item import Episode, MediaItem, Movie, Season, Show

    if not media_item_id:
        logger.error("Item ID can not be empty")
        return False

    with db.Session() as session:
        try:
            # First, retrieve the media item's type
            media_item_type = session.execute(
                select(MediaItem.type)
                .where(MediaItem.id == media_item_id)
            ).scalar_one_or_none()

            if not media_item_type:
                logger.error(f"No item found with ID {media_item_id}")
                return False

            if media_item_type == "show":
                season_ids = session.execute(
                    select(Season.id).where(Season.parent_id == media_item_id)
                ).scalars().all()

                delete_seasons_and_episodes(session, season_ids, batch_size)
                session.execute(delete(Show).where(Show.id == media_item_id))

            if media_item_type == "movie":
                session.execute(delete(Movie).where(Movie.id == media_item_id))

            if media_item_type == "season":
                delete_seasons_and_episodes(session, [media_item_id], batch_size)
                session.execute(delete(Season).where(Season.id == media_item_id))

            if media_item_type == "episode":
                session.execute(delete(Episode).where(Episode.id == media_item_id))

            session.execute(delete(MediaItem).where(MediaItem.id == media_item_id))
            session.commit()
            # Clear cache since data was modified
            clear_static_cache()
            return True

        except IntegrityError as e:
            logger.error(f"Integrity error while deleting media item with ID {media_item_id}: {e}")
            session.rollback()
            return False
        except Exception as e:
            logger.error(f"Unexpected error while deleting media item with ID {media_item_id}: {e}")
            session.rollback()
            return False

def delete_seasons_and_episodes(session: Session, season_ids: list[str], batch_size: int = 30):
    """Delete seasons and episodes of a show in optimized batches."""
    from program.media.item import Episode, Season
    from program.media.stream import StreamBlacklistRelation, StreamRelation
    from program.media.subtitle import Subtitle

    if not season_ids:
        return

    # Get all episode IDs for all seasons in one query
    all_episode_ids = session.execute(
        select(Episode.id).where(Episode.parent_id.in_(season_ids))
    ).scalars().all()

    # Delete related data in bulk for better performance
    if all_episode_ids:
        # Delete episode-related data in batches
        for i in range(0, len(all_episode_ids), batch_size):
            batch_episode_ids = all_episode_ids[i:i + batch_size]
            session.execute(delete(StreamRelation).where(StreamRelation.parent_id.in_(batch_episode_ids)))
            session.execute(delete(StreamBlacklistRelation).where(StreamBlacklistRelation.media_item_id.in_(batch_episode_ids)))
            session.execute(delete(Subtitle).where(Subtitle.parent_id.in_(batch_episode_ids)))
            session.execute(delete(Episode).where(Episode.id.in_(batch_episode_ids)))
            session.commit()

    # Delete season-related data in bulk
    session.execute(delete(StreamRelation).where(StreamRelation.parent_id.in_(season_ids)))
    session.execute(delete(StreamBlacklistRelation).where(StreamBlacklistRelation.media_item_id.in_(season_ids)))
    session.execute(delete(Subtitle).where(Subtitle.parent_id.in_(season_ids)))
    session.execute(delete(Season).where(Season.id.in_(season_ids)))
    session.commit()

def reset_media_item(item: "MediaItem"):
    """Reset a MediaItem with optimized session management."""
    with managed_session() as session:
        item = session.merge(item)
        item.reset()

def reset_streams(item: "MediaItem"):
    """Reset streams associated with a MediaItem."""
    with db.Session() as session:
        session.execute(delete(StreamRelation).where(StreamRelation.parent_id == item.id))
        session.execute(delete(StreamBlacklistRelation).where(StreamBlacklistRelation.media_item_id == item.id))
        session.commit()

def clear_streams(item: "MediaItem"):
    """Clear all streams for a media item."""
    reset_streams(item)

def clear_streams_by_id(media_item_id: str):
    """Clear all streams for a media item by the MediaItem id."""
    with db.Session() as session:
        session.execute(
            delete(StreamRelation).where(StreamRelation.parent_id == media_item_id)
        )
        session.execute(
            delete(StreamBlacklistRelation).where(StreamBlacklistRelation.media_item_id == media_item_id)
        )
        session.commit()


def clear_streams_batch(media_item_ids: list[str]):
    """Clear all streams for multiple media items with optimized session management."""
    if not media_item_ids:
        return

    with managed_session() as session:
        # Optimize session for bulk operations
        optimize_session_for_bulk_operations(session)

        # Use batch operations for better performance
        session.execute(
            delete(StreamRelation).where(StreamRelation.parent_id.in_(media_item_ids))
        )
        session.execute(
            delete(StreamBlacklistRelation).where(StreamBlacklistRelation.media_item_id.in_(media_item_ids))
        )
        logger.debug(f"Cleared streams for {len(media_item_ids)} media items")


def add_streams_batch(item_stream_pairs: list[tuple[str, int]]):
    """Add multiple stream relationships in a single transaction.

    Args:
        item_stream_pairs: List of (media_item_id, stream_id) tuples
    """
    if not item_stream_pairs:
        return

    with db.Session() as session:
        # Prepare batch insert data
        relations_data = [
            {"parent_id": item_id, "child_id": stream_id}
            for item_id, stream_id in item_stream_pairs
        ]

        # Use bulk insert for better performance
        session.execute(insert(StreamRelation), relations_data)
        session.commit()
        logger.debug(f"Added {len(item_stream_pairs)} stream relationships")


def blacklist_streams_batch(item_stream_pairs: list[tuple[str, int]]):
    """Blacklist multiple streams in a single transaction.

    Args:
        item_stream_pairs: List of (media_item_id, stream_id) tuples
    """
    if not item_stream_pairs:
        return

    with db.Session() as session:
        # Prepare batch insert data
        blacklist_data = [
            {"media_item_id": item_id, "stream_id": stream_id}
            for item_id, stream_id in item_stream_pairs
        ]

        # Use bulk insert for better performance
        session.execute(insert(StreamBlacklistRelation), blacklist_data)
        session.commit()
        logger.debug(f"Blacklisted {len(item_stream_pairs)} streams")


def blacklist_stream(item: "MediaItem", stream: Stream, session: Session = None) -> bool:
    """Blacklist a stream for a media item."""
    close_session = False
    if session is None:
        session = db.Session()
        item = session.execute(select(type(item)).where(type(item).id == item.id)).unique().scalar_one()
        close_session = True

    try:
        item = session.merge(item)
        association_exists = session.query(
            session.query(StreamRelation)
            .filter(StreamRelation.parent_id == item.id)
            .filter(StreamRelation.child_id == stream.id)
            .exists()
        ).scalar()

        if association_exists:
            session.execute(
                delete(StreamRelation)
                .where(StreamRelation.parent_id == item.id)
                .where(StreamRelation.child_id == stream.id)
            )
            session.execute(
                insert(StreamBlacklistRelation)
                .values(media_item_id=item.id, stream_id=stream.id)
            )
            item.store_state()
            session.commit()
            return True
        return False
    finally:
        if close_session:
            session.close()

def unblacklist_stream(item: "MediaItem", stream: Stream, session: Session = None) -> bool:
    """Unblacklist a stream for a media item."""
    close_session = False
    if session is None:
        session = db.Session()
        item = session.execute(select(type(item)).where(type(item).id == item.id)).unique().scalar_one()
        close_session = True

    try:
        item = session.merge(item)
        association_exists = session.query(
            session.query(StreamBlacklistRelation)
            .filter(StreamBlacklistRelation.media_item_id == item.id)
            .filter(StreamBlacklistRelation.stream_id == stream.id)
            .exists()
        ).scalar()

        if association_exists:
            session.execute(
                delete(StreamBlacklistRelation)
                .where(StreamBlacklistRelation.media_item_id == item.id)
                .where(StreamBlacklistRelation.stream_id == stream.id)
            )
            session.execute(
                insert(StreamRelation)
                .values(parent_id=item.id, child_id=stream.id)
            )
            item.store_state()
            session.commit()
            return True
        return False
    finally:
        if close_session:
            session.close()

def get_item_ids(session: Session, item_id: str) -> tuple[str, list[str]]:
    """Get the item ID and all related item IDs for a given MediaItem."""
    from program.media.item import Episode, MediaItem, Season

    item_type = session.query(MediaItem.type).filter(MediaItem.id == item_id).scalar()
    related_ids = []

    if item_type == "show":
        season_ids = session.execute(
            select(Season.id).where(Season.parent_id == item_id)
        ).scalars().all()

        # Get all episode IDs for all seasons in a single query to avoid N+1
        if season_ids:
            episode_ids = session.execute(
                select(Episode.id).where(Episode.parent_id.in_(season_ids))
            ).scalars().all()
            related_ids.extend(episode_ids)
        related_ids.extend(season_ids)

    elif item_type == "season":
        episode_ids = session.execute(
            select(Episode.id).where(Episode.parent_id == item_id)
        ).scalars().all()
        related_ids.extend(episode_ids)

    return item_id, related_ids

def get_item_by_symlink_path(filepath: str, session: Session = None) -> list["MediaItem"]:
    """Get a list of MediaItems by their symlink path."""
    from program.media.item import MediaItem
    _session = session if session else db.Session()

    with _session:
        items = _session.execute(
            select(MediaItem).where(MediaItem.symlink_path == filepath)
        ).unique().scalars().all()
        for item in items:
            _session.expunge(item)
        return items

@cache_static_query(ttl=600)  # Cache for 10 minutes since IMDb metadata is static
def get_item_by_imdb_and_episode(imdb_id: str, season_number: Optional[int] = None, episode_number: Optional[int] = None, session: Session = None) -> list["MediaItem"]:
    """Get a MediaItem by its IMDb ID and optionally season and episode numbers with caching."""
    from program.media.item import Episode, Movie, Season, Show

    _session = session if session else db.Session()

    with _session:
        if season_number is not None and episode_number is not None:
            # Look for an episode
            items = _session.execute(
                select(Episode).options(
                    selectinload(Episode.parent).selectinload(Season.parent)
                ).where(
                    Episode.parent.has(Season.parent.has(Show.imdb_id == imdb_id)),
                    Episode.parent.has(Season.number == season_number),
                    Episode.number == episode_number
                )
            ).scalars().all()
        else:
            # Look for a movie
            items = _session.execute(
                select(Movie).where(Movie.imdb_id == imdb_id)
            ).scalars().all()

        for item in items:
            _session.expunge(item)
        return items

def retry_library(session) -> list[str]:
    """Retry items that failed to download."""
    from program.media.item import MediaItem
    session = session if session else db.Session()

    count = session.execute(
        select(func.count(MediaItem.id))
        .where(MediaItem.last_state.not_in([States.Completed, States.Unreleased, States.Paused, States.Failed]))
        .where(MediaItem.type.in_(["movie", "show"]))
    ).scalar_one()

    if count == 0:
        return []

    logger.log("PROGRAM", f"Starting retry process for {count} items.")

    items_query = (
        select(MediaItem.id)
        .where(MediaItem.last_state.not_in([States.Completed, States.Unreleased, States.Paused, States.Failed]))
        .where(MediaItem.type.in_(["movie", "show"]))
        .order_by(MediaItem.requested_at.desc())
    )

    result = session.execute(items_query)
    return [item_id for item_id in result.scalars()]

def update_ongoing(session) -> list[tuple[str, str, str]]:
    """Update state for ongoing and unreleased items."""
    from program.media.item import MediaItem
    session = session if session else db.Session()

    item_ids = session.execute(
        select(MediaItem.id)
        .where(MediaItem.type.in_(["movie", "episode"]))
        .where(MediaItem.last_state.in_([States.Ongoing, States.Unreleased]))
    ).scalars().all()

    if not item_ids:
        logger.debug("No ongoing or unreleased items to update.")
        return []

    logger.debug(f"Updating state for {len(item_ids)} ongoing and unreleased items.")

    # Load all items in a single query to avoid N+1 problem
    items = session.execute(
        select(MediaItem).where(MediaItem.id.in_(item_ids))
    ).unique().scalars().all()

    updated_items = []
    items_to_update = []

    for item in items:
        try:
            previous_state, new_state = item.store_state()
            if previous_state != new_state:
                updated_items.append((item.id, previous_state.name, new_state.name))
                items_to_update.append(item)
        except Exception as e:
            logger.error(f"Failed to update state for item with ID {item.id}: {e}")

    # Bulk update all changed items
    if items_to_update:
        try:
            for item in items_to_update:
                session.merge(item)
            session.commit()
        except Exception as e:
            logger.error(f"Failed to commit bulk state updates: {e}")
            session.rollback()

    return updated_items

def create_calendar(session: Session) -> dict:
    """Create a calendar of all the items in the library."""
    from program.media.item import MediaItem, Show, Season
    session = session if session else db.Session()

    results = session.execute(
        select(MediaItem)
        .options(selectinload(Show.seasons).selectinload(Season.episodes))
        .where(MediaItem.type.in_(["movie", "episode"]))
        .where(MediaItem.last_state != States.Completed)
        .where(MediaItem.aired_at.is_not(None))
        .where(MediaItem.aired_at >= datetime.now() - timedelta(days=1))
    ).unique().scalars().all()

    calendar = {}
    for item in results:
        calendar[item.id] = {}
        calendar[item.id]["trakt_id"] = item.trakt_id
        calendar[item.id]["imdb_id"] = item.imdb_id
        calendar[item.id]["tvdb_id"] = item.tvdb_id
        calendar[item.id]["tmdb_id"] = item.tmdb_id
        calendar[item.id]["aired_at"] = item.aired_at
        if item.type == "episode":
            calendar[item.id]["title"] = item.parent.parent.title
            calendar[item.id]["season"] = item.parent.number
            calendar[item.id]["episode"] = item.number
        else:
            calendar[item.id]["title"] = item.title

    return calendar

def run_thread_with_db_item(fn, service, program, event: Event, cancellation_event: Event) -> Optional[str]:
    """Run a thread with a MediaItem."""
    from program.media.item import MediaItem
    if event:
        with db.Session() as session:
            if event.item_id:
                input_item = get_item_by_id(event.item_id, session=session)
                if input_item:
                    input_item = session.merge(input_item)
                    res = next(fn(input_item), None)
                    if res:
                        if isinstance(res, tuple):
                            item, run_at = res
                            res = item.id, run_at
                        else:
                            item = res
                            res = item.id
                        if not isinstance(item, MediaItem):
                            logger.log("PROGRAM", f"Service {service.__name__} emitted {item} from input item {input_item} of type {type(item).__name__}, backing off.")
                            program.em.remove_id_from_queues(input_item.id)

                        if not cancellation_event.is_set():
                            # Update parent item
                            if input_item.type == "episode":
                                input_item.parent.parent.store_state()
                            elif input_item.type == "season":
                                input_item.parent.store_state()
                            else:
                                input_item.store_state()
                            session.commit()
                        return res
            # This is in bad need of indexing...
            if event.content_item:
                indexed_item = next(fn(event.content_item), None)
                if indexed_item is None:
                    logger.debug(f"Unable to index {event.content_item.log_string if event.content_item.log_string is not None else event.content_item.imdb_id}")
                    return None
                indexed_item.store_state()
                session.add(indexed_item)
                item_id = indexed_item.id
                if not cancellation_event.is_set():
                    session.commit()
                return item_id
    # Content services dont pass events, get ready for a ride!
    else:
        for i in fn():
            if isinstance(i, MediaItem):
                i = [i]
            if isinstance(i, list):
                for item in i:
                    if isinstance(item, MediaItem):
                        program.em.add_item(item, service)
    return None

def hard_reset_database() -> None:
    """Resets the database to a fresh state while maintaining migration capability."""
    logger.log("DATABASE", "Starting Hard Reset of Database")

    # Store current alembic version before reset
    current_version = None
    try:
        with db.engine.connect() as connection:
            result = connection.execute(text("SELECT version_num FROM alembic_version"))
            current_version = result.scalar()
    except Exception:
        pass

    with db.engine.connect() as connection:
        # Ensure we're in AUTOCOMMIT mode for PostgreSQL schema operations
        connection = connection.execution_options(isolation_level="AUTOCOMMIT")

        try:
            # Terminate existing connections for PostgreSQL
            if db.engine.name == "postgresql":
                connection.execute(text("""
                    SELECT pg_terminate_backend(pid)
                    FROM pg_stat_activity
                    WHERE datname = current_database()
                    AND pid <> pg_backend_pid()
                """))

                # Drop and recreate schema
                connection.execute(text("DROP SCHEMA public CASCADE"))
                connection.execute(text("CREATE SCHEMA public"))
                connection.execute(text("GRANT ALL ON SCHEMA public TO public"))
                logger.log("DATABASE", "Schema reset complete")

            # For SQLite, drop all tables
            elif db.engine.name == "sqlite":
                connection.execute(text("PRAGMA foreign_keys = OFF"))

                # Get all tables
                tables = connection.execute(text(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )).scalars().all()

                # Drop each table
                for table in tables:
                    connection.execute(text(f"DROP TABLE IF EXISTS {table}"))

                connection.execute(text("PRAGMA foreign_keys = ON"))
                logger.log("DATABASE", "All tables dropped")

            # Recreate all tables
            db.Model.metadata.create_all(connection)
            logger.log("DATABASE", "All tables recreated")

            # If we had a previous version, restore it
            if current_version:
                connection.execute(text("CREATE TABLE IF NOT EXISTS alembic_version (version_num VARCHAR(32) NOT NULL)"))
                connection.execute(text("INSERT INTO alembic_version (version_num) VALUES (:version)"), 
                                {"version": current_version})
                logger.log("DATABASE", f"Restored alembic version to: {current_version}")
            else:
                # Stamp with head version if no previous version
                alembic.stamp("head")
                logger.log("DATABASE", "Database stamped with head revision")

        except Exception as e:
            logger.error(f"Error during database reset: {str(e)}")
            raise

    logger.log("DATABASE", "Hard Reset Complete")

    # Verify database state
    try:
        with db.engine.connect() as connection:
            # Check if all tables exist
            inspector = inspect(db.engine)
            all_tables = inspector.get_table_names()
            logger.log("DATABASE", f"Verified tables: {', '.join(all_tables)}")

            # Verify alembic version
            result = connection.execute(text("SELECT version_num FROM alembic_version"))
            version = result.scalar()
            logger.log("DATABASE", f"Verified alembic version: {version}")

    except Exception as e:
        logger.error(f"Error verifying database state: {str(e)}")
        raise

def hard_reset_database_pre_migration() -> None:
    """Resets the database to a fresh state."""
    logger.log("DATABASE", "Starting Hard Reset of Database")

    # Disable foreign key checks temporarily
    with db.engine.connect() as connection:
        if db.engine.name == "sqlite":
            connection.execute(text("PRAGMA foreign_keys = OFF"))
        elif db.engine.name == "postgresql":
            connection.execute(text("SET CONSTRAINTS ALL DEFERRED"))

        try:
            for table in reversed(db.Model.metadata.sorted_tables):
                try:
                    table.drop(connection, checkfirst=True)
                    logger.log("DATABASE", f"Dropped table: {table.name}")
                except Exception as e:
                    logger.log("DATABASE", f"Error dropping table {table.name}: {str(e)}")

            try:
                connection.execute(text("DROP TABLE IF EXISTS alembic_version"))
                logger.log("DATABASE", "Alembic version table dropped")
            except Exception as e:
                logger.log("DATABASE", f"Error dropping alembic_version table: {str(e)}")

            db.Model.metadata.create_all(connection)
            logger.log("DATABASE", "All tables recreated")

            # Re-enable foreign key checks
            if db.engine.name == "sqlite":
                connection.execute(text("PRAGMA foreign_keys = ON"))
            elif db.engine.name == "postgresql":
                connection.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))

            connection.commit()
        except Exception as e:
            connection.rollback()
            logger.log("DATABASE", f"Error during database reset: {str(e)}")
            raise

    try:
        alembic_dir = root_dir / "data" / "alembic"
        logger.log("DATABASE", "Removing Alembic Directory")
        shutil.rmtree(alembic_dir, ignore_errors=True)
        os.makedirs(alembic_dir, exist_ok=True)
        alembic.init(alembic_dir)
        logger.log("DATABASE", "Alembic reinitialized")
    except Exception as e:
        logger.log("DATABASE", f"Error reinitializing Alembic: {str(e)}")

    logger.log("DATABASE", "Pre Migration - Hard Reset Complete")

# Hard Reset Database
reset = os.getenv("HARD_RESET", None)
if reset is not None and reset.lower() in ["true","1"]:
    hard_reset_database()
    exit(0)

# Hard Reset Database
reset = os.getenv("HARD_RESET_PRE_MIGRATION", None)
if reset is not None and reset.lower() in ["true","1"]:
    hard_reset_database_pre_migration()
    exit(0)

# Repair Symlinks
if os.getenv("REPAIR_SYMLINKS", None) is not None and os.getenv("REPAIR_SYMLINKS").lower() in ["true","1"]:
    fix_broken_symlinks(settings_manager.settings.symlink.library_path, settings_manager.settings.symlink.rclone_path)
    exit(0)

def clear_failed_attempts(session: Session) -> None:
    """Clear all `failed_attempts` from all items in the database."""
    from program.media.item import MediaItem
    session.execute(update(MediaItem).where(MediaItem.failed_attempts > 0).values(failed_attempts=0))
    session.commit()

def clear_scraped_times(session: Session) -> None:
    """Clear all `scraped_times` from all items in the database."""
    from program.media.item import MediaItem
    session.execute(update(MediaItem).where(MediaItem.scraped_times > 0).values(scraped_times=0))
    session.commit()
