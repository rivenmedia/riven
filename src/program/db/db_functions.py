# program/services/db_functions.py
from __future__ import annotations

import os
from contextlib import contextmanager
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any, Dict, Iterator, List, Optional, Sequence, Tuple

from loguru import logger
from sqlalchemy import case, delete, func, inspect, or_, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, object_session, selectinload
from sqlalchemy.sql import bindparam

import alembic
from program.services.libraries.symlink import fix_broken_symlinks
from program.settings.manager import settings_manager

from .db import db

if TYPE_CHECKING:
    from program.media.item import MediaItem


@contextmanager
def _maybe_session(session: Optional[Session]) -> Iterator[Tuple[Session, bool]]:
    """
    Yield a (session, owns_session) pair.

    If `session` is None, create a new db.Session() and close it on exit.
    Otherwise, yield the caller-provided session and do not close it.
    """
    if session is not None:
        yield session, False
        return
    _s = db.Session()
    try:
        yield _s, True
    finally:
        _s.close()

def get_item_by_id(
    item_id: str,
    item_types: Optional[List[str]] = None,
    session: Optional[Session] = None,
) -> "MediaItem" | None:
    """
    Get a MediaItem by its ID, optionally constraining by type.
    Loads seasons/episodes for shows via selectinload.
    Returns a detached instance safe for use outside the session.
    """
    if not item_id:
        return None

    from program.media.item import MediaItem, Season, Show

    with _maybe_session(session) as (_s, _owns):
        query = (
            select(MediaItem)
            .where(MediaItem.id == item_id)
            .options(selectinload(Show.seasons).selectinload(Season.episodes))
        )
        if item_types:
            query = query.where(MediaItem.type.in_(item_types))

        item = _s.execute(query).unique().scalar_one_or_none()
        if item:
            _s.expunge(item)
        return item

def get_items_by_ids(
    ids: Sequence[str],
    item_types: Optional[List[str]] = None,
    session: Optional[Session] = None,
) -> List["MediaItem"]:
    """
    Fetch a list of MediaItems by their IDs using one round trip.

    - Preserves the input order at the SQL layer via CASE(..) ORDER BY.
    - Eager-loads Show -> seasons -> episodes using select-in.
    - Calls .unique() to collapse duplicates that arise from joined eager loads.
    - Returns detached instances (expunged) to avoid lazy-loads on closed sessions.
    """
    if not ids:
        return []

    from program.media.item import MediaItem, Season, Show

    pos = {v: i for i, v in enumerate(ids)}
    order_clause = case(pos, value=MediaItem.id, else_=len(ids))
    id_param = bindparam("item_ids", expanding=True)

    stmt = (
        select(MediaItem)
        .where(MediaItem.id.in_(id_param))
        .options(selectinload(Show.seasons).selectinload(Season.episodes))
        .order_by(order_clause)
    )
    if item_types:
        stmt = stmt.where(MediaItem.type.in_(item_types))

    close_me = False
    if session is None:
        from program.db.db import db
        _s: Session = db.Session()
        close_me = True
    else:
        _s = session

    try:
        rows = _s.execute(stmt, {"item_ids": list(ids)}).unique().scalars().all()
        for obj in rows:
            if object_session(obj) is _s:
                _s.expunge(obj)

        by_id: Dict[str, "MediaItem"] = {m.id: m for m in rows}
        return [by_id[i] for i in ids if i in by_id]
    finally:
        if close_me:
            _s.close()

def get_item_by_external_id(
    imdb_id: Optional[str] = None,
    tvdb_id: Optional[int] = None,
    tmdb_id: Optional[int] = None,
    session: Optional[Session] = None,
) -> "MediaItem" | None:
    """
    Get a movie/show by any external ID (IMDb/TVDB/TMDB).
    Loads seasons/episodes for shows via selectinload.
    """
    from program.media.item import MediaItem, Season, Show

    conditions: List[Any] = []
    if imdb_id:
        conditions.append(MediaItem.imdb_id == str(imdb_id))
    if tvdb_id:
        conditions.append(MediaItem.tvdb_id == str(tvdb_id))
    if tmdb_id:
        conditions.append(MediaItem.tmdb_id == str(tmdb_id))

    if not conditions:
        raise ValueError("At least one external ID must be provided")

    with _maybe_session(session) as (_s, _owns):
        query = (
            select(MediaItem)
            .options(selectinload(Show.seasons).selectinload(Season.episodes))
            .where(MediaItem.type.in_(["movie", "show"]))
            .where(or_(*conditions))
        )
        item = _s.execute(query).unique().scalar_one_or_none()
        if item:
            _s.expunge(item)
        return item

