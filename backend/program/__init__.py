"""Program main module"""
import os
import threading
import time
import traceback

from concurrent.futures import ThreadPoolExecutor, Future
from datetime import datetime
from queue import Queue, Empty
from typing import Union, Generator
from dataclasses import dataclass

from apscheduler.schedulers.background import BackgroundScheduler

from program.content import Overseerr, PlexWatchlist, Listrr, Mdblist
from program.indexers.trakt import TraktIndexer
from program.media.container import MediaItemContainer
from program.media.item import MediaItem, Show, Season, Movie, Episode
from program.media.state import States
from program.libaries import SymlinkLibrary
from program.realdebrid import Debrid
from program.scrapers import Scraping, Torrentio, Orionoid, Jackett
from program.settings.manager import settings_manager
from program.symlink import Symlinker
from program.updaters.plex import PlexUpdater
from utils import data_dir_path
from utils.logger import logger
from utils.utils import Pickly

# Typehint classes
Scraper = Union[Scraping, Torrentio, Orionoid, Jackett]
Content = Union[Overseerr, PlexWatchlist, Listrr, Mdblist]
Service = Union[Content, SymlinkLibrary, Scraper, Debrid, Symlinker]
MediaItemGenerator = Generator[MediaItem, None, MediaItem | None]

@dataclass
class Event:
    emitted_by: Service
    item: MediaItem

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
        self.job_queue = Queue()
        os.makedirs(data_dir_path, exist_ok=True)

        try:
            self.initialize_services()
        except Exception:
            logger.error(traceback.format_exc())

        self.media_items = MediaItemContainer()
        if not self.startup_args.dev:
            self.pickly = Pickly(self.media_items, data_dir_path)
            self.pickly.start()
        else:
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
            self.job_queue.put(Event(emitted_by=self.__class__, item=item))

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
                self.job_queue.put(Event(emitted_by=service, item=item))
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
                event: Event = self.job_queue.get(timeout=1)
            except Empty:
                # Unblock after waiting in case we are no longer supposed to be running
                continue
            service, item = event.emitted_by, event.item
            existing_item = self.media_items.get(item.item_id, None)
            # we always want to get metadata for content items before we compare to the container. 
            # we can't just check if the show exists we have to check if it's complete
            if service in (*self.library_services.keys(), *self.requesting_services.keys()):
                next_service = TraktIndexer
                # if we already have a copy of this item check if we even need to index it
                if existing_item and not TraktIndexer.should_submit(existing_item):
                    continue
                self._submit_job(next_service, item)
                continue
            elif service == TraktIndexer or item.state == States.Indexed:
                next_service = Scraping
                # grab a copy of the item in the container
                if existing_item and not existing_item.indexed_at:
                    # merge our fresh metadata item to make sure there aren't any
                    # missing seasons or episodes in our library copy
                    if isinstance(item, (Show, Season)):
                        existing_item.fill_in_missing_info(item)
                        existing_item.indexed_at = item.indexed_at
                        item = existing_item
                    # if after making sure we aren't missing any episodes check to 
                    # see if we need to process this, if not then skip
                    if item.state == States.Completed:
                        logger.debug("%s is already complete and in the Library, skipping.", item.title)
                        continue
                # we attemted to scrape it already and it failed, scraping each component
                if item.scraped_times:
                    if isinstance(item, Show):
                        items_to_submit = [s for s in item.seasons if s.state != States.Completed]
                    elif isinstance(item, Season):
                        items_to_submit = [e for e in item.episodes if e.state != States.Completed]
                elif self.services[Scraping].should_submit(item):
                    items_to_submit = [item]
                else:
                    items_to_submit = []
            # Only shows and seasons can be PartiallyCompleted.  This is also the last part of the state
            # processing that can can be at the show level
            elif item.state == States.PartiallyCompleted:
                next_service = Scraping
                if isinstance(item, Show):
                    items_to_submit = [s for s in item.seasons if s.state != States.Completed]
                elif isinstance(item, Season):
                    items_to_submit = [e for e in item.episodes if e.state != States.Completed]
            # if we successfully scraped the item then send it to debrid
            elif item.state == States.Scraped:
                next_service = Debrid
                items_to_submit = [item]
            elif item.state == States.Downloaded:
                next_service = Symlinker
                if isinstance(item, Season):
                    proposed_submissions = [e for e in item.episodes]
                elif isinstance(item, (Movie, Episode)):
                    proposed_submissions = [item]
                items_to_submit = []
                for item in proposed_submissions:
                    if not self.services[Symlinker].should_submit(item):
                        logger.error("Item %s rejected by Symlinker, skipping", item.log_string)
                    else:
                        items_to_submit.append(item)
            elif item.state == States.Symlinked:
                next_service = PlexUpdater
                if isinstance(item, Show):
                    items_to_submit = [s for s in item.seasons]
                if isinstance(item, Season):
                    items_to_submit = [e for e in item.episodes]
                else:
                    items_to_submit = [item]
            elif item.state == States.Completed:
                continue
            
            # commit the item to the container before submitting it to be processed
            self.media_items.upsert(item)

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
        if hasattr(self, 'pickly'):
            self.pickly.stop()
        settings_manager.save()
        symlinker_service = self.processing_services.get(Symlinker)
        if symlinker_service:
            symlinker_service.stop_monitor()
        if hasattr(self, 'scheduler'):
            self.scheduler.shutdown(wait=False)  # Don't block, doesn't contain data to consume
        if hasattr(self, 'executor'):
            self.executor.shutdown(wait=True) 
        self.running = False
