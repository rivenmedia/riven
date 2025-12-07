from __future__ import annotations

import threading
import os

from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from program.utils.logging import logger
from sqlalchemy import delete, func, inspect, or_, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from program.media.state import States
from program.media.stream import StreamBlacklistRelation, StreamRelation
from program.core.runner import MediaItemGenerator
from program.db.base_model import get_base_metadata

from .db import db, db_session

if TYPE_CHECKING:
    from program.types import Service
    from program.program import Program
    from program.types import Event
    from program.media.item import MediaItem


@contextmanager
def _maybe_session(session: Session | None) -> Iterator[tuple[Session, bool]]:
    """
    Yield a (session, owns_session) pair.

    If `session` is None, create a new db.Session() and close it on exit.
    Otherwise, yield the caller-provided session and do not close it.
    """

    if session:
        yield session, False
        return

    with db_session() as s:
        yield s, True


def get_item_by_id(
    item_id: int,
    item_types: list[str] | None = None,
    session: Session | None = None,
) -> "MediaItem | None":
    """
    Retrieve a MediaItem by its database ID.

    Parameters:
        item_id (int): The numeric primary key of the MediaItem to retrieve.
        item_types (list[str] | None): If provided, restricts the lookup to items whose `type` is one of these values (e.g., "movie", "show").
        session (Session | None): Database session to use; if omitted, a new session will be created for the query.

    Returns:
        MediaItem | None: The matching MediaItem detached from the session, or `None` if no matching item exists.
    """

    from program.media.item import MediaItem

    with _maybe_session(session) as (_s, _):
        query = select(MediaItem).where(MediaItem.id == item_id)

        if item_types:
            query = query.where(MediaItem.type.in_(item_types))

        item = _s.execute(query).unique().scalar_one_or_none()

        if item:
            _s.expunge(item)

        return item


def get_item_by_external_id(
    imdb_id: str | None = None,
    tvdb_id: str | None = None,
    tmdb_id: str | None = None,
    session: Session | None = None,
) -> "MediaItem | None":
    """
    Retrieve a movie or show by one of its external identifiers.

    If a matching show is returned, its seasons and episodes are also loaded. At least one of `imdb_id`, `tvdb_id`, or `tmdb_id` must be provided.

    Parameters:
        imdb_id (str | None): IMDb identifier to match.
        tvdb_id (str | None): TVDB identifier to match.
        tmdb_id (str | None): TMDB identifier to match.

    Returns:
        MediaItem: The matched movie or show, or `None` if no match is found.

    Raises:
        ValueError: If none of `imdb_id`, `tvdb_id`, or `tmdb_id` are provided.
    """
    from program.media.item import MediaItem, Season, Show

    conditions = list[Any]()

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
    item_id: int | None = None,
    tvdb_id: str | None = None,
    tmdb_id: str | None = None,
    imdb_id: str | None = None,
    session: Session | None = None,
) -> bool:
    """
    Check whether any provided identifier corresponds to an existing MediaItem.

    At least one of `item_id`, `tvdb_id`, `tmdb_id`, or `imdb_id` must be supplied; otherwise a ValueError is raised.

    Returns:
        `true` if at least one matching MediaItem exists, `false` otherwise.

    Raises:
        ValueError: If no identifier is provided.
    """

    from program.media.item import MediaItem

    if not any([item_id, tvdb_id, tmdb_id, imdb_id]):
        raise ValueError("At least one ID must be provided")

    clauses = list[Any]()

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


def clear_streams(
    *,
    media_item_id: int,
    session: Session | None = None,
) -> None:
    """
    Remove all stream relations and blacklist entries for a media item in a single transaction.

    Parameters:
        media_item_id (int): ID of the media item whose stream relations and blacklist entries will be removed.
    """

    with _maybe_session(session) as (_s, _owns):
        _s.execute(
            delete(StreamRelation).where(StreamRelation.parent_id == media_item_id)
        )
        _s.execute(
            delete(StreamBlacklistRelation).where(
                StreamBlacklistRelation.media_item_id == media_item_id
            )
        )
        _s.commit()


