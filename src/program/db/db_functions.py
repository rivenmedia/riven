import os
import shutil
from typing import List, TYPE_CHECKING

import alembic

from program.media.stream import Stream, StreamRelation, StreamBlacklistRelation
from sqlalchemy import delete, func, select, text, union_all, exists, insert
from sqlalchemy.orm import joinedload, aliased, Session
from utils.logger import logger
from utils import alembic_dir
from program.libraries.symlink import fix_broken_symlinks
from program.settings.manager import settings_manager
from .db import db, alembic

if TYPE_CHECKING:
    from program.media.item import MediaItem

def get_media_items_by_ids(media_item_ids: list[int]):
    """Retrieve multiple MediaItems by a list of MediaItem _ids using the _get_item_from_db method."""
    from program.media.item import Movie, Show, Season, Episode, MediaItem
    items = []

    with db.Session() as session:
        for media_item_id in media_item_ids:
            item_type = session.execute(select(MediaItem.type).where(MediaItem._id==media_item_id)).scalar_one()
            if not item_type:
                continue
            item = None
            match item_type:
                case "movie":
                    item = session.execute(
                        select(Movie)
                        .where(MediaItem._id == media_item_id)
                    ).unique().scalar_one()
                case "show":
                    item = session.execute(
                        select(Show)
                        .where(MediaItem._id == media_item_id)
                        .options(joinedload(Show.seasons).joinedload(Season.episodes))
                    ).unique().scalar_one()
                case "season":
                    item = session.execute(
                        select(Season)
                        .where(Season._id == media_item_id)
                        .options(joinedload(Season.episodes))
                    ).unique().scalar_one()
                case "episode":
                    item = session.execute(
                        select(Episode)
                        .where(Episode._id == media_item_id)
                    ).unique().scalar_one()
            if item:
                items.append(item)

    return items

def delete_media_item(item: "MediaItem"):
    """Delete a MediaItem and all its associated relationships."""
    with db.Session() as session:
        item = session.merge(item)
        session.delete(item)
        session.commit()

def delete_media_item_by_id(media_item_id: int):
    """Delete a MediaItem and all its associated relationships by the MediaItem _id."""
    from program.media.item import MediaItem
    with db.Session() as session:
        item = session.query(MediaItem).filter_by(_id=media_item_id).first()

        if item:
            session.delete(item)
            session.commit()
        else:
            raise ValueError(f"MediaItem with id {media_item_id} does not exist.")

def delete_media_item_by_item_id(item_id: str):
    """Delete a MediaItem and all its associated relationships by the MediaItem _id."""
    from program.media.item import MediaItem
    with db.Session() as session:
        item = session.query(MediaItem).filter_by(item_id=item_id).first()

        if item:
            session.delete(item)
            session.commit()
        else:
            raise ValueError(f"MediaItem with item_id {item_id} does not exist.")

def delete_media_items_by_ids(media_item_ids: list[int]):
    """Delete multiple MediaItems and all their associated relationships by a list of MediaItem _ids."""
    try:
        for media_item_id in media_item_ids:
            delete_media_item_by_id(media_item_id)
    except Exception as e:
        error = f"Failed to delete media items: {e}"
        logger.error(error)
        raise ValueError(error)

def reset_streams(item: "MediaItem", active_stream_hash: str = None):
    """Reset streams associated with a MediaItem."""
    with db.Session() as session:
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
        item.active_stream = None
        session.commit()
        session.refresh(item)

def blacklist_stream(item: "MediaItem", stream: Stream, session: Session = None) -> bool:
    """Blacklist a stream for a media item."""
    close_session = False
    if session is None:
        session = db.Session()
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

            session.commit()
            session.refresh(item)
            return True
        return False
    # except Exception as e:
    #     if close_session:
    #         session.rollback()
    #     logger.log("DATABASE", f"Failed to blacklist stream {stream.infohash} for {item.log_string}: {e}")
    #     raise e
    finally:
        if close_session:
            session.close()

def filter_existing_streams(media_item_id: int, scraped_streams: List[Stream]) -> List[Stream]:
    from program.media.item import MediaItem
    """Return streams that are not already associated with the media item."""
    scraped_hashes = [stream.infohash for stream in scraped_streams]

    with db.Session() as session:
        existing_streams = session.execute(
            select(Stream.infohash)
            .join(Stream.parents)
            .where(MediaItem._id == media_item_id)
            .where(Stream.infohash.in_(scraped_hashes))
        ).scalars().all()
        existing_hashes = set(existing_streams)
        new_streams = [stream for stream in scraped_streams if stream.infohash not in existing_hashes]
        return new_streams

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

def _get_item_ids(session, item):
    from program.media.item import Season, Episode
    if item.type == "show":
        show_id = item._id

        season_alias = aliased(Season, flat=True)
        season_query = select(Season._id.label('id')).where(Season.parent_id == show_id)
        episode_query = (
            select(Episode._id.label('id'))
            .join(season_alias, Episode.parent_id == season_alias._id)
            .where(season_alias.parent_id == show_id)
        )

        combined_query = union_all(season_query, episode_query)
        related_ids = session.execute(combined_query).scalars().all()
        return show_id, related_ids

    elif item.type == "season":
        season_id = item._id
        episode_ids = session.execute(
            select(Episode._id)
            .where(Episode.parent_id == season_id)
        ).scalars().all()
        return season_id, episode_ids

    elif hasattr(item, "parent"):
        parent_id = item.parent._id
        return parent_id, []

    return item._id, []

