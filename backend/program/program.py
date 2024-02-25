import os
import threading
import time
import traceback

from concurrent.futures import ThreadPoolExecutor, Future
from datetime import datetime
from queue import Queue, Empty

from apscheduler.schedulers.background import BackgroundScheduler

from program.content import Overseerr, PlexWatchlist, Listrr, Mdblist
from program.state_transision import process_event, process_event_and_collect_coverage
from program.indexers.trakt import TraktIndexer
from program.media.container import MediaItemContainer
from program.media.item import MediaItem
from program.media.state import States
from program.libaries import SymlinkLibrary
from program.realdebrid import Debrid
from program.scrapers import Scraping
from program.settings.manager import settings_manager
from program.symlink import Symlinker
from program.updaters.plex import PlexUpdater
from program.types import Event, Service, ProcessedEvent
from utils import data_dir_path
from utils.logger import logger
from utils.utils import Pickly


class Program(threading.Thread):
    """Program class"""

    def __init__(self, args):
        super().__init__(name="Iceberg")
        self.running = False
        self.startup_args = args
        logger.configure_logger(
            debug=settings_manager.settings.debug, 
            log=settings_manager.settings.log
        )

    def initialize_services(self):
        self.library_services = {
            SymlinkLibrary: SymlinkLibrary()
        }
        self.requesting_services = {
            Overseerr: Overseerr(), 
            PlexWatchlist: PlexWatchlist(), 
            Listrr: Listrr(), 
            Mdblist: Mdblist(),
        }
        self.indexing_services = {
            TraktIndexer: TraktIndexer()
        }
        self.processing_services = {
            Scraping: Scraping(), 
            Debrid: Debrid(), 
            Symlinker: Symlinker(),
            PlexUpdater: PlexUpdater()
        }
        self.services = {
            **self.library_services,
            **self.indexing_services,
            **self.requesting_services,
            **self.processing_services
        }

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

        self.media_items = MediaItemContainer()
        if not self.startup_args.ignore_cache:
            self.pickly = Pickly(self.media_items, data_dir_path)
            self.pickly.start()
        if not len(self.media_items):
            # seed initial MIC with Library State
            for item in self.services[SymlinkLibrary].run():
                self.media_items.upsert(item)

        if self.validate():
            logger.info("Iceberg started!")
        else:
            logger.info("----------------------------------------------")
            logger.info("Iceberg is waiting for configuration to start!")
            logger.info("----------------------------------------------")
        self.scheduler = BackgroundScheduler()
        self.executor = ThreadPoolExecutor(thread_name_prefix="Worker") 
        self._schedule_services()
        self._schedule_functions()
        super().start()
        self.scheduler.start()
        self.running = True
        self.initialized = True

    def _retry_library(self) -> None:
        for item_id, item in self.media_items.get_incomplete_items().items():
            self.event_queue.put(Event(emitted_by=self.__class__, item=item))

    def _schedule_functions(self) -> None:
        """Schedule each service based on its update interval."""
        scheduled_functions = { 
            self._retry_library: {
                'interval': 60 * 10
            } 
        }
        for func, config in scheduled_functions.items():
            self.scheduler.add_job(
                func,
                'interval',
                seconds=config['interval'],
                args=config.get('args'),
                id=f'{func.__name__}',
                max_instances=1,
                replace_existing=True,  # Replace existing jobs with the same ID
                next_run_time=datetime.now()
            )
            logger.info("Scheduled %s to run every %s seconds.", func.__name__, config['interval'])
        return
    
    def _schedule_services(self) -> None:
        """Schedule each service based on its update interval."""
        scheduled_services = { **self.requesting_services, **self.library_services }
        for service_cls, service_instance in scheduled_services.items():
            if not service_instance.initialized:
                logger.info("Not scheduling %s due to not being initialized", service_cls.__name__)
                continue
            if not (update_interval := getattr(service_instance.settings, 'update_interval', False)):
                logger.info(
                    "Service %s update_interval set to False or missing, "
                    + " not schedulings regular updates", 
                    service_cls.__name__
                )
                continue

            self.scheduler.add_job(
                self._submit_job,
                'interval',
                seconds=update_interval,
                args=[service_cls, None],
                id=f'{service_cls.__name__}_update',
                max_instances=1,
                replace_existing=True,  # Replace existing jobs with the same ID
                next_run_time=datetime.now() if service_cls != SymlinkLibrary else None
            )
            logger.info("Scheduled %s to run every %s seconds.", service_cls.__name__, update_interval)
        return

    def _process_future_item(self, future: Future, service: Service, input_item: MediaItem) -> None:
        """Callback to add the results from a future emitted by a service to the event queue."""
        try:
            for item in future.result():
                if not isinstance(item, MediaItem):
                    logger.error("Service %s emitted item %s of type %s, skipping", service.__name__, item, item.__class__.__name__)
                    continue
                self.event_queue.put(Event(emitted_by=service, item=item))
        except Exception:
            logger.error("Service %s failed with exception %s", service.__name__, traceback.format_exc())

    def _submit_job(self, service: Service, item: MediaItem | None) -> None:
        logger.debug(
            f"Submitting service {service.__name__} to the pool" +
            (f" with {getattr(item, 'log_string', None) or item.item_id}" if item else "")
        )
        func = self.services[service].run
        future = self.executor.submit(func) if item is None else self.executor.submit(func, item)
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
            existing_item = self.media_items.get(event.item.item_id, None)
            func = (
                process_event_and_collect_coverage 
                if self.startup_args.profile_state_transitions 
                else process_event
            )
            updated_item, next_service, items_to_submit = func(
                existing_item, event.emitted_by, event.item
            )

            # before submitting the item to be processed, commit it to the container
            if updated_item:
                self.media_items.upsert(updated_item)
                if updated_item.state == States.Completed:
                    logger.debug("%s %s has been completed", 
                        updated_item.__class__.__name__, updated_item.log_string
                    )

            for item_to_submit in items_to_submit:
                self._submit_job(next_service, item_to_submit)

    def validate(self):
        return any(
            service.initialized 
            for service in self.requesting_services.values()
        ) and all(
            service.initialized 
            for service in self.processing_services.values()
        )

    def stop(self):
        if hasattr(self, 'executor'):
            self.executor.shutdown(wait=True) 
        if hasattr(self, 'pickly'):
            self.pickly.stop()
        settings_manager.save()
        symlinker_service = self.processing_services.get(Symlinker)
        if symlinker_service:
            symlinker_service.stop_monitor()
        if hasattr(self, 'scheduler'):
            self.scheduler.shutdown(wait=False)  # Don't block, doesn't contain data to consume
        self.running = False