def get_item_ids(session: Session, item_id: int) -> tuple[int, list[int]]:
    """
    Return the root media item ID and a list of its descendant item IDs.

    For a show, `related_ids` contains season IDs followed by episode IDs for those seasons.
    For a season, `related_ids` contains episode IDs for that season.
    For other item types, `related_ids` is an empty list.

    Returns:
        tuple: `(root_id, related_ids)` where `related_ids` is a list of descendant media item IDs.
    """

    from program.media.item import Episode, MediaItem, Season

    item_type = session.execute(
        select(MediaItem.type).where(MediaItem.id == item_id)
    ).scalar_one_or_none()

    related_ids = list[int]()

    if item_type == "show":
        season_ids = (
            session.execute(select(Season.id).where(Season.parent_id == item_id))
            .scalars()
            .all()
        )

        if season_ids:
            episode_ids = (
                session.execute(
                    select(Episode.id).where(Episode.parent_id.in_(season_ids))
                )
                .scalars()
                .all()
            )

            related_ids.extend(episode_ids)

        related_ids.extend(season_ids)
    elif item_type == "season":
        episode_ids = (
            session.execute(select(Episode.id).where(Episode.parent_id == item_id))
            .scalars()
            .all()
        )
        related_ids.extend(episode_ids)

    return item_id, related_ids


# --------------------------------------------------------------------------- #
# State-Machine Adjacent Helpers
# --------------------------------------------------------------------------- #


def retry_library(session: Session | None = None) -> Sequence[int]:
    """
    Return IDs of items that should be retried. Single query, no pre-count.
    """

    from program.media.item import MediaItem

    with _maybe_session(session) as (s, _owns):
        ids = (
            s.execute(
                select(MediaItem.id)
                .where(
                    MediaItem.last_state.not_in(
                        [
                            States.Completed,
                            States.Unreleased,
                            States.Paused,
                            States.Failed,
                        ]
                    )
                )
                .where(MediaItem.type.in_(["movie", "show"]))
                .order_by(MediaItem.requested_at.desc())
            )
            .scalars()
            .all()
        )

        return ids


def create_calendar(session: Session | None = None) -> dict[int, dict[str, Any]]:
    """
    Create a calendar of all upcoming/ongoing items in the library.
    Returns a dict keyed by item.id with minimal metadata for scheduling.
    """

    from program.media.item import MediaItem, Season, Show, Episode

    with _maybe_session(session) as (s, _owns):
        result = s.execute(
            select(MediaItem)
            .options(selectinload(Show.seasons).selectinload(Season.episodes))
            .where(MediaItem.aired_at.is_not(None))
            .where(MediaItem.aired_at >= datetime.now() - timedelta(days=30))
            .execution_options(stream_results=True)
        ).unique()

    calendar = dict[int, dict[str, Any]]()

    for item in result.scalars().yield_per(500):
        title = item.top_title
        calendar[item.id] = {
            "item_id": item.id,
            "tvdb_id": item.tvdb_id,
            "tmdb_id": item.tmdb_id,
            "show_title": title,
            "item_type": item.type,
            "aired_at": item.aired_at,
            "last_state": item.last_state,
        }

        if isinstance(item, Show):
            calendar[item.id]["release_data"] = item.release_data

        if isinstance(item, Season):
            calendar[item.id]["season"] = item.number

        if isinstance(item, Episode):
            calendar[item.id]["season"] = item.parent.number
            calendar[item.id]["episode"] = item.number

    return calendar


