import os
import shutil
from threading import Event
from typing import TYPE_CHECKING

import alembic
from sqlalchemy import delete, func, insert, select, text, desc
from sqlalchemy.orm import Session, selectinload
from sqlalchemy.exc import SQLAlchemyError

from program.services.libraries.symlink import fix_broken_symlinks
from program.media.stream import Stream, StreamBlacklistRelation, StreamRelation
from program.settings.manager import settings_manager
from program.utils import alembic_dir
from loguru import logger

from .db import alembic, db

if TYPE_CHECKING:
    from program.media.item import MediaItem

def get_item_by_id(id: str, item_types = None, session = None):
    if not id:
        return None

    from program.media.item import MediaItem, Season, Show
    _session = session if session else db.Session()

    with _session:
        query = (select(MediaItem)
            .where(MediaItem.id == id)
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

def get_items_by_ids(ids: list, item_types = None, session = None):
    items = []
    for id in ids:
        items.append(get_item_by_id(id, item_types,  session))
    return items

def get_item_by_external_id(imdb_id: str = None, tvdb_id: int = None, tmdb_id: int = None, session = None):
    from program.media.item import MediaItem, Season, Show

    _session = session if session else db.Session()
    query = (select(MediaItem)
            .options(
                selectinload(Show.seasons)
                .selectinload(Season.episodes)
            ))

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
    """Delete a MediaItem and all its associated relationships."""
    with db.Session() as session:
        item = session.merge(item)
        session.delete(item)
        session.commit()

def delete_media_item_by_id(media_item_id: int, batch_size: int = 30):
    """Delete a Movie or Show by _id. If it's a Show, delete its Seasons and Episodes in batches, committing after each batch."""
    from program.media.item import MediaItem, Show, Movie, Season, Episode
    from sqlalchemy.exc import IntegrityError

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
            return True

        except IntegrityError as e:
            logger.error(f"Integrity error while deleting media item with ID {media_item_id}: {e}")
            session.rollback()
            return False
        except Exception as e:
            logger.error(f"Unexpected error while deleting media item with ID {media_item_id}: {e}")
            session.rollback()
            return False

def delete_seasons_and_episodes(session, season_ids: list[int], batch_size: int = 30):
    """Delete seasons and episodes of a show in batches, committing after each batch."""
    from program.media.item import Episode, Season
    from program.media.stream import StreamRelation, StreamBlacklistRelation
    from program.media.subtitle import Subtitle

    for season_id in season_ids:
        # Load the season object
        season = session.query(Season).get(season_id)

        # Bulk delete related streams and subtitles
        session.execute(delete(StreamRelation).where(StreamRelation.parent_id == season_id))
        session.execute(delete(StreamBlacklistRelation).where(StreamBlacklistRelation.media_item_id == season_id))
        session.execute(delete(Subtitle).where(Subtitle.parent_id == season_id))
        session.commit()  # Commit after bulk deletion

        # Delete episodes in batches for each season
        while True:
            episode_ids = session.execute(
                select(Episode.id).where(Episode.parent_id == season_id).limit(batch_size)
            ).scalars().all()

            if not episode_ids:
                break

            session.execute(delete(Episode).where(Episode.id.in_(episode_ids)))
            session.commit()  # Commit after each batch of episodes

        session.delete(season)  # Delete the season itself
        session.commit()  # Commit after deleting the season

def reset_media_item(item: "MediaItem"):
    """Reset a MediaItem."""
    with db.Session() as session:
        item = session.merge(item)
        item.reset()
        session.commit()

def reset_streams(item: "MediaItem"):
    """Reset streams associated with a MediaItem."""
    with db.Session() as session:

        session.execute(
            delete(StreamRelation).where(StreamRelation.parent_id == item.id)
        )

        session.execute(
            delete(StreamBlacklistRelation).where(StreamBlacklistRelation.media_item_id == item.id)
        )
        session.commit()

def clear_streams(item: "MediaItem"):
    """Clear all streams for a media item."""
    reset_streams(item)

def clear_streams_by_id(media_item_id: int):
    """Clear all streams for a media item by the MediaItem id."""
    with db.Session() as session:
        session.execute(
            delete(StreamRelation).where(StreamRelation.parent_id == media_item_id)
        )
        session.execute(
            delete(StreamBlacklistRelation).where(StreamBlacklistRelation.media_item_id == media_item_id)
        )
        session.commit()

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

def get_item_ids(session, item_id: int) -> tuple[int, list[int]]:
    """Get the item ID and all related item IDs for a given MediaItem."""
    from program.media.item import MediaItem, Episode, Season

    item_type = session.query(MediaItem.type).filter(MediaItem.id == item_id).scalar()
    related_ids = []

    if item_type == "show":
        season_ids = session.execute(
            select(Season.id).where(Season.parent_id == item_id)
        ).scalars().all()

        for season_id in season_ids:
            episode_ids = session.execute(
                select(Episode.id).where(Episode.parent_id == season_id)
            ).scalars().all()
            related_ids.extend(episode_ids)
        related_ids.extend(season_ids)

    elif item_type == "season":
        episode_ids = session.execute(
            select(Episode.id).where(Episode.parent_id == item_id)
        ).scalars().all()
        related_ids.extend(episode_ids)

    return item_id, related_ids

def run_thread_with_db_item(fn, service, program, event: Event, cancellation_event: Event):
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
                    logger.debug(f"Unable to index {event.content_item.log_string}")
                    return
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
    return

def hard_reset_database():
    """Resets the database to a fresh state."""
    logger.log("DATABASE", "Starting Hard Reset of Database")

    # Disable foreign key checks temporarily
    with db.engine.connect() as connection:
        if db.engine.name == 'sqlite':
            connection.execute(text("PRAGMA foreign_keys = OFF"))
        elif db.engine.name == 'postgresql':
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
            if db.engine.name == 'sqlite':
                connection.execute(text("PRAGMA foreign_keys = ON"))
            elif db.engine.name == 'postgresql':
                connection.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))

            connection.commit()
        except Exception as e:
            connection.rollback()
            logger.log("DATABASE", f"Error during database reset: {str(e)}")
            raise

    try:
        logger.log("DATABASE", "Removing Alembic Directory")
        shutil.rmtree(alembic_dir, ignore_errors=True)
        os.makedirs(alembic_dir, exist_ok=True)
        alembic.init(alembic_dir)
        logger.log("DATABASE", "Alembic reinitialized")
    except Exception as e:
        logger.log("DATABASE", f"Error reinitializing Alembic: {str(e)}")

    logger.log("DATABASE", "Hard Reset Complete")

