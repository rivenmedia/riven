from sqla_wrapper import Alembic, SQLAlchemy
from program.settings.manager import settings_manager
from program.media.item import Episode, MediaItem, Movie, Season, Show
from sqlalchemy import select, func
from sqlalchemy.orm import joinedload
from utils.logger import logger
from program.types import Event
from .db import db
import os

def _ensure_item_exists_in_db(item:MediaItem) -> bool:
    if isinstance(item, (Movie, Show)):
        with db.Session() as session:
            return session.execute(select(func.count(MediaItem._id)).where(MediaItem.imdb_id==item.imdb_id)).scalar_one() != 0
    return item._id is not None

def _get_item_type_from_db(item: MediaItem) -> str:
    with db.Session() as session:
        if item._id is None:
            return session.execute(select(MediaItem.type).where( (MediaItem.imdb_id==item.imdb_id ) & ( (MediaItem.type == 'show') | (MediaItem.type == 'movie') ) )).scalar_one() 
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
    type = _get_item_type_from_db(item)

    match type:
        case "movie":
            r = session.execute(select(Movie).where(MediaItem.imdb_id==item.imdb_id).options(joinedload("*"))).unique().scalar_one()
            session.expunge(r)
            return r
        case "show":
            r = session.execute(select(Show).where(MediaItem.imdb_id==item.imdb_id).options(joinedload("*"))).unique().scalar_one()
            session.expunge(r)
            for season in r.seasons:
                for episode in season.episodes:
                    episode.parent = season
                season.parent = r
            return r
        case "season":
            r = session.execute(select(Season).where(Season._id==item._id).options(joinedload("*"))).unique().scalar_one()
            r.parent = r.parent
            r.parent.seasons = r.parent.seasons
            session.expunge(r)
            for episode in r.episodes:
                episode.parent = r
            return r
        case "episode":
            r = session.execute(select(Episode).where(Episode._id==item._id).options(joinedload("*"))).unique().scalar_one()
            r.parent = r.parent
            r.parent.parent = r.parent.parent
            r.parent.parent.seasons = r.parent.parent.seasons
            r.parent.episodes = r.parent.episodes
            session.expunge(r)
            return r
        case _:
            logger.error(f"_get_item_from_db Failed to create item from data: {data}")
            return None
            
def _check_for_and_run_insertion_required(session, item: MediaItem) -> None:
    if _ensure_item_exists_in_db(item) == False:
        if isinstance(item, (Show, Movie, Season, Episode)):
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
                item = input_item
                if not _check_for_and_run_insertion_required(session, item): 
                    item = _get_item_from_db(session, item)
                item.set("streams", input_item.get("streams", {}))
                #session.merge(item)
                for res in fn(item):
                    if isinstance(res, list):
                        all_media_items = True
                        for i in res:
                            if not isinstance(i, MediaItem):
                                all_media_items = False

                        program._remove_from_running_items(item, service.__name__)
                        if all_media_items == True:
                            for i in res:
                                program._push_event_queue(Event(emitted_by="_run_thread_with_db_item", item=i))
                        session.commit()
                        return
                    elif not isinstance(res, MediaItem):
                        logger.log("PROGRAM", f"Service {service.__name__} emitted item {item} of type {item.__class__.__name__}, skipping")
                    program._remove_from_running_items(item, service.__name__)
                    if res is not None and isinstance(res, MediaItem):
                        program._push_event_queue(Event(emitted_by=service, item=res))
                        # self._check_for_and_run_insertion_required(item)    

                    item.store_state()
                    session.commit()

                    session.expunge_all()
                return res
        for i in fn(input_item):
            yield i
        return
    else:
        for i in fn():
            yield i
        return