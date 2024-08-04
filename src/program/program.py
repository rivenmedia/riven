import linecache
import os
import threading
import time
import traceback
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime
from multiprocessing import Lock
from queue import Empty, Queue

from apscheduler.schedulers.background import BackgroundScheduler
from program.content import Listrr, Mdblist, Overseerr, PlexWatchlist, TraktContent
from program.downloaders import Downloader
from program.indexers.trakt import TraktIndexer
from program.libraries import SymlinkLibrary
from program.media.item import Episode, MediaItem, Movie, Season, Show, copy_item
from program.media.state import States
from program.scrapers import Scraping
from program.settings.manager import settings_manager
from program.settings.models import get_version
from program.updaters import Updater
from utils import data_dir_path
from utils.logger import logger, scrub_logs
from utils.notifications import notify_on_complete

from .state_transition import process_event
from .symlink import Symlinker
from .types import Event, Service

if settings_manager.settings.tracemalloc:
    import tracemalloc

import program.db.db_functions as DB
from program.db.db import db, run_migrations
from sqlalchemy import func, select


class Program(threading.Thread):
    """Program class"""

    def __init__(self, args):
        super().__init__(name="Riven")
        self.running = False
        self.startup_args = args
        self.initialized = False
        self.event_queue = Queue()
        self.services = {}
        self.queued_events = []
        self.running_events = []
        self.mutex = Lock()
        self.enable_trace = settings_manager.settings.tracemalloc
        self.sql_Session = db.Session
        if self.enable_trace:
            tracemalloc.start()
            self.malloc_time = time.monotonic()-50
            self.last_snapshot = None

    def initialize_services(self):
        self.requesting_services = {
            Overseerr: Overseerr(),
            PlexWatchlist: PlexWatchlist(),
            Listrr: Listrr(),
            Mdblist: Mdblist(),
            TraktContent: TraktContent(),
        }
        self.indexing_services = {TraktIndexer: TraktIndexer()}
        self.processing_services = {
            Scraping: Scraping(),
            Symlinker: Symlinker(),
            Updater: Updater(),
            Downloader: Downloader(),
        }
        # Depends on Symlinker having created the file structure so needs
        # to run after it
        self.library_services = {
            SymlinkLibrary: SymlinkLibrary(),
        }
        if not any(s.initialized for s in self.requesting_services.values()):
            logger.error("No Requesting service initialized, you must enable at least one.")
        if not self.processing_services.get(Scraping).initialized:
            logger.error("No Scraping service initialized, you must enable at least one.")
        if not self.processing_services.get(Downloader).initialized:
            logger.error("No Downloader service initialized, you must enable at least one.")
        if not self.processing_services.get(Updater).initialized:
            logger.error("No Updater service initialized, you must enable at least one.")

        self.services = {
            **self.library_services,
            **self.indexing_services,
            **self.requesting_services,
            **self.processing_services,
        }

        if self.enable_trace:
            self.last_snapshot = tracemalloc.take_snapshot()

    def validate(self) -> bool:
        """Validate that all required services are initialized."""
        return all(
            (
                any(s.initialized for s in self.requesting_services.values()),
                any(s.initialized for s in self.library_services.values()),
                any(s.initialized for s in self.indexing_services.values()),
                all(s.initialized for s in self.processing_services.values()),
                self.processing_services[Downloader].initialized,
            )
        )

    def start(self):
        latest_version = get_version()
        logger.log("PROGRAM", f"Riven v{latest_version} starting!")

        settings_manager.register_observer(self.initialize_services)
        os.makedirs(data_dir_path, exist_ok=True)

        if not settings_manager.settings_file.exists():
            logger.log("PROGRAM", "Settings file not found, creating default settings")
            settings_manager.save()

        try:
            self.initialize_services()
            scrub_logs()
        except Exception as e:
            logger.exception(f"Failed to initialize services: {e}")

        max_worker_env_vars = [var for var in os.environ if var.endswith("_MAX_WORKERS")]
        if max_worker_env_vars:
            for var in max_worker_env_vars:
                logger.log("PROGRAM", f"{var} is set to {os.environ[var]} workers")

        logger.log("PROGRAM", "----------------------------------------------")
        logger.log("PROGRAM", "Riven is waiting for configuration to start!")
        logger.log("PROGRAM", "----------------------------------------------")

        while not self.validate():
            time.sleep(1)

        self.initialized = True
        logger.log("PROGRAM", "Riven started!")

        run_migrations()
        with db.Session() as session:
            res = session.execute(select(func.count(MediaItem._id))).scalar_one()
            added = []
            if res == 0:
                for item in self.services[SymlinkLibrary].run():
                    if settings_manager.settings.map_metadata:
                        if isinstance(item, (Movie, Show)):
                            try:
                                item = next(self.services[TraktIndexer].run(item))
                            except StopIteration as e:
                                logger.error(f"Failed to enhance metadata for {item.title} ({item.item_id}): {e}")
                                continue
                            if item.item_id in added:
                                logger.error(f"Cannot enhance metadata, {item.title} ({item.item_id}) contains multiple folders. Manual resolution required. Skipping.")
                                continue
                            added.append(item.item_id)
                            item.store_state()
                            session.add(item)
                            logger.debug(f"Mapped metadata to {item.type.title()}: {item.log_string}")
                session.commit()

            movies_symlinks = session.execute(select(func.count(Movie._id)).where(Movie.symlinked == True)).scalar_one() # noqa
            episodes_symlinks = session.execute(select(func.count(Episode._id)).where(Episode.symlinked == True)).scalar_one() # noqa
            total_symlinks = movies_symlinks + episodes_symlinks
            total_movies = session.execute(select(func.count(Movie._id))).scalar_one()
            total_shows = session.execute(select(func.count(Show._id))).scalar_one()
            total_seasons = session.execute(select(func.count(Season._id))).scalar_one()
            total_episodes = session.execute(select(func.count(Episode._id))).scalar_one()
            total_items = session.execute(select(func.count(MediaItem._id))).scalar_one()

            logger.log("ITEM", f"Movies: {total_movies} (Symlinks: {movies_symlinks})")
            logger.log("ITEM", f"Shows: {total_shows}")
            logger.log("ITEM", f"Seasons: {total_seasons}")
            logger.log("ITEM", f"Episodes: {total_episodes} (Symlinks: {episodes_symlinks})")
            logger.log("ITEM", f"Total Items: {total_items} (Symlinks: {total_symlinks})")

        self.executors = []
        self.scheduler = BackgroundScheduler()
        self._schedule_services()
        self._schedule_functions()

        super().start()
        self.scheduler.start()
        self.running = True
        logger.success("Riven is running!")

    def _retry_library(self) -> None:
        count = 0
        with db.Session() as session:
            count = session.execute(
                select(func.count(MediaItem._id))
                .where(MediaItem.type.in_(["movie", "show"]))
                .where(MediaItem.last_state != "Completed")
            ).scalar_one()
        logger.log("PROGRAM", f"Found {count} items to retry")

        number_of_rows_per_page = 10
        for page_number in range(0, (count // number_of_rows_per_page) + 1):
            with db.Session() as session:
                items_to_submit = session.execute(
                    select(MediaItem)
                    .where(MediaItem.type.in_(["movie", "show"]))
                    .where(MediaItem.last_state != "Completed")
                    .order_by(MediaItem.requested_at.desc())
                    .limit(number_of_rows_per_page)
                    .offset(page_number * number_of_rows_per_page)
                ).unique().scalars().all()

                for item in items_to_submit:
                    self._push_event_queue(Event(emitted_by="RetryLibrary", item=item))

    def _schedule_functions(self) -> None:
        """Schedule each service based on its update interval."""
        scheduled_functions = {
            self._retry_library: {"interval": 60 * 10},
        }
        for func, config in scheduled_functions.items():
            self.scheduler.add_job(
                func,
                "interval",
                seconds=config["interval"],
                args=config.get("args"),
                id=f"{func.__name__}",
                max_instances=config.get("max_instances", 1),
                replace_existing=True,
                next_run_time=datetime.now(),
                misfire_grace_time=30
            )
            logger.log("PROGRAM", f"Scheduled {func.__name__} to run every {config['interval']} seconds.")

    def _schedule_services(self) -> None:
        """Schedule each service based on its update interval."""
        scheduled_services = {**self.requesting_services, **self.library_services}
        for service_cls, service_instance in scheduled_services.items():
            if not service_instance.initialized:
                continue
            if not (update_interval := getattr(service_instance.settings, "update_interval", False)):
                continue

            self.scheduler.add_job(
                self._submit_job,
                "interval",
                seconds=update_interval,
                args=[service_cls, None],
                id=f"{service_cls.__name__}_update",
                max_instances=1,
                replace_existing=True,
                next_run_time=datetime.now() if service_cls != SymlinkLibrary else None,
                coalesce=False,
            )
            logger.log("PROGRAM", f"Scheduled {service_cls.__name__} to run every {update_interval} seconds.")

    def _id_in_queue(self, id):
        return any(event.item._id == id for event in self.queued_events)

    def _id_in_running_events(self, id):
        return any(event.item._id == id for event in self.running_events)

    def _push_event_queue(self, event):
        with self.mutex:
            if any(qi.item.imdb_id == event.item.imdb_id and qi.emitted_by == event.emitted_by for qi in self.queued_events):
                logger.debug(f"Item {event.item.log_string} is already in the queue, skipping.")
                return False
            elif any(ri.item.imdb_id == event.item.imdb_id and ri.emitted_by == event.emitted_by for ri in self.running_events):
                logger.debug(f"Item {event.item.log_string} is already running, skipping.")
                return False

            if isinstance(event.item, MediaItem) and hasattr(event.item, "_id"):
                if event.item.type == "show":
                    for s in event.item.seasons:
                        if self._id_in_queue(s._id) or self._id_in_running_events(s._id):
                            return False
                        for e in s.episodes:
                            if self._id_in_queue(e._id) or self._id_in_running_events(e._id):
                                return False

                elif event.item.type == "season":
                    for e in event.item.episodes:
                        if self._id_in_queue(e._id) or self._id_in_running_events(e._id):
                            return False

                elif hasattr(event.item, "parent"):
                    parent = event.item.parent
                    if self._id_in_queue(parent._id) or self._id_in_running_events(parent._id):
                        return False
                    elif hasattr(parent, "parent") and (self._id_in_queue(parent.parent._id) or self._id_in_running_events(parent.parent._id)):
                        return False

            if not isinstance(event.item, (Show, Movie, Episode, Season)):
                logger.log("NEW", f"Added {event.item.log_string} to the queue")
            else:
                logger.log("DISCOVERY", f"Re-added {event.item.log_string} to the queue")
            if not isinstance(event.item, MediaItem):
                event.item = copy_item(event.item)
            self.queued_events.append(event)
            self.event_queue.put(event)
            return True

    def _pop_event_queue(self, event):
        with self.mutex:
            # DB._store_item(event.item)  # possibly causing duplicates
            self.queued_events.remove(event)

    def _remove_from_running_events(self, item, service_name=""):
        with self.mutex:
            event = next((event for event in self.running_events if event.item._id == item._id), None)
            if event:
                self.running_events.remove(event)
                logger.log("PROGRAM", f"Item {item.log_string} finished running section {service_name}" )

    def add_to_running(self, e):
        if e.item is None:
            return
        with self.mutex:
            if all(event.item._id != e.item._id for event in self.running_events):
                if isinstance(e.item, MediaItem) and not self._id_in_running_events(e.item._id):
                    self.running_events.append(e)
                elif not isinstance(e.item, MediaItem):
                    self.running_events.append(e)
                logger.log("PROGRAM", f"Item {e.item.log_string} started running section { e.emitted_by.__name__ if type(e.emitted_by) != str else e.emitted_by}" )

    def _process_future_item(self, future: Future, service: Service, orig_item: MediaItem) -> None:
        """Callback to add the results from a future emitted by a service to the event queue."""
        try:
            for i in future.result():
                if i is not None:
                    self._remove_from_running_events(i, service.__name__)
                    self._push_event_queue(Event(emitted_by=service, item=i))
            if orig_item is not None:
                logger.log("PROGRAM", f"Service {service.__name__} finished running on {orig_item.log_string}")
        except TimeoutError:
            logger.debug("Service {service.__name__} timeout waiting for result on {orig_item.log_string}")
            self._remove_from_running_events(orig_item, service.__name__)
        except Exception:
            logger.exception(f"Service {service.__name__} failed with exception {traceback.format_exc()}")
            self._remove_from_running_events(orig_item, service.__name__)

    def _submit_job(self, service: Service, item: MediaItem | None) -> None:
        if item and service:
            if service.__name__ == "TraktIndexer":
                logger.log("NEW", f"Submitting service {service.__name__} to the pool with {getattr(item, 'log_string', None) or item.item_id}")
            else:
                logger.log("PROGRAM", f"Submitting service {service.__name__} to the pool with {getattr(item, 'log_string', None) or item.item_id}")

        # Check if the executor has been shut down
        if not self.running:
            logger.log("PROGRAM", "Waiting for executor to start before submitting jobs")
            return

        # Instead of using the one executor, loop over the list of self.executors, if one is found with the service.__name__ then use that one
        # If one is not found with the service.__name__ then create a new one and append it to the list
        # This will allow for multiple services to run at the same time
        found = False
        cur_executor = None
        for executor in self.executors:
            if executor["_name_prefix"] == service.__name__:
                found = True
                cur_executor = executor["_executor"]
                break

        if not found:
            max_workers = int(os.environ[service.__name__.upper() +"_MAX_WORKERS"]) if service.__name__.upper() + "_MAX_WORKERS" in os.environ else 1
            new_executor = ThreadPoolExecutor(thread_name_prefix=f"Worker_{service.__name__}", max_workers=max_workers )
            self.executors.append({ "_name_prefix": service.__name__, "_executor": new_executor })
            cur_executor = new_executor
        fn = self.services[service].run
        func = DB._run_thread_with_db_item #func = self.services[service].run # self._run_thread_with_db_item
        future = cur_executor.submit(func, fn, service, self, item)  #cur_executor.submit(func) if item is None else cur_executor.submit(func, item)
        future.add_done_callback(lambda f: self._process_future_item(f, service, item))

    def display_top_allocators(self, snapshot, key_type="lineno", limit=10):
        top_stats = snapshot.compare_to(self.last_snapshot, "lineno")

        logger.debug("Top %s lines" % limit)
        for index, stat in enumerate(top_stats[:limit], 1):
            frame = stat.traceback[0]
            # replace "/path/to/module/file.py" with "module/file.py"
            filename = os.sep.join(frame.filename.split(os.sep)[-2:])
            logger.debug("#%s: %s:%s: %.1f KiB"
                % (index, filename, frame.lineno, stat.size / 1024))
            line = linecache.getline(frame.filename, frame.lineno).strip()
            if line:
                logger.debug("    %s" % line)

        other = top_stats[limit:]
        if other:
            size = sum(stat.size for stat in other)
            logger.debug("%s other: %.1f KiB" % (len(other), size / 1024))
        total = sum(stat.size for stat in top_stats)
        logger.debug("Total allocated size: %.1f KiB" % (total / 1024))

    def dump_tracemalloc(self):
        if time.monotonic() - self.malloc_time > 60:
            self.malloc_time = time.monotonic()
            snapshot = tracemalloc.take_snapshot()
            self.display_top_allocators(snapshot)

    def run(self):
        while self.running:
            if not self.validate():
                time.sleep(1)
                continue

            try:
                event: Event = self.event_queue.get(timeout=10)
                if self.enable_trace:
                    self.dump_tracemalloc()
                self.add_to_running(event)
                self._pop_event_queue(event)
            except Empty:
                if self.enable_trace:
                    self.dump_tracemalloc()
                continue

            with db.Session() as session:
                existing_item: MediaItem | None = DB._get_item_from_db(session, event.item)
                processed_item, next_service, items_to_submit = process_event(
                    existing_item, event.emitted_by, event.item
                )

                if processed_item and processed_item.state == States.Completed:
                    if processed_item.type in ["show", "movie"]:
                        logger.success(f"Item has been completed: {processed_item.log_string}")

                    if settings_manager.settings.notifications.enabled:
                            notify_on_complete(processed_item)

                self._remove_from_running_events(event.item, "program.run")

                if items_to_submit:
                    for item_to_submit in items_to_submit:
                        self.add_to_running(Event(next_service.__name__, item_to_submit))
                        self._submit_job(next_service, item_to_submit)
                if isinstance(processed_item, MediaItem):
                    processed_item.store_state()
                session.commit()

    def stop(self):
        if not self.running:
            return

        self.running = False
        self.clear_queue()  # Clear the queue when stopping
        if hasattr(self, "executors"):
            for executor in self.executors:
                if not getattr(executor["_executor"], "_shutdown", False):
                    executor["_executor"].shutdown(wait=False)
        if hasattr(self, "scheduler") and getattr(self.scheduler, "running", False):
            self.scheduler.shutdown(wait=False)
        logger.log("PROGRAM", "Riven has been stopped.")

    def add_to_queue(self, item: MediaItem, emitted_by="Manual") -> bool:
        """Add item to the queue for processing."""
        logger.log("PROGRAM", f"Adding {item.log_string} to the queue.")
        return self._push_event_queue(Event(emitted_by=emitted_by, item=item))

    def clear_queue(self):
        """Clear the event queue."""
        logger.log("PROGRAM", "Clearing the event queue. Please wait.")
        while not self.event_queue.empty():
            try:
                self.event_queue.get_nowait()
                self.event_queue.task_done()
            except Empty:
                break
        logger.log("PROGRAM", "Cleared the event queue")