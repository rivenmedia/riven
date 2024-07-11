from sqlalchemy import select, func
from sqlalchemy.orm import joinedload
from utils.logger import logger
from program.media.item import Episode, MediaItem, Movie, Season, Show
from program.types import Event


class DbFunctions:
    def __init__(self, _logger: logger):
        self.logger = _logger

    @staticmethod
    def ensure_item_exists_in_db(session, item: MediaItem) -> bool:
        if isinstance(item, (Movie, Show)):
            return session.execute(
                select(func.count(MediaItem._id)).where(MediaItem.imdb_id == item.imdb_id)).scalar_one() != 0
        return item._id is not None

    @staticmethod
    def get_item_type_from_db(session, item: MediaItem) -> str:
        if item._id is None:
            return session.execute(select(MediaItem.type).where((MediaItem.imdb_id == item.imdb_id) & (
                    (MediaItem.type == 'show') | (MediaItem.type == 'movie')))).scalar_one()
        return session.execute(select(MediaItem.type).where(MediaItem._id == item._id)).scalar_one()

    def store_item(self, session, item: MediaItem):
        if isinstance(item, (Movie, Show, Season, Episode)) and item._id is not None:
            session.merge(item)
            session.commit()
        else:
            self.check_for_and_run_insertion_required(session, item)

    def get_item_from_db(self, session, item: MediaItem):
        if not self.ensure_item_exists_in_db(session, item):
            return None
        item_type = self.get_item_type_from_db(session, item)
        session.expire_on_commit = False
        match item_type:
            case "movie":
                r = session.execute(
                    select(Movie).where(MediaItem.imdb_id == item.imdb_id).options(joinedload("*"))).unique().scalar_one()
                session.expunge(r)
                return r
            case "show":
                r = session.execute(
                    select(Show).where(MediaItem.imdb_id == item.imdb_id).options(joinedload("*"))).unique().scalar_one()
                session.expunge(r)
                for season in r.seasons:
                    for episode in season.episodes:
                        episode.parent = season
                    season.parent = r
                return r
            case "season":
                r = session.execute(
                    select(Season).where(Season._id == item._id).options(joinedload("*"))).unique().scalar_one()
                r.parent = r.parent
                r.parent.seasons = r.parent.seasons
                session.expunge(r)
                for episode in r.episodes:
                    episode.parent = r
                return r
            case "episode":
                r = session.execute(
                    select(Episode).where(Episode._id == item._id).options(joinedload("*"))).unique().scalar_one()
                r.parent = r.parent
                r.parent.parent = r.parent.parent
                r.parent.parent.seasons = r.parent.parent.seasons
                r.parent.episodes = r.parent.episodes
                session.expunge(r)
                return r
            case _:
                self.logger.error(f"get_item_from_db Failed to create item from type: {item_type}")
                return None

    def check_for_and_run_insertion_required(self, session, item: MediaItem) -> bool:
        if not self.ensure_item_exists_in_db(session, item):
            if isinstance(item, (Show, Movie, Season, Episode)):
                item.store_state()
                session.add(item)
                session.commit()
                self.logger.log("PROGRAM", f"{item.log_string} Inserted into the database.")
                return True
        return False

    def run_thread_with_db_item(self, session, fn, service, program, input_item: MediaItem | None):
        if input_item is not None:
            with session:
                if isinstance(input_item, (Movie, Show, Season, Episode)):
                    item = input_item
                    if not self.check_for_and_run_insertion_required(session, item):
                        item = self.get_item_from_db(session, item)
                    item.set("streams", input_item.get("streams", {}))
                    for res in fn(item):
                        if isinstance(res, list):
                            all_media_items = True
                            for i in res:
                                if not isinstance(i, MediaItem):
                                    all_media_items = False

                            program._remove_from_running_items(item, service.__name__)
                            if all_media_items:
                                for i in res:
                                    program._push_event_queue(Event(emitted_by="run_thread_with_db_item", item=i))
                            session.commit()
                            return
                        elif not isinstance(res, MediaItem):
                            self.logger.log("PROGRAM",
                                            f"Service {service.__name__} emitted item {item} of type {item.__class__.__name__}, skipping")
                        program._remove_from_running_items(item, service.__name__)
                        if res is not None and isinstance(res, MediaItem):
                            program._push_event_queue(Event(emitted_by=service, item=res))

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