def resolve_duplicates(batch_size: int = 100):
    """Resolve duplicates in the database without loading all items into memory."""
    from program.media.item import MediaItem
    with db.Session() as session:
        try:
            # Find all duplicate ids
            duplicates = session.query(
                MediaItem.id,
                func.count(MediaItem.id).label("dupe_count")
            ).group_by(MediaItem.id).having(func.count(MediaItem.id) > 1)

            # Loop through the duplicates and resolve them in batches
            for id, _ in duplicates.yield_per(batch_size):
                offset = 0
                while True:
                    # Fetch a batch of duplicate items
                    duplicate_items = session.query(MediaItem.id)\
                        .filter(MediaItem.id == id)\
                        .order_by(desc(MediaItem.indexed_at))\
                        .offset(offset)\
                        .limit(batch_size)\
                        .all()

                    if not duplicate_items:
                        break

                    # Keep the first item (most recent) and delete the others
                    for item_id in [item.id for item in duplicate_items[1:]]:
                        try:
                            delete_media_item_by_id(item_id)
                            logger.debug(f"Deleted duplicate item with id {id} and ID {item_id}")
                        except Exception as e:
                            logger.error(f"Error deleting duplicate item with id {id} and ID {item_id}: {str(e)}")

                    session.commit()
                    offset += batch_size

            # Recreate the unique index
            session.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uix_id ON MediaItem (id)"))
            session.commit()

            logger.success("Duplicate entries resolved in batches successfully and unique index recreated.")

        except SQLAlchemyError as e:
            logger.error(f"Error resolving duplicates: {str(e)}")
            session.rollback()

        finally:
            session.close()


# Hard Reset Database
reset = os.getenv("HARD_RESET", None)
if reset is not None and reset.lower() in ["true","1"]:
    hard_reset_database()
    exit(0)

# Repair Symlinks
if os.getenv("REPAIR_SYMLINKS", None) is not None and os.getenv("REPAIR_SYMLINKS").lower() in ["true","1"]:
    fix_broken_symlinks(settings_manager.settings.symlink.library_path, settings_manager.settings.symlink.rclone_path)
    exit(0)

# Resolve Duplicates
if os.getenv("RESOLVE_DUPLICATES", None) is not None and os.getenv("RESOLVE_DUPLICATES").lower() in ["true","1"]:
    resolve_duplicates()
    exit(0)

