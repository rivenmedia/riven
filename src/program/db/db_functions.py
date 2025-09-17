# program/services/db_functions.py
from __future__ import annotations

import os
from contextlib import contextmanager
from datetime import datetime, timedelta
from threading import Event
from typing import TYPE_CHECKING, Any, Dict, Iterator, List, Optional, Sequence, Tuple

from kink import di, inject
from loguru import logger
from sqlalchemy import case, delete, func, insert, inspect, or_, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, object_session, selectinload
from sqlalchemy.sql import bindparam

import alembic
from program.apis.tvdb_api import TVDBApi
from program.media.state import States
from program.media.stream import Stream, StreamBlacklistRelation, StreamRelation
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
    item_id: int,
    item_types: Optional[List[str]] = None,
    session: Optional[Session] = None,
    *,
    load_tree: bool = False,
) -> "MediaItem" | None:
    """
    Get a MediaItem by its ID, optionally constraining by type.
    Optionally load seasons/episodes for shows via selectinload if load_tree=True.
    Returns a detached instance safe for use outside the session.
    """
    if not item_id:
        return None

    from program.media.item import MediaItem, Season, Show

    with _maybe_session(session) as (_s, _owns):
        query = select(MediaItem).where(MediaItem.id == item_id)
        if load_tree:
            query = query.options(selectinload(Show.seasons).selectinload(Season.episodes))
        if item_types:
            query = query.where(MediaItem.type.in_(item_types))

        item = _s.execute(query).unique().scalar_one_or_none()
        if item:
            _s.expunge(item)
        return item

def get_items_by_ids(
    ids: Sequence[int],
    item_types: Optional[List[str]] = None,
    session: Optional[Session] = None,
    *,
    load_tree: bool = False,
) -> List["MediaItem"]:
    """
    Fetch a list of MediaItems by their IDs using one round trip.

    - Preserves the input order at the SQL layer via CASE(..) ORDER BY.
    - Optionally eager-load Show -> seasons -> episodes using select-in if load_tree=True.
    - Calls .unique() to collapse duplicates that arise from joined eager loads.
    - Returns detached instances (expunged) to avoid lazy-loads on closed sessions.
    """
    if not ids:
        return []

    from program.media.item import MediaItem, Season, Show

    pos = {v: i for i, v in enumerate(ids)}
    order_clause = case(pos, value=MediaItem.id, else_=len(ids))
    id_param = bindparam("item_ids", expanding=True)

    stmt = select(MediaItem).where(MediaItem.id.in_(id_param)).order_by(order_clause)
    if load_tree:
        stmt = stmt.options(selectinload(Show.seasons).selectinload(Season.episodes))
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
        result = _s.execute(
            stmt.execution_options(stream_results=True),
            {"item_ids": list(ids)},
        ).unique()
        rows: List["MediaItem"] = [obj for obj in result.scalars().yield_per(500)]
        for obj in rows:
            if object_session(obj) is _s:
                _s.expunge(obj)
        by_id: Dict[int, "MediaItem"] = {m.id: m for m in rows}
        return [by_id[i] for i in ids if i in by_id]
    finally:
        if close_me:
            _s.close()

def get_item_by_external_id(
    imdb_id: Optional[str] = None,
    tvdb_id: Optional[str] = None,
    tmdb_id: Optional[str] = None,
    session: Optional[Session] = None,
) -> "MediaItem" | None:
    """
    Get a movie/show by any external ID (IMDb/TVDB/TMDB).
    Loads seasons/episodes for shows via selectinload.
    """
    from program.media.item import MediaItem, Season, Show

    conditions: List[Any] = []
    if imdb_id:
        conditions.append(MediaItem.imdb_id == imdb_id)
    if tvdb_id:
        conditions.append(MediaItem.tvdb_id == tvdb_id)
    if tmdb_id:
        conditions.append(MediaItem.tmdb_id == tmdb_id)

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
    item_id: Optional[int] = None,
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
        clauses.append(MediaItem.id == item_id)
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
        result = _s.execute(
            select(MediaItem).where(MediaItem.symlink_path == filepath).execution_options(stream_results=True)
        ).unique()
        items: List["MediaItem"] = [obj for obj in result.scalars().yield_per(500)]
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
            result = _s.execute(
                select(Episode)
                .options(selectinload(Episode.parent).selectinload(Season.parent))
                .where(
                    Episode.parent.has(Season.parent.has(Show.tvdb_id == tvdb_id)),
                    Episode.parent.has(Season.number == season_number),
                    Episode.number == episode_number,
                ).execution_options(stream_results=True)
            )
            rows = [r for r in result.scalars().yield_per(200)]
            for r in rows:
                _s.expunge(r)
            return rows

        result = _s.execute(select(Movie).where(Movie.tmdb_id == tmdb_id).execution_options(stream_results=True))
        rows = [r for r in result.scalars().yield_per(200)]
        for r in rows:
            _s.expunge(r)
        return rows

