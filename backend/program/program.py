import os
import threading
import time
import traceback
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime
from multiprocessing import Lock
from queue import Empty, Queue
from typing import Union

from apscheduler.schedulers.background import BackgroundScheduler
from program.content import Listrr, Mdblist, Overseerr, PlexWatchlist, TraktContent
from program.downloaders.realdebrid import Debrid
from program.downloaders.torbox import TorBoxDownloader
from program.indexers.trakt import TraktIndexer
from program.libraries import SymlinkLibrary
from program.media.container import MediaItemContainer
from program.media.item import Episode, MediaItem, Movie, Season, Show
from program.media.state import States
from program.scrapers import Scraping
from program.settings.manager import settings_manager
from program.updaters.plex import PlexUpdater
from utils import data_dir_path
from utils.logger import logger, scrub_logs

from .cache import hash_cache
from .pickly import Pickly
from .state_transition import process_event
from .symlink import Symlinker
from .types import Event, Service


class Program(threading.Thread):
    """Program class"""

    def __init__(self, args):
        super().__init__(name="Riven")
        self.running = False
        self.startup_args = args
        self.initialized = False
        self.event_queue = Queue()
        self.media_items = MediaItemContainer()
        self.services = {}
        self.queued_items = []
        self.running_items = []
        self.mutex = Lock()

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
            Scraping: Scraping(hash_cache),
            Symlinker: Symlinker(self.media_items),
            PlexUpdater: PlexUpdater(),
        }
        self.downloader_services = {
            Debrid: Debrid(hash_cache),
            TorBoxDownloader: TorBoxDownloader(hash_cache),
        }
        # Depends on Symlinker having created the file structure so needs
        # to run after it
        self.library_services = {
            SymlinkLibrary: SymlinkLibrary(),
        }
        if not any(s.initialized for s in self.requesting_services.values()):
            logger.error("No Requesting service initialized, you must select at least one.")
        if not any(s.initialized for s in self.downloader_services.values()):
            logger.error("No Downloader service initialized, you must select at least one.")
        if not self.processing_services.get(Scraping).initialized:
            logger.error("No Scraping service initialized, you must select at least one.")

        self.services = {
            **self.library_services,
            **self.indexing_services,
            **self.requesting_services,
            **self.processing_services,
            **self.downloader_services,
        }

    def validate(self) -> bool:
        """Validate that all required services are initialized."""
        return all(
            (
                any(s.initialized for s in self.requesting_services.values()),
                any(s.initialized for s in self.library_services.values()),
                any(s.initialized for s in self.indexing_services.values()),
                all(s.initialized for s in self.processing_services.values()),
                any(s.initialized for s in self.downloader_services.values()),
            )
        )

    def start(self):
        logger.log("PROGRAM", f"Riven v{settings_manager.settings.version} starting!")
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

        max_worker_env_vars = [var for var in os.environ if var.endswith('_MAX_WORKERS')]
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

        if not self.startup_args.ignore_cache:
            self.pickly = Pickly(self.media_items, data_dir_path)
            self.pickly.start()

        if not len(self.media_items):
            # Seed initial MIC with Library State
            for item in self.services[SymlinkLibrary].run():
                self.media_items.upsert(item)
            self.media_items.save(str(data_dir_path / "media.pkl"))

        if len(self.media_items):
            self.media_items.log()

        self.executors = []
        self.scheduler = BackgroundScheduler()
        self._schedule_services()
        self._schedule_functions()

        super().start()
        self.scheduler.start()
        self.running = True
        logger.success("Riven is running!")

    def _retry_library(self) -> None:
        """Retry any items that are in an incomplete state."""
        items_to_submit = [
            item for item in self.media_items.get_incomplete_items().values()
        ]
        logger.log("PROGRAM", f"Found {len(items_to_submit)} items to retry")
        for item in items_to_submit:
            self._push_event_queue(Event(emitted_by=self.__class__, item=item))

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

    def _push_event_queue(self, event):
        with self.mutex:
            if( not event.item in self.queued_items and not event.item in self.running_items):
                if ( isinstance(event.item, Show) 
                        and (any( [s for s in event.item.seasons if s in self.queued_items or s in self.running_items]) 
                        or any([e for e in [s.episodes for s in event.item.seasons] if e in self.queued_items or e in self.running_items]) ) 
                        ):
                    return 
                if isinstance(event.item, Season) and any( [e for e in event.item.episodes if e in self.queued_items or e in self.running_items] ):
                    return
                if hasattr(event.item, "parent") and event.item.parent in self.queued_items :
                    return
                if hasattr(event.item, "parent") and hasattr(event.item.parent, "parent") and event.item.parent.parent and event.item.parent.parent in self.queued_items :
                    return
                if hasattr(event.item, "parent") and event.item.parent in self.running_items :
                    return
                if hasattr(event.item, "parent") and hasattr(event.item.parent, "parent") and event.item.parent.parent and event.item.parent.parent in self.running_items :
                    return
                self.queued_items.append(event.item)
                self.event_queue.put(event)
                if not isinstance(event.item, (Show, Movie, Episode, Season)):
                    logger.log("NEW", f"Added {event.item.log_string} to the queue")
                else:
                    logger.log("DISCOVERY", f"Re-added {event.item.log_string} to the queue" )
                return True
            logger.debug(f"Item {event.item.log_string} is already in the queue or running, skipping.")
            return False

    def _pop_event_queue(self, event):
        with self.mutex:
            self.queued_items.remove(event.item)
    def _remove_from_running_items(self, item, service_name=""):
        with self.mutex:
            if item in self.running_items:
                self.running_items.remove(item)
                logger.log("PROGRAM", f"Item {item.log_string} finished running section {service_name}" )
    def add_to_running(self, item, service_name):
        if item not in self.running_items:
            self.running_items.append(item)
            logger.log("PROGRAM", f"Item {item.log_string} started running section {service_name}" )

    def _process_future_item(self, future: Future, service: Service, orig_item: MediaItem) -> None:
        """Callback to add the results from a future emitted by a service to the event queue."""
        try:
            timeout_seconds = int(
                os.environ[service.__name__.upper() +"_WORKER_TIMEOUT"]
            ) if service.__name__.upper() + "_WORKER_TIMEOUT" in os.environ else 60 * 3
            for item in future.result(timeout=timeout_seconds):
                if isinstance(item, list):
                    all_media_items = True
                    for i in item:
                        if not isinstance(i, MediaItem):
                            all_media_items = False
                    self._remove_from_running_items(orig_item, service.__name__)
                    if all_media_items == True:
                        for i in item:
                            self._push_event_queue(Event(emitted_by=self.__class__, item=i))    
                    return
                elif not isinstance(item, MediaItem):
                    logger.log("PROGRAM", f"Service {service.__name__} emitted item {item} of type {item.__class__.__name__}, skipping")
                self._remove_from_running_items(orig_item, service.__name__)
                if item is not None and isinstance(item, MediaItem):
                    self._push_event_queue(Event(emitted_by=service, item=item))
        except TimeoutError:
            logger.debug('Service {service.__name__} timeout waiting for result on {orig_item.log_string}')
            self._remove_from_running_items(orig_item, service.__name__)
        except Exception:
            logger.exception(f"Service {service.__name__} failed with exception {traceback.format_exc()}")
            self._remove_from_running_items(orig_item, service.__name__)

    def _submit_job(self, service: Service, item: MediaItem | None) -> None:
        if item and service:
            if service.__name__ == "TraktIndexer":
                logger.log("NEW", f"Submitting service {service.__name__} to the pool with {getattr(item, 'log_string', None) or item.item_id}")
            else:
                logger.log("PROGRAM", f"Submitting service {service.__name__} to the pool with {getattr(item, 'log_string', None) or item.item_id}")
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
        func = self.services[service].run
        future = cur_executor.submit(func) if item is None else cur_executor.submit(func, item)
        future.add_done_callback(lambda f: self._process_future_item(f, service, item))

    def run(self):
        orig_item = None
        while self.running:
            if not self.validate():
                time.sleep(1)
                continue

            try:
                event: Event = self.event_queue.get(timeout=10)
                self.add_to_running(event.item, "program.run")
                self._pop_event_queue(event)
            except Empty:
                continue

            existing_item = self.media_items.get(event.item.item_id, None)
            updated_item, next_service, items_to_submit = process_event(
                existing_item, event.emitted_by, event.item
            )

            if updated_item and isinstance(existing_item, (Movie, Show)) and updated_item.state == States.Symlinked:
                logger.success(f"Item has been completed: {updated_item.log_string}")

            if updated_item:
                self.media_items.upsert(updated_item)

            self._remove_from_running_items(event.item, "program.run")

            if items_to_submit:
                for item_to_submit in items_to_submit:
                    self.add_to_running(item_to_submit, next_service.__name__)
                    self._submit_job(next_service, item_to_submit)

    def stop(self):
        self.running = False
        self.clear_queue()  # Clear the queue when stopping
        if hasattr(self, "executors"):
            for executor in self.executors:
                if not getattr(executor["_executor"], '_shutdown', False):
                    executor["_executor"].shutdown(wait=False)
        if hasattr(self, "scheduler") and getattr(self.scheduler, 'running', False):
            self.scheduler.shutdown(wait=False)
        if hasattr(self, "pickly") and getattr(self.pickly, 'running', False):
            self.pickly.stop()
        logger.log("PROGRAM", "Riven has been stopped.")

    def add_to_queue(self, item: MediaItem) -> bool:
        """Add item to the queue for processing."""
        return self._push_event_queue(Event(emitted_by=self.__class__, item=item))

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