def _ensure_item_exists_in_db(item: "MediaItem") -> bool:
    from program.media.item import MediaItem, Movie, Show
    if isinstance(item, (Movie, Show)):
        with db.Session() as session:
            if item._id is None:
                return session.execute(select(func.count(MediaItem._id)).where(MediaItem.imdb_id == item.imdb_id)).scalar_one() != 0
            return session.execute(select(func.count(MediaItem._id)).where(MediaItem._id == item._id)).scalar_one() != 0
    return bool(item and item._id)

def _get_item_type_from_db(item: "MediaItem") -> str:
    from program.media.item import MediaItem
    with db.Session() as session:
        if item._id is None:
            return session.execute(select(MediaItem.type).where((MediaItem.imdb_id==item.imdb_id) & (MediaItem.type.in_(["show", "movie"])))).scalar_one()
        return session.execute(select(MediaItem.type).where(MediaItem._id==item._id)).scalar_one()

def _store_item(item: "MediaItem"):
    from program.media.item import Movie, Show, Season, Episode
    if isinstance(item, (Movie, Show, Season, Episode)) and item._id is not None:
        with db.Session() as session:
            session.merge(item)
            session.commit()
            logger.log("DATABASE", f"{item.log_string} Updated!")
    else:
        with db.Session() as session:
            _check_for_and_run_insertion_required(session, item)

def _get_item_from_db(session, item: "MediaItem"):
    from program.media.item import MediaItem, Movie, Show, Season, Episode
    if not _ensure_item_exists_in_db(item):
        return None
    session.expire_on_commit = False
    type = _get_item_type_from_db(item)
    match type:
        case "movie":
            r = session.execute(
                select(Movie)
                .where(MediaItem.imdb_id == item.imdb_id)
            ).unique().scalar_one()
            return r
        case "show":
            r = session.execute(
                select(Show)
                .where(MediaItem.imdb_id == item.imdb_id)
                .options(joinedload(Show.seasons).joinedload(Season.episodes))
            ).unique().scalar_one()
            return r
        case "season":
            r = session.execute(
                select(Season)
                .where(Season._id == item._id)
                .options(joinedload(Season.episodes))
            ).unique().scalar_one()
            return r
        case "episode":
            r = session.execute(
                select(Episode)
                .where(Episode._id == item._id)
            ).unique().scalar_one()
            return r
        case _:
            logger.error(f"_get_item_from_db Failed to create item from type: {type}")
            return None

def _check_for_and_run_insertion_required(session, item: "MediaItem") -> bool:
    from program.media.item import Movie, Show, Season, Episode
    if not _ensure_item_exists_in_db(item) and isinstance(item, (Show, Movie, Season, Episode)):
            item.store_state()
            session.add(item)
            session.commit()
            logger.log("DATABASE", f"{item.log_string} Inserted into the database.")
            return True
    return False

def _run_thread_with_db_item(fn, service, program, input_item: "MediaItem" = None):
    from program.media.item import MediaItem, Movie, Show, Season, Episode
    if input_item is not None:
        with db.Session() as session:
            if isinstance(input_item, (Movie, Show, Season, Episode)):
                if not _check_for_and_run_insertion_required(session, input_item):
                    pass
                input_item = _get_item_from_db(session, input_item)

                for res in fn(input_item):
                    if not isinstance(res, MediaItem):
                        logger.log("PROGRAM", f"Service {service.__name__} emitted {res} from input item {input_item} of type {type(res).__name__}, backing off.")
                        program.em.remove_item_from_running(input_item)

                    input_item.store_state()
                    session.commit()

                    session.expunge_all()
                    yield res
            else:
                #Content services
                for i in fn(input_item):
                    if isinstance(i, (MediaItem)):
                        with db.Session() as session:
                            _check_for_and_run_insertion_required(session, i)                            
                    yield i
        return
    else:
        for i in fn():
            if isinstance(i, (MediaItem)):
                with db.Session() as session:
                    _check_for_and_run_insertion_required(session, i)
                yield i
        return

def hard_reset_database():
    """Resets the database to a fresh state."""
    logger.log("DATABASE", "Resetting Database")
    
    # Drop all tables
    db.Model.metadata.drop_all(db.engine)
    logger.log("DATABASE","All MediaItem tables dropped")
    
    # Drop the alembic_version table
    with db.engine.connect() as connection:
        connection.execute(text("DROP TABLE IF EXISTS alembic_version CASCADE"))
    logger.log("DATABASE","Alembic table dropped")
    
    # Recreate all tables
    db.Model.metadata.create_all(db.engine)
    logger.log("DATABASE","All tables recreated")
    
    # Reinitialize Alembic
    logger.log("DATABASE","Removing Alembic Directory")
    shutil.rmtree(alembic_dir, ignore_errors=True)
    os.makedirs(alembic_dir, exist_ok=True)
    alembic.init(alembic_dir)
    logger.log("DATABASE","Alembic reinitialized")

    logger.log("DATABASE","Hard Reset Complete")

reset = os.getenv("HARD_RESET", None)
if reset is not None and reset.lower() in ["true","1"]:
    hard_reset_database()

if os.getenv("REPAIR_SYMLINKS", None) is not None and os.getenv("REPAIR_SYMLINKS").lower() in ["true","1"]:
    fix_broken_symlinks(settings_manager.settings.symlink.library_path, settings_manager.settings.symlink.rclone_path)
    exit(0)