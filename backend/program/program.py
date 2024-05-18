import os
import threading
import time
import traceback
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime
from queue import Empty, Queue

from apscheduler.schedulers.background import BackgroundScheduler
from program.content import Listrr, Mdblist, Overseerr, PlexWatchlist
from program.indexers.trakt import TraktIndexer
from program.libaries import SymlinkLibrary
from program.media.container import MediaItemContainer
from program.media.item import MediaItem
from program.media.state import States
from program.scrapers import Scraping
from program.settings.manager import settings_manager
from program.updaters.plex import PlexUpdater
from utils import data_dir_path
from utils.logger import logger

from .pickly import Pickly
from .realdebrid import Debrid
from .state_transition import process_event
from .symlink import Symlinker
from .types import Event, Service


class Program(threading.Thread):
    """Program class"""

    def __init__(self, args):
        super().__init__(name="Iceberg")
        self.running = False
        self.startup_args = args
        logger.configure_logger(
            debug=settings_manager.settings.debug, log=settings_manager.settings.log
        )

    def initialize_services(self):
        self.requesting_services = {
            Overseerr: Overseerr(),
            PlexWatchlist: PlexWatchlist(),
            Listrr: Listrr(),
            Mdblist: Mdblist(),
        }
        self.indexing_services = {TraktIndexer: TraktIndexer()}
        self.processing_services = {
            Scraping: Scraping(),
            Debrid: Debrid(),
            Symlinker: Symlinker(),
            PlexUpdater: PlexUpdater(),
        }
        # Depends on Symlinker having created the file structure so needs
        #   to run after it
        self.library_services = {SymlinkLibrary: SymlinkLibrary()}
        self.services = {
            **self.library_services,
            **self.indexing_services,
            **self.requesting_services,
            **self.processing_services,
        }

        self.initialized = True

    def start(self):
        logger.info("Iceberg v%s starting!", settings_manager.settings.version)
        settings_manager.register_observer(self.initialize_services)
        self.initialized = False
        self.event_queue = Queue()
        os.makedirs(data_dir_path, exist_ok=True)

        try:
            self.initialize_services()
        except Exception:
            logger.error(traceback.format_exc())

        logger.info("----------------------------------------------")
        logger.info("Iceberg is waiting for configuration to start!")
        logger.info("----------------------------------------------")
        while not self.validate():
            time.sleep(1)

        logger.info("Iceberg started!")

        self.media_items = MediaItemContainer()
        if not self.startup_args.ignore_cache:
            self.pickly = Pickly(self.media_items, data_dir_path)
            self.pickly.start()

        if not len(self.media_items):
            # seed initial MIC with Library State
            for item in self.services[SymlinkLibrary].run():
                self.media_items.upsert(item)
        self.scheduler = BackgroundScheduler()
        self.executor = ThreadPoolExecutor(thread_name_prefix="Worker", max_workers=4)
        self._schedule_services()
        self._schedule_functions()
        super().start()
        self.scheduler.start()
        self.running = True
        logger.info("Iceberg is running!")

    def _retry_library(self) -> None:
        for _, item in self.media_items.get_incomplete_items().items():
            self.event_queue.put(Event(emitted_by=self.__class__, item=item))

    def _schedule_functions(self) -> None:
        """Schedule each service based on its update interval."""
        scheduled_functions = {self._retry_library: {"interval": 60 * 10}}
        for func, config in scheduled_functions.items():
            self.scheduler.add_job(
                func,
                "interval",
                seconds=config["interval"],
                args=config.get("args"),
                id=f"{func.__name__}",
                max_instances=1,
                replace_existing=True,  # Replace existing jobs with the same ID
                next_run_time=datetime.now(),
            )
            logger.info(
                "Scheduled %s to run every %s seconds.",
                func.__name__,
                config["interval"],
            )

    def _schedule_services(self) -> None:
        """Schedule each service based on its update interval."""
        scheduled_services = {**self.requesting_services, **self.library_services}
        for service_cls, service_instance in scheduled_services.items():
            if not service_instance.initialized:
                logger.info(
                    "Not scheduling %s due to not being initialized",
                    service_cls.__name__,
                )
                continue
            if not (
                update_interval := getattr(
                    service_instance.settings, "update_interval", False
                )
            ):
                logger.info(
                    "Service %s update_interval set to False or missing, "
                    + " not schedulings regular updates",
                    service_cls.__name__,
                )
                continue

            self.scheduler.add_job(
                self._submit_job,
                "interval",
                seconds=update_interval,
                args=[service_cls, None],
                id=f"{service_cls.__name__}_update",
                max_instances=1,
                replace_existing=True,  # Replace existing jobs with the same ID
                next_run_time=datetime.now() if service_cls != SymlinkLibrary else None,
            )
            logger.info(
                "Scheduled %s to run every %s seconds.",
                service_cls.__name__,
                update_interval,
            )

    def _process_future_item(self, future: Future, service: Service, item: MediaItem) -> None:
        """Callback to add the results from a future emitted by a service to the event queue."""
        try:
            for item in future.result():
                if not isinstance(item, MediaItem):
                    logger.error(
                        "Service %s emitted item %s of type %s, skipping",
                        service.__name__,
                        item,
                        item.__class__.__name__,
                    )
                    continue
                if item.state != States.Completed:
                    self.event_queue.put(Event(emitted_by=service, item=item))

        except Exception:
            logger.error(
                "Service %s failed with exception %s",
                service.__name__,
                traceback.format_exc(),
            )

    def _submit_job(self, service: Service, item: MediaItem | None) -> None:
        if item:
            # lets cleanup the log output so we aren't spamming the logs..
            logger.debug(f"Submitting service {service.__name__} to the pool with {getattr(item, 'log_string', None) or item.item_id}")
        func = self.services[service].run
        future = (
            self.executor.submit(func)
            if item is None
            else self.executor.submit(func, item)
        )
        future.add_done_callback(lambda f: self._process_future_item(f, service, item))

    def run(self):
        while self.running:
            if not self.validate():
                time.sleep(1)
                continue
            try:
                event: Event = self.event_queue.get(timeout=1)
            except Empty:
                # Unblock after waiting in case we are no longer supposed to be running
                continue

            if event.item.state == States.Completed:
                logger.debug(
                    "Item %s is already completed, skipping",
                    event.item.state.log_string,
                )
                self.event_queue.task_done()
                continue

            existing_item = self.media_items.get(event.item.item_id, None)
            if not existing_item:
                logger.error(
                    "Event emitted by %s for item %s, but item not found in container",
                    event.emitted_by.__name__,
                    event.item.item_id,
                )
                continue

            updated_item, next_service, items_to_submit = process_event(
                existing_item, event.emitted_by, event.item
            )

            # before submitting the item to be processed, commit it to the container
            if updated_item:
                self.media_items.upsert(updated_item)
                if updated_item.state == States.Completed:
                    logger.info(
                        "%s %s has been completed",
                        updated_item.__class__.__name__,
                        updated_item.log_string,
                    )

            for item_to_submit in items_to_submit:
                self._submit_job(next_service, item_to_submit)
        
            self.event_queue.task_done()

    def validate(self):
        return all(
            (
                any(s.initialized for s in self.requesting_services.values()),
                any(s.initialized for s in self.library_services.values()),
                any(s.initialized for s in self.indexing_services.values()),
                all(s.initialized for s in self.processing_services.values()),
            )
        )

    def stop(self):
        self.running = False
        if hasattr(self, "scheduler") and self.scheduler.running:
            self.scheduler.shutdown(wait=False)
        if hasattr(self, "executor") and not self.executor.shutdown:
            self.executor.shutdown(wait=False)
        if hasattr(self, "pickly") and self.pickly.running:
            self.pickly.stop()
        if hasattr(self, "services"):
            for service in self.services.values():
                if hasattr(service, "stop"):
                    service.stop()
        logger.info("Iceberg has been stopped.")

    def add_to_queue(self, item: MediaItem):
        """Add item to the queue for processing."""
        if item is not None:
            if item not in self.media_items and item not in self.library_items:
                self.queue.put(Event(emitted_by=self.__class__, item=item))
                logger.info(f"Added {item.log_string} to the queue")
            else:
                logger.info(f"Item {item.log_string} already in container, skipping")