def clear_streams(
    *,
    media_item_id: int,
    session: Optional[Session] = None,
) -> None:
    """
    Remove ALL stream relations and blacklists for a media item in one transaction.
    """
    with _maybe_session(session) as (_s, _owns):
        _s.execute(delete(StreamRelation).where(StreamRelation.parent_id == media_item_id))
        _s.execute(delete(StreamBlacklistRelation).where(StreamBlacklistRelation.media_item_id == media_item_id))
        _s.commit()


def set_stream_blacklisted(
    item: "MediaItem",
    stream: Stream,
    *,
    blacklisted: bool,
    session: Optional[Session] = None,
) -> bool:
    """
    Toggle blacklist state for a (item, stream) pair atomically.
    Returns True if a change was applied.
    """
    with _maybe_session(session) as (_s, _owns):
        m_item = _s.merge(item)

        if blacklisted:
            # If the stream is currently linked, remove the link and add a blacklist row.
            linked = _s.query(
                _s.query(StreamRelation)
                .filter(
                    StreamRelation.parent_id == m_item.id,
                    StreamRelation.child_id == stream.id,
                )
                .exists()
            ).scalar()

            if not linked:
                return False

            _s.execute(
                delete(StreamRelation).where(
                    StreamRelation.parent_id == m_item.id,
                    StreamRelation.child_id == stream.id,
                )
            )
            _s.execute(
                insert(StreamBlacklistRelation).values(
                    media_item_id=m_item.id, stream_id=stream.id
                )
            )

        else:
            # If the stream is blacklisted, remove blacklist and restore link.
            bl = _s.query(
                _s.query(StreamBlacklistRelation)
                .filter(
                    StreamBlacklistRelation.media_item_id == m_item.id,
                    StreamBlacklistRelation.stream_id == stream.id,
                )
                .exists()
            ).scalar()

            if not bl:
                return False

            _s.execute(
                delete(StreamBlacklistRelation).where(
                    StreamBlacklistRelation.media_item_id == m_item.id,
                    StreamBlacklistRelation.stream_id == stream.id,
                )
            )
            _s.execute(
                insert(StreamRelation).values(parent_id=m_item.id, child_id=stream.id)
            )

        m_item.store_state()
        _s.commit()
        return True

def delete_media_item_by_id(media_item_id: int) -> bool:
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
    from sqlalchemy.exc import IntegrityError

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


def get_item_ids(session: Session, item_id: int) -> Tuple[int, List[int]]:
    """
    Return (root_id, related_ids) where related_ids are all children under the root,
    depending on the root type. Uses set-based selects.
    """
    from program.media.item import Episode, MediaItem, Season

    item_type = session.execute(
        select(MediaItem.type).where(MediaItem.id == item_id)
    ).scalar_one_or_none()

    related_ids: List[int] = []
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


# --------------------------------------------------------------------------- #
# State-Machine Adjacent Helpers
# --------------------------------------------------------------------------- #

def retry_library(session: Optional[Session] = None) -> List[int]:
    """
    Return IDs of items that should be retried. Single query, no pre-count.
    """
    from program.media.item import MediaItem

    with _maybe_session(session) as (s, owns):
        ids = s.execute(
            select(MediaItem.id)
            .where(
                MediaItem.last_state.not_in(
                    [States.Completed, States.Unreleased, States.Paused, States.Failed]
                )
            )
            .where(MediaItem.type.in_(["movie", "show"]))
            .order_by(MediaItem.requested_at.desc())
        ).scalars().all()
        return ids


def update_ongoing(session: Optional[Session] = None) -> List[int]:
    """
    Update state for ongoing/unreleased items with one commit.
    Calls store_state() per item (state machine), aggregates changed IDs.
    """
    from program.media.item import MediaItem

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

        changed: List[int] = []
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


