import os
import shutil

import alembic

from program.media.item import Episode, MediaItem, Movie, Season, Show
from program.media.stream import Stream, StreamRelation
from program.types import Event
from sqlalchemy import delete, func, select, text
from sqlalchemy.orm import joinedload
from utils.logger import logger
from utils import alembic_dir
from program.libraries.symlink import fix_broken_symlinks
from program.settings.manager import settings_manager

from .db import db, alembic


def _ensure_item_exists_in_db(item: MediaItem) -> bool:
    if isinstance(item, (Movie, Show)):
        with db.Session() as session:
            return session.execute(select(func.count(MediaItem._id)).where(MediaItem.imdb_id == item.imdb_id)).scalar_one() != 0
    return bool(item and item._id)

def _get_item_type_from_db(item: MediaItem) -> str:
    with db.Session() as session:
        if item._id is None:
            return session.execute(select(MediaItem.type).where((MediaItem.imdb_id==item.imdb_id) & (MediaItem.type.in_(["show", "movie"])))).scalar_one()
        return session.execute(select(MediaItem.type).where(MediaItem._id==item._id)).scalar_one()

def _store_item(item: MediaItem):
    if isinstance(item, (Movie, Show, Season, Episode)) and item._id is not None:
        with db.Session() as session:
            session.merge(item)
            session.commit()
    else:
        with db.Session() as session:
            _check_for_and_run_insertion_required(session, item)

def _get_item_from_db(session, item: MediaItem):
    if not _ensure_item_exists_in_db(item):
        return None
    session.expire_on_commit = False
    type = _get_item_type_from_db(item)
    match type:
        case "movie":
            r = session.execute(
                select(Movie)
                .where(MediaItem.imdb_id == item.imdb_id)
                .options(joinedload("*"))
            ).unique().scalar_one()
            return r
        case "show":
            r = session.execute(
                select(Show)
                .where(MediaItem.imdb_id == item.imdb_id)
                .options(joinedload("*"))
            ).unique().scalar_one()
            return r
        case "season":
            r = session.execute(
                select(Season)
                .where(Season._id == item._id)
                .options(joinedload("*"))
            ).unique().scalar_one()
            return r
        case "episode":
            r = session.execute(
                select(Episode)
                .where(Episode._id == item._id)
                .options(joinedload("*"))
            ).unique().scalar_one()
            return r
        case _:
            logger.error(f"_get_item_from_db Failed to create item from type: {type}")
            return None

def _check_for_and_run_insertion_required(session, item: MediaItem) -> None:
    if not _ensure_item_exists_in_db(item) and isinstance(item, (Show, Movie, Season, Episode)):
            item.store_state()
            session.add(item)
            session.commit()
            logger.log("PROGRAM", f"{item.log_string} Inserted into the database.")
            return True
    return False

def _run_thread_with_db_item(fn, service, program, input_item: MediaItem | None):
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
    logger.debug("Resetting Database")
    
    # Drop all tables
    db.Model.metadata.drop_all(db.engine)
    logger.debug("All MediaItem tables dropped")
    
    # Drop the alembic_version table
    with db.engine.connect() as connection:
        connection.execute(text("DROP TABLE IF EXISTS alembic_version CASCADE"))
    logger.debug("Alembic table dropped")
    
    # Recreate all tables
    db.Model.metadata.create_all(db.engine)
    logger.debug("All tables recreated")
    
    # Reinitialize Alembic
    logger.debug("Removing Alembic Directory")
    shutil.rmtree(alembic_dir, ignore_errors=True)
    os.makedirs(alembic_dir, exist_ok=True)
    alembic.init(alembic_dir)
    logger.debug("Alembic reinitialized")

    logger.debug("Hard Reset Complete")

reset = os.getenv("HARD_RESET", None)
if reset is not None and reset.lower() in ["true","1"]:
    hard_reset_database()

if os.getenv("REPAIR_SYMLINKS", None) is not None and os.getenv("REPAIR_SYMLINKS").lower() in ["true","1"]:
    fix_broken_symlinks(settings_manager.settings.symlink.library_path, settings_manager.settings.symlink.rclone_path)
    exit(0)