def item_exists_by_any_id(
    item_id: Optional[str] = None,
    tvdb_id: Optional[str] = None,
    tmdb_id: Optional[str] = None,
    imdb_id: Optional[str] = None,
    session: Optional[Session] = None,
) -> bool:
    """
    Return True if ANY provided identifier matches an existing MediaItem.

    Previous behavior chained .where() equalities on all fields, which only
    matched when *all* IDs belonged to the same row. This version matches ANY.
    """
    from program.media.item import MediaItem

    if not any([item_id, tvdb_id, tmdb_id, imdb_id]):
        raise ValueError("At least one ID must be provided")

    clauses: List[Any] = []
    if item_id is not None:
        clauses.append(MediaItem.id == str(item_id))
    if tvdb_id is not None:
        clauses.append(MediaItem.tvdb_id == str(tvdb_id))
    if tmdb_id is not None:
        clauses.append(MediaItem.tmdb_id == str(tmdb_id))
    if imdb_id is not None:
        clauses.append(MediaItem.imdb_id == str(imdb_id))

    with _maybe_session(session) as (_s, _owns):
        count = _s.execute(
            select(func.count()).select_from(MediaItem).where(or_(*clauses)).limit(1)
        ).scalar_one()
        return count > 0

def get_item_by_symlink_path(
    filepath: str,
    session: Optional[Session] = None,
) -> List["MediaItem"]:
    """
    Return items that match an exact symlink_path. Returns detached instances.
    """
    from program.media.item import MediaItem

    with _maybe_session(session) as (_s, _owns):
        items = (
            _s.execute(select(MediaItem).where(MediaItem.symlink_path == filepath))
            .unique()
            .scalars()
            .all()
        )
        for itm in items:
            _s.expunge(itm)
        return items

def get_item_by_imdb_and_episode(
    tvdb_id: str = None,
    tmdb_id: str = None,
    season_number: Optional[int] = None,
    episode_number: Optional[int] = None,
    session: Optional[Session] = None,
) -> List["MediaItem"]:
    """
    If season+episode provided, return matching Episode(s) for the show with tvdb_id.
    Otherwise, return Movie(s) with that tvdb_id.
    Returns detached instances.
    """
    from program.media.item import Episode, Movie, Season, Show

    if not tvdb_id and not tmdb_id:
        raise ValueError("Either tvdb_id or tmdb_id must be provided")

    with _maybe_session(session) as (_s, _owns):
        if season_number is not None and episode_number is not None:
            rows = _s.execute(
                select(Episode)
                .options(selectinload(Episode.parent).selectinload(Season.parent))
                .where(
                    Episode.parent.has(Season.parent.has(Show.tvdb_id == tvdb_id)),
                    Episode.parent.has(Season.number == season_number),
                    Episode.number == episode_number,
                )
            ).scalars().all()
            for r in rows:
                _s.expunge(r)
            return rows

        rows = _s.execute(select(Movie).where(Movie.tmdb_id == tmdb_id)).scalars().all()
        for r in rows:
            _s.expunge(r)
        return rows


def delete_media_item_by_id(media_item_id: str) -> bool:
    """
    Delete any MediaItem (movie/show/season/episode) and all dependents.

    Steps:
      - Resolve root type and collect descendant Season/Episode MediaItem ids.
      - DELETE descendant MediaItem rows (DB cascades remove concrete rows + links + subtitles).
      - DELETE root MediaItem row.
      - PURGE orphan Stream rows (those with no remaining associations).

    Returns:
      True on success, False on error.
    """

    from program.media.item import Episode, MediaItem, Season

    if not media_item_id:
        logger.error("Item ID can not be empty")
        return False

    with db.Session() as s:
        try:
            root_type = s.execute(
                select(MediaItem.type).where(MediaItem.id == media_item_id)
            ).scalar_one_or_none()

            if not root_type:
                logger.error(f"No item found with ID {media_item_id}")
                return False

            season_ids: list[str] = []
            episode_ids: list[str] = []

            if root_type == "show":
                season_ids = s.execute(
                    select(Season.id).where(Season.parent_id == media_item_id)
                ).scalars().all()
                if season_ids:
                    episode_ids = s.execute(
                        select(Episode.id).where(Episode.parent_id.in_(season_ids))
                    ).scalars().all()

            elif root_type == "season":
                episode_ids = s.execute(
                    select(Episode.id).where(Episode.parent_id == media_item_id)
                ).scalars().all()

            # 1) remove descendant items
            if episode_ids:
                s.execute(delete(MediaItem).where(MediaItem.id.in_(episode_ids)))
            if season_ids:
                s.execute(delete(MediaItem).where(MediaItem.id.in_(season_ids)))

            # 2) remove root
            s.execute(delete(MediaItem).where(MediaItem.id == media_item_id))

            # 3) purge orphan streams *within the same transaction*
            _purge_orphan_streams_tx(s)

            s.commit()
            return True

        except IntegrityError as e:
            logger.error(f"Integrity error while deleting media item with ID {media_item_id}: {e}")
            s.rollback()
            return False
        except Exception as e:
            logger.error(f"Unexpected error while deleting media item with ID {media_item_id}: {e}")
            s.rollback()
            return False


