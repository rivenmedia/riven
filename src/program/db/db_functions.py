import os
import shutil
from typing import TYPE_CHECKING

import alembic
from sqlalchemy import delete, func, insert, select, text, desc
from sqlalchemy.orm import Session, selectinload
from sqlalchemy.exc import SQLAlchemyError

from program.libraries.symlink import fix_broken_symlinks
from program.media.stream import Stream, StreamBlacklistRelation, StreamRelation
from program.settings.manager import settings_manager
from utils import alembic_dir
from utils.logger import logger

from .db import alembic, db

if TYPE_CHECKING:
    from program.media.item import MediaItem


def get_media_items_by_ids(media_item_ids: list[int]):
    """Retrieve multiple MediaItems by a list of MediaItem _ids using the get_item_from_db method."""
    from program.media.item import Episode, MediaItem, Movie, Season, Show

    def get_item(session, media_item_id, item_type):
        match item_type:
            case "movie":
                return session.execute(
                    select(Movie)
                    .where(MediaItem._id == media_item_id)
                ).unique().scalar_one()
            case "show":
                return session.execute(
                    select(Show)
                    .where(MediaItem._id == media_item_id)
                    .options(selectinload(Show.seasons).selectinload(Season.episodes))
                ).unique().scalar_one()
            case "season":
                return session.execute(
                    select(Season)
                    .where(Season._id == media_item_id)
                    .options(selectinload(Season.episodes))
                ).unique().scalar_one()
            case "episode":
                return session.execute(
                    select(Episode)
                    .where(Episode._id == media_item_id)
                ).unique().scalar_one()
            case _:
                return None

    with db.Session() as session:
        for media_item_id in media_item_ids:
            item_type = session.execute(select(MediaItem.type).where(MediaItem._id == media_item_id)).scalar_one()
            if not item_type:
                continue
            item = get_item(session, media_item_id, item_type)
            if item:
                yield item

def get_parent_ids(media_item_ids: list[int]):
    """Retrieve the _ids of MediaItems of type 'movie' or 'show' by a list of MediaItem _ids."""
    from program.media.item import MediaItem
    with db.Session() as session:
        parent_ids = []
        for media_item_id in media_item_ids:
            item_id = session.execute(
                select(MediaItem._id)
                .where(MediaItem._id == media_item_id, MediaItem.type.in_(["movie", "show"]))
            ).scalar_one()
            if item_id:
                parent_ids.append(item_id)
    return parent_ids

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
                .where(MediaItem._id == media_item_id)
            ).scalar_one_or_none()

            if not media_item_type:
                logger.error(f"No item found with ID {media_item_id}")
                return False

            if media_item_type == "show":
                season_ids = session.execute(
                    select(Season._id).where(Season.parent_id == media_item_id)
                ).scalars().all()

                delete_seasons_and_episodes(session, season_ids, batch_size)
                session.execute(delete(Show).where(Show._id == media_item_id))

            if media_item_type == "movie":
                session.execute(delete(Movie).where(Movie._id == media_item_id))

            if media_item_type == "season":
                delete_seasons_and_episodes(session, [media_item_id], batch_size)
                session.execute(delete(Season).where(Season._id == media_item_id))

            if media_item_type == "episode":
                session.execute(delete(Episode).where(Episode._id == media_item_id))

            session.execute(delete(MediaItem).where(MediaItem._id == media_item_id))
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
                select(Episode._id).where(Episode.parent_id == season_id).limit(batch_size)
            ).scalars().all()

            if not episode_ids:
                break

            session.execute(delete(Episode).where(Episode._id.in_(episode_ids)))
            session.commit()  # Commit after each batch of episodes

        session.delete(season)  # Delete the season itself
        session.commit()  # Commit after deleting the season

def reset_media_item(item: "MediaItem"):
    """Reset a MediaItem."""
    with db.Session() as session:
        item = session.merge(item)
        item.reset()
        session.commit()