@inject
def update_new_releases(session: Optional[Session] = None, update_type: str = "episodes", hours: int = 24) -> List[int]:
    """
    Get new releases for a given type and since timestamp.

    Args:
        session: Optional database session
        update_type: Type of updates to get (episodes, series, etc.)
        hours: Number of hours to look back for updates
        
    Returns:
        List of show TVDB IDs that have new episodes
    """
    from program.media.item import Episode, MediaItem, Season, Show

    tvdb_api = di[TVDBApi]
    ids_to_update = []
    series_episodes: List[Tuple[str, str]] = tvdb_api.get_new_releases(update_type, hours)
    series_ids = [str(series_id) for series_id, _ in series_episodes]

    with _maybe_session(session) as (s, owns):
        # Get only the series IDs that have new releases and exist in our database
        existing_series_ids = s.execute(
            select(MediaItem.tvdb_id)
            .where(MediaItem.type == "show")
            .where(MediaItem.tvdb_id.is_not(None))
            .where(MediaItem.tvdb_id.in_(series_ids))
        ).scalars().all()
        
        # Filter series_episodes to only include series we have in our database
        relevant_series_episodes = [
            (series_id, episode_id) for series_id, episode_id in series_episodes
            if series_id in existing_series_ids
        ]

        if not relevant_series_episodes:
            return ids_to_update

        # Get all existing episodes for the relevant series in one query
        from sqlalchemy.orm import aliased, selectinload
        season_alias = aliased(Season, flat=True)
        episode_alias = aliased(Episode, flat=True)
        
        existing_episodes_query = s.execute(
            select(Show.tvdb_id, episode_alias.number)
            .join(season_alias, Show.id == season_alias.parent_id)
            .join(episode_alias, season_alias.id == episode_alias.parent_id)
            .where(Show.tvdb_id.in_(series_ids))
        ).all()
        
        # Create a set of existing (series_id, episode_number) pairs for fast lookup
        existing_episodes = {(row[0], str(row[1])) for row in existing_episodes_query}
        
        # Check which episodes are missing and collect unique series IDs
        missing_series_ids = set()
        for series_id, episode_id in relevant_series_episodes:
            if (series_id, episode_id) not in existing_episodes:
                missing_series_ids.add(series_id)
        
        ids_to_update = list(missing_series_ids)

        ids_updated = []
        for id in ids_to_update:
            # Load item directly from session with relationships to avoid detached object issues
            item = s.execute(
                select(MediaItem)
                .options(selectinload(Show.seasons).selectinload(Season.episodes))
                .where(MediaItem.tvdb_id == id)
                .where(MediaItem.type == "show")
            ).unique().scalar_one_or_none()

            if item:
                try:
                    previous_state, new_state = item.store_state(States.Requested)
                    if previous_state != new_state:
                        ids_updated.append(item.id)
                except Exception as e:
                    logger.error(f"Failed to update state for item with ID {item.id}: {e}")

        if ids_updated:
            s.commit()

        return ids_updated


def create_calendar(session: Optional[Session] = None) -> Dict[str, Dict[str, Any]]:
    """
    Create a calendar of all upcoming/ongoing items in the library.
    Returns a dict keyed by item.id with minimal metadata for scheduling.
    """
    from program.media.item import MediaItem, Season, Show

    session = session if session else db.Session()

    result = session.execute(
        select(MediaItem)
        .options(selectinload(Show.seasons).selectinload(Season.episodes))
        .where(MediaItem.type.in_(["movie", "episode"]))
        .where(MediaItem.last_state != States.Completed)
        .where(MediaItem.aired_at.is_not(None))
        .where(MediaItem.aired_at >= datetime.now() - timedelta(days=1))
        .execution_options(stream_results=True)
    ).unique()

    calendar: Dict[str, Dict[str, Any]] = {}
    for item in result.scalars().yield_per(500):
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