def delete_media_item(item: "MediaItem") -> None:
    """
    Backwards-compatible convenience wrapper around delete_media_item_by_id().
    """
    delete_media_item_by_id(item.id)


def get_item_ids(session: Session, item_id: str) -> Tuple[str, List[str]]:
    """
    Return (root_id, related_ids) where related_ids are all children under the root,
    depending on the root type. Uses set-based selects.
    """
    from program.media.item import Episode, MediaItem, Season

    item_type = session.execute(
        select(MediaItem.type).where(MediaItem.id == item_id)
    ).scalar_one_or_none()

    related_ids: List[str] = []
    if item_type == "show":
        season_ids = session.execute(
            select(Season.id).where(Season.parent_id == item_id)
        ).scalars().all()
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


def retry_library(session: Optional[Session] = None) -> List[str]:
    """
    Return IDs of items that should be retried. Single query, no pre-count.
    """
    from program.media.item import MediaItem
    from program.media.state import States

    with _maybe_session(session) as (s, owns):
        return s.execute(
            select(MediaItem.id)
            .where(
                MediaItem.last_state.not_in(
                    [States.Completed, States.Unreleased, States.Paused, States.Failed]
                )
            )
            .where(MediaItem.type.in_(["movie", "show"]))
            .order_by(MediaItem.requested_at.desc())
        ).scalars().all()


def update_ongoing(session: Optional[Session] = None) -> List[str]:
    """
    Update state for ongoing/unreleased items with one commit.
    Calls store_state() per item (state machine), aggregates changed IDs.
    """
    from program.media.item import MediaItem
    from program.media.state import States

    with _maybe_session(session) as (s, owns):
        item_ids = s.execute(
            select(MediaItem.id)
            .where(MediaItem.type.in_(["movie", "episode"]))
            .where(MediaItem.last_state.in_([States.Ongoing, States.Unreleased]))
        ).scalars().all()

        if not item_ids:
            logger.debug("No ongoing or unreleased items to update.")
            return []

        logger.debug(f"Updating state for {len(item_ids)} ongoing and unreleased items.")

        changed: List[str] = []
        items = s.execute(select(MediaItem).where(MediaItem.id.in_(item_ids))).unique().scalars().all()
        for item in items:
            try:
                previous_state, new_state = item.store_state()
                if previous_state != new_state:
                    changed.append(item.id)
            except Exception as e:
                logger.error(f"Failed to update state for item with ID {item.id}: {e}")

        if changed:
            s.commit()
            for iid in changed:
                logger.log("PROGRAM", f"Updated state for {iid}.")

        return changed


def create_calendar(session: Optional[Session] = None) -> Dict[str, Dict[str, Any]]:
    """
    Create a calendar of all upcoming/ongoing items in the library.
    Returns a dict keyed by item.id with minimal metadata for scheduling.
    """
    from program.media.item import MediaItem, Season, Show
    from program.media.state import States

    session = session if session else db.Session()

    results = session.execute(
        select(MediaItem)
        .options(selectinload(Show.seasons).selectinload(Season.episodes))
        .where(MediaItem.type.in_(["movie", "episode"]))
        .where(MediaItem.last_state != States.Completed)
        .where(MediaItem.aired_at.is_not(None))
        .where(MediaItem.aired_at >= datetime.now() - timedelta(days=1))
    ).unique().scalars().all()

    calendar: Dict[str, Dict[str, Any]] = {}
    for item in results:
        calendar[item.id] = {
            "trakt_id": item.trakt_id,
            "imdb_id": item.imdb_id,
            "tvdb_id": item.tvdb_id,
            "tmdb_id": item.tmdb_id,
            "aired_at": item.aired_at,
        }
        if item.type == "episode":
            calendar[item.id]["title"] = item.parent.parent.title
            calendar[item.id]["season"] = item.parent.number
            calendar[item.id]["episode"] = item.number
        else:
            calendar[item.id]["title"] = item.title

    return calendar