def reset_streams(item: "MediaItem", active_stream_hash: str = None):
    """Reset streams associated with a MediaItem."""
    with db.Session() as session:
        item.store_state()
        item = session.merge(item)
        if active_stream_hash:
            stream = session.query(Stream).filter(Stream.infohash == active_stream_hash).first()
            if stream:
                blacklist_stream(item, stream, session)

        session.execute(
            delete(StreamRelation).where(StreamRelation.parent_id == item._id)
        )

        session.execute(
            delete(StreamBlacklistRelation).where(StreamBlacklistRelation.media_item_id == item._id)
        )
        item.active_stream = {}
        session.commit()

def clear_streams(item: "MediaItem"):
    """Clear all streams for a media item."""
    with db.Session() as session:
        item = session.merge(item)
        session.execute(
            delete(StreamRelation).where(StreamRelation.parent_id == item._id)
        )
        session.execute(
            delete(StreamBlacklistRelation).where(StreamBlacklistRelation.media_item_id == item._id)
        )
        session.commit()

def clear_streams_by_id(media_item_id: int):
    """Clear all streams for a media item by the MediaItem _id."""
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
        item = session.execute(select(type(item)).where(type(item)._id == item._id)).unique().scalar_one()
        close_session = True

    try:
        item = session.merge(item)
        association_exists = session.query(
            session.query(StreamRelation)
            .filter(StreamRelation.parent_id == item._id)
            .filter(StreamRelation.child_id == stream._id)
            .exists()
        ).scalar()

        if association_exists:
            session.execute(
                delete(StreamRelation)
                .where(StreamRelation.parent_id == item._id)
                .where(StreamRelation.child_id == stream._id)
            )
            session.execute(
                insert(StreamBlacklistRelation)
                .values(media_item_id=item._id, stream_id=stream._id)
            )
            item.store_state()
            session.commit()
            return True
        return False
    finally:
        if close_session:
            session.close()

def get_stream_count(media_item_id: int) -> int:
    from program.media.item import MediaItem
    """Get the count of streams for a given MediaItem."""
    with db.Session() as session:
        return session.execute(
            select(func.count(Stream._id))
            .filter(Stream.parents.any(MediaItem._id == media_item_id))
        ).scalar_one()

def load_streams_in_pages(session: Session, media_item_id: int, page_number: int, page_size: int = 5):
    """Load a specific page of streams for a given MediaItem."""
    from program.media.item import MediaItem
    stream_query = session.query(Stream._id, Stream.infohash).filter(Stream.parents.any(MediaItem._id == media_item_id))
    stream_chunk = stream_query.limit(page_size).offset(page_number * page_size).all()

    for stream_id, infohash in stream_chunk:
        stream = session.query(Stream).get(stream_id)
        yield stream_id, infohash, stream

def get_item_ids(session, item_id: int) -> tuple[int, list[int]]:
    """Get the item ID and all related item IDs for a given MediaItem."""
    from program.media.item import MediaItem, Episode, Season

    item_type = session.query(MediaItem.type).filter(MediaItem._id == item_id).scalar()
    related_ids = []

    if item_type == "show":
        season_ids = session.execute(
            select(Season._id).where(Season.parent_id == item_id)
        ).scalars().all()

        for season_id in season_ids:
            episode_ids = session.execute(
                select(Episode._id).where(Episode.parent_id == season_id)
            ).scalars().all()
            related_ids.extend(episode_ids)
        related_ids.extend(season_ids)

    elif item_type == "season":
        episode_ids = session.execute(
            select(Episode._id).where(Episode.parent_id == item_id)
        ).scalars().all()
        related_ids.extend(episode_ids)

    return item_id, related_ids

def ensure_item_exists_in_db(item: "MediaItem") -> bool:
    """Ensure a MediaItem exists in the database."""
    from program.media.item import MediaItem
    with db.Session() as session:
        query = select(func.count(MediaItem._id)).where(
            (MediaItem._id == item._id) if item._id is not None else (MediaItem.imdb_id == item.imdb_id)
        ).where(MediaItem.type.in_(["movie", "show"]))
        return session.execute(query).scalar_one() != 0