def run_thread_with_db_item(fn, service, program, event: Event, cancellation_event: Event) -> Optional[str]:
    """
    Run a worker function `fn` against an existing or soon-to-exist MediaItem.
    Supports both:
      - event.item_id path: load + process item, update parent state if needed
      - event.content_item path: index new item (idempotent via item_exists_by_any_id)
      - generator path (no event): emit items into the program.em queue
    """
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
                            res = (item.id, run_at)
                        else:
                            item = res
                            res = item.id

                        if not isinstance(item, MediaItem):
                            logger.log(
                                "PROGRAM",
                                f"Service {service.__name__} emitted {item} from input item {input_item} of type {type(item).__name__}, backing off.",
                            )
                            program.em.remove_id_from_queues(input_item.id)

                        if not cancellation_event.is_set():
                            # Update parent item based on type
                            if input_item.type == "episode":
                                input_item.parent.parent.store_state()
                            elif input_item.type == "season":
                                input_item.parent.store_state()
                            else:
                                item.store_state()
                            session.commit()
                        return res

            if event.content_item:
                indexed_item = next(fn(event.content_item), None)
                if indexed_item is None:
                    msg = (
                        event.content_item.log_string
                        if getattr(event.content_item, "log_string", None) is not None
                        else event.content_item.imdb_id
                    )
                    logger.debug(f"Unable to index {msg}")
                    return None

                # Idempotent insert: skip if any known ID already exists
                if item_exists_by_any_id(
                    indexed_item.id, indexed_item.tvdb_id, indexed_item.tmdb_id, indexed_item.imdb_id, session
                ):
                    logger.debug(f"Item with ID {indexed_item.id} already exists, skipping save")
                    return indexed_item.id

                indexed_item.store_state()
                session.add(indexed_item)
                if not cancellation_event.is_set():
                    try:
                        session.commit()
                    except IntegrityError as e:
                        if "duplicate key value violates unique constraint" in str(e):
                            logger.debug(f"Item with ID {event.item_id} was added by another process, skipping")
                            session.rollback()
                            return None
                        raise
                return indexed_item.id
    else:
        # Content services dont pass events
        for i in fn():
            if isinstance(i, MediaItem):
                i = [i]
            if isinstance(i, list):
                for item in i:
                    if isinstance(item, MediaItem):
                        program.em.add_item(item, service)
    return None

def _purge_orphan_streams_tx(session: Session) -> int:
    """
    Delete Stream rows that have no parent references in either association table.
    Must be called *inside* a transaction after cascades have removed association rows.

    Returns:
        int: number of Stream rows deleted.
    """
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
                connection.execute(
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
                connection.execute(text("DROP SCHEMA public CASCADE"))
                connection.execute(text("CREATE SCHEMA public"))
                connection.execute(text("GRANT ALL ON SCHEMA public TO public"))
                logger.log("DATABASE", "Schema reset complete")

            # For SQLite, drop all tables
            elif db.engine.name == "sqlite":
                connection.execute(text("PRAGMA foreign_keys = OFF"))

                tables = connection.execute(
                    text("SELECT name FROM sqlite_master WHERE type='table'")
                ).scalars().all()

                for table in tables:
                    connection.execute(text(f"DROP TABLE IF EXISTS {table}"))

                connection.execute(text("PRAGMA foreign_keys = ON"))
                logger.log("DATABASE", "All tables dropped")

            # Recreate all tables
            db.Model.metadata.create_all(connection)
            logger.log("DATABASE", "All tables recreated")

            # If we had a previous version, restore it
            if current_version:
                connection.execute(
                    text(
                        "CREATE TABLE IF NOT EXISTS alembic_version (version_num VARCHAR(32) NOT NULL)"
                    )
                )
                connection.execute(
                    text("INSERT INTO alembic_version (version_num) VALUES (:version)"),
                    {"version": current_version},
                )
                logger.log("DATABASE", f"Restored alembic version to: {current_version}")
            else:
                # Stamp with head version if no previous version
                from program.utils import root_dir
                alembic_cfg = alembic.config.Config(root_dir / "src" / "alembic.ini")
                alembic.command.stamp(alembic_cfg, "head")
                logger.log("DATABASE", "Database stamped with head revision")

        except Exception as e:
            logger.error(f"Error during database reset: {str(e)}")
            raise

    logger.log("DATABASE", "Hard Reset Complete")

    # Verify database state
    try:
        with db.engine.connect() as connection:
            inspector = inspect(db.engine)
            all_tables = inspector.get_table_names()
            logger.log("DATABASE", f"Verified tables: {', '.join(all_tables)}")

            result = connection.execute(text("SELECT version_num FROM alembic_version"))
            version = result.scalar()
            logger.log("DATABASE", f"Verified alembic version: {version}")

    except Exception as e:
        logger.error(f"Error verifying database state: {str(e)}")
        raise

# Hard Reset Database
reset = os.getenv("HARD_RESET", None)
if reset is not None and reset.lower() in ["true","1"]:
    hard_reset_database()
    exit(0)