def _purge_orphan_streams_tx(session: Session) -> int:
    """
    Delete Stream rows that have no parent references in either association table.
    Must be called *inside* a transaction after cascades have removed association rows.

    Returns:
        int: number of Stream rows deleted.
    """
    from program.media.stream import Stream, StreamBlacklistRelation, StreamRelation

    # Streams with zero links in BOTH association tables
    orphan_ids_subq = (
        select(Stream.id)
        .outerjoin(StreamRelation, StreamRelation.child_id == Stream.id)
        .outerjoin(StreamBlacklistRelation, StreamBlacklistRelation.stream_id == Stream.id)
        .group_by(Stream.id)
        .having(
            func.count(StreamRelation.id) == 0,
            func.count(StreamBlacklistRelation.id) == 0,
        )
        .subquery()
    )

    result = session.execute(
        delete(Stream).where(Stream.id.in_(select(orphan_ids_subq.c.id)))
    )
    # SQLAlchemy 2.0 returns rowcount in result.rowcount (may be -1 depending on DB)
    return int(result.rowcount or 0)


def hard_reset_database() -> None:
    """Resets the database to a fresh state while maintaining migration capability."""
    logger.info("Starting Hard Reset of Database")

    # Store current alembic version before reset
    current_version = None
    try:
        with db.engine.connect() as connection:
            result = connection.execute(text("SELECT version_num FROM alembic_version"))
            current_version = result.scalar()
    except Exception:
        logger.error("Could not retrieve current alembic version - database may not exist yet")

    with db.engine.connect() as connection:
        # Ensure we're in AUTOCOMMIT mode for PostgreSQL schema operations
        autocommit_conn = connection.execution_options(isolation_level="AUTOCOMMIT")

        try:
            # Terminate existing connections for PostgreSQL
            if db.engine.name == "postgresql":
                autocommit_conn.execute(
                    text(
                        """
                        SELECT pg_terminate_backend(pid)
                        FROM pg_stat_activity
                        WHERE datname = current_database()
                        AND pid <> pg_backend_pid()
                        """
                    )
                )

                # Drop and recreate schema
                autocommit_conn.execute(text("DROP SCHEMA public CASCADE"))
                autocommit_conn.execute(text("CREATE SCHEMA public"))
                autocommit_conn.execute(text("GRANT ALL ON SCHEMA public TO public"))
                logger.info("Schema reset complete")

            # For SQLite, drop all tables
            elif db.engine.name == "sqlite":
                autocommit_conn.execute(text("PRAGMA foreign_keys = OFF"))

                tables = autocommit_conn.execute(
                    text("SELECT name FROM sqlite_master WHERE type='table'")
                ).scalars().all()

                for table in tables:
                    autocommit_conn.execute(text(f"DROP TABLE IF EXISTS {table}"))

                autocommit_conn.execute(text("PRAGMA foreign_keys = ON"))
                logger.info("All tables dropped")

            # Recreate all tables
            db.Model.metadata.create_all(autocommit_conn)
            logger.info("All tables recreated")

            # If we had a previous version, restore it
            if current_version:
                autocommit_conn.execute(
                    text(
                        "CREATE TABLE IF NOT EXISTS alembic_version (version_num VARCHAR(32) NOT NULL)"
                    )
                )
                autocommit_conn.execute(
                    text("INSERT INTO alembic_version (version_num) VALUES (:version)"),
                    {"version": current_version},
                )
                logger.info(f"Restored alembic version to: {current_version}")
            else:
                # Stamp with head version if no previous version
                alembic.stamp("head")
                logger.info("Database stamped with head revision")

        except Exception as e:
            logger.error(f"Error during database reset: {str(e)}")
            raise

    logger.info("Hard Reset Complete")

    # Verify database state
    try:
        with db.engine.connect() as connection:
            inspector = inspect(db.engine)
            all_tables = inspector.get_table_names()
            logger.info(f"Verified tables: {', '.join(all_tables)}")

            result = connection.execute(text("SELECT version_num FROM alembic_version"))
            version = result.scalar()
            logger.info(f"Verified alembic version: {version}")

    except Exception as e:
        logger.error(f"Error verifying database state: {str(e)}")
        raise


if os.getenv("RIVEN_HARD_RESET", None) is not None and os.getenv("RIVEN_HARD_RESET", "").lower() in ["true", "1"]:
    hard_reset_database()
    raise SystemExit(0)

if os.getenv("RIVEN_REPAIR_SYMLINKS", None) is not None and os.getenv("RIVEN_REPAIR_SYMLINKS").lower() in ["true", "1"]:
    fix_broken_symlinks(settings_manager.settings.symlink.library_path, settings_manager.settings.symlink.rclone_path)
    raise SystemExit(0)