def get_item_from_db(session: Session, item_id: int) -> "MediaItem":
    """Get a MediaItem from the database by _id."""
    from program.media.item import MediaItem, Movie, Show, Season, Episode

    item_type = session.execute(
        select(MediaItem.type).where(MediaItem._id == item_id)
    ).scalar_one_or_none()

    session.expire_on_commit = False
    match item_type:
        case "movie":
            return session.execute(
                select(Movie).where(Movie._id == item_id)
            ).unique().scalar_one_or_none()
        case "show":
            return session.execute(
                select(Show)
                .where(Show._id == item_id)
                .options(selectinload(Show.seasons).selectinload(Season.episodes))
            ).unique().scalar_one_or_none()
        case "season":
            return session.execute(
                select(Season)
                .where(Season._id == item_id)
                .options(selectinload(Season.episodes))
            ).unique().scalar_one_or_none()
        case "episode":
            return session.execute(
                select(Episode).where(Episode._id == item_id)
            ).unique().scalar_one_or_none()
        case "mediaitem":
            return session.execute(
                select(MediaItem).where(MediaItem._id == item_id)
            ).unique().scalar_one_or_none()
        case _:
            logger.error(f"Unknown item type for ID {item_id}")
            return None

def store_item(item: "MediaItem"):
    """Store a MediaItem in the database."""
    from program.media.item import MediaItem

    with db.Session() as session:
        try:
            item.store_state()
            session.add(item)
            logger.log("DATABASE", f"Inserted {item.log_string} into the database.")
            session.commit()
        except Exception as e:
            session.rollback()
            logger.error(f"Error during store_or_update_item: {e}")
        finally:
            session.close()

def run_thread_with_db_item(fn, service, program, input_id: int = None):
    from program.media.item import MediaItem
    if input_id:
        with db.Session() as session:
            input_item = get_item_from_db(session, input_id)
            if input_item.type in ["movie", "show", "season", "episode"]:
                # check if the item needs insertion
                if input_item._id is None:
                    pass
                for res in fn(input_item):
                    if isinstance(res, tuple):
                        item, run_at = res
                        res = item._id, run_at
                    else:
                        item = res
                        res = item._id
                    if not isinstance(item, MediaItem):
                        logger.log("PROGRAM", f"Service {service.__name__} emitted {item} from input item {input_item} of type {type(item).__name__}, backing off.")
                        program.em.remove_id_from_queues(input_item._id)

                    input_item.store_state()
                    session.commit()

                    session.expunge_all()
                    yield res
            else:
                # Indexing returns a copy of the item, was too lazy to create a copy attr func so this will do for now
                indexed_item = next(fn(input_item), None)
                if indexed_item is None:
                    pass
                if indexed_item.type != "mediaitem":
                    indexed_item.store_state()
                    session.delete(input_item)
                    indexed_item = session.merge(indexed_item)
                    session.commit()
                    logger.debug(f"{input_item._id} is now {indexed_item._id} after indexing...")
                    yield indexed_item._id
        return
    else:
        # Content services
        for i in fn():
            if isinstance(i, MediaItem):
                i = [i]
            if isinstance(i, list):
                for item in i:
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
            # Find all duplicate imdb_ids
            duplicates = session.query(
                MediaItem.imdb_id,
                func.count(MediaItem._id).label("dupe_count")
            ).group_by(MediaItem.imdb_id).having(func.count(MediaItem._id) > 1)

            # Loop through the duplicates and resolve them in batches
            for imdb_id, _ in duplicates.yield_per(batch_size):
                offset = 0
                while True:
                    # Fetch a batch of duplicate items
                    duplicate_items = session.query(MediaItem._id)\
                        .filter(MediaItem.imdb_id == imdb_id)\
                        .order_by(desc(MediaItem.indexed_at))\
                        .offset(offset)\
                        .limit(batch_size)\
                        .all()

                    if not duplicate_items:
                        break

                    # Keep the first item (most recent) and delete the others
                    for item_id in [item._id for item in duplicate_items[1:]]:
                        try:
                            delete_media_item_by_id(item_id)
                            logger.debug(f"Deleted duplicate item with imdb_id {imdb_id} and ID {item_id}")
                        except Exception as e:
                            logger.error(f"Error deleting duplicate item with imdb_id {imdb_id} and ID {item_id}: {str(e)}")

                    session.commit()
                    offset += batch_size

            # Recreate the unique index
            session.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uix_imdb_id ON MediaItem (imdb_id)"))
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