def run_thread_with_db_item(
    fn: Callable[..., MediaItemGenerator],
    service: "Service",
    program: "Program",
    event: Event | None,
    cancellation_event: threading.Event,
) -> int | tuple[int, datetime] | None:
    """
    Run a worker function against a database-backed MediaItem or enqueue items produced by a content service.

    Depending on the provided event, this function executes one of three flows:
    - event.item_id: load the existing MediaItem, pass it into `fn`, and if `fn` produces an item update related parent/item state and commit the session (unless cancelled).
    - event.content_item: index a new item produced by `fn` and perform an idempotent insert (skip if any known external ID already exists); handle race conditions that result in duplicate inserts.
    - no event: iterate over values yielded by `fn()` and enqueue produced MediaItem instances into program.em for later processing.

    Parameters:
        fn: A callable or generator used to process or produce MediaItem objects.
        service: The calling service (used for logging/queueing context).
        program: The program runtime which exposes the event manager/queue (program.em).
        event: An Event object that may contain `item_id` or `content_item`, selecting the processing path.
        cancellation_event: An Event used to short-circuit commits/updates if set.

    Returns:
        The produced item identifier as a string, a tuple `(item_id, run_at)` when the worker returned scheduling info, or `None` when no item was produced or processing was skipped.
    """

    from program.media.item import Episode, Season

    if event:
        with db_session() as session:
            if event.item_id:
                input_item = get_item_by_id(event.item_id, session=session)

                if input_item:
                    input_item = session.merge(input_item)
                    runner_result = next(fn(input_item), None)

                    if runner_result:
                        if len(runner_result.media_items) > 1:
                            logger.warning(
                                f"Service {service.__class__.__name__} emitted multiple items for input item {input_item}, only the first will be processed."
                            )

                        item = runner_result.media_items[0]
                        run_at = runner_result.run_at

                        if not cancellation_event.is_set():
                            # Update parent item based on type
                            if isinstance(input_item, Episode):
                                input_item.parent.parent.store_state()
                            elif isinstance(input_item, Season):
                                input_item.parent.store_state()
                            else:
                                item.store_state()

                            session.commit()

                        if run_at:
                            return (item.id, run_at)

                        return item.id

            if event.content_item:
                runner_result = next(fn(event.content_item), None)

                if runner_result is None:
                    msg = event.content_item.log_string or event.content_item.imdb_id

                    logger.debug(f"Unable to index {msg}")

                    return None

                if len(runner_result.media_items) > 1:
                    logger.warning(
                        f"Service {service.__class__.__name__} emitted multiple items for input item {event.content_item}, only the first will be processed."
                    )

                indexed_item = runner_result.media_items[0]

                # Idempotent insert: skip if any known ID already exists
                if item_exists_by_any_id(
                    item_id=indexed_item.id,
                    tvdb_id=indexed_item.tvdb_id,
                    tmdb_id=indexed_item.tmdb_id,
                    imdb_id=indexed_item.imdb_id,
                    session=session,
                ):
                    logger.debug(
                        f"Item with ID {indexed_item.id} already exists, skipping save"
                    )

                    return indexed_item.id

                indexed_item.store_state()

                session.add(indexed_item)

                if not cancellation_event.is_set():
                    try:
                        session.commit()
                    except IntegrityError as e:
                        if "duplicate key value violates unique constraint" in str(e):
                            logger.debug(
                                f"Item with ID {event.item_id} was added by another process, skipping"
                            )

                            session.rollback()

                            return None

                        raise

                return indexed_item.id
    else:
        # Content services dont pass events
        runner_result = next(fn(None), None)

        if runner_result:
            for item in runner_result.media_items:
                program.em.add_item(item, service=service.__class__.__name__)

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

                tables = (
                    connection.execute(
                        text("SELECT name FROM sqlite_master WHERE type='table'")
                    )
                    .scalars()
                    .all()
                )

                for table in tables:
                    connection.execute(text(f"DROP TABLE IF EXISTS {table}"))

                connection.execute(text("PRAGMA foreign_keys = ON"))
                logger.log("DATABASE", "All tables dropped")

            # Recreate all tables
            get_base_metadata().create_all(connection)

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
                logger.log(
                    "DATABASE", f"Restored alembic version to: {current_version}"
                )
            else:
                # Stamp with head version if no previous version
                from program.utils import root_dir
                import alembic.config
                import alembic.command

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

if reset is not None and reset.lower() in ["true", "1"]:
    hard_reset_database()
    exit(0)
