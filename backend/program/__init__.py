"""Program main module"""
import os
import threading
import time
import traceback

from concurrent.futures import ThreadPoolExecutor, Future
from datetime import datetime
from queue import Queue, Empty
from typing import Union, get_args, Generator, Callable
from dataclasses import dataclass

from pydantic import BaseModel
from apscheduler.schedulers.background import BackgroundScheduler

from program.content import Overseerr, PlexWatchlist, Listrr, Mdblist
from program.metadata.trakt import TraktMetadata
from program.media.container import MediaItemContainer
from program.media.item import MediaItem, Show, Season, Movie, Episode
from program.media.state import States
from program.plex import PlexLibrary
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
Service = Union[Content, PlexLibrary, Scraper, Debrid, Symlinker]
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
            debug=settings_manager.settings.debug, log=settings_manager.settings.log
        )

    def start(self):
        logger.info("Iceberg v%s starting!", settings_manager.settings.version)
        self.initialized = False
        self.job_queue = Queue()
        os.makedirs(data_dir_path, exist_ok=True)

        self.media_items = MediaItemContainer()
        if not self.startup_args.dev:
            self.pickly = Pickly(self.media_items, data_dir_path)
            self.pickly.start()
        try:
            self.content_services = {
                PlexLibrary: PlexLibrary(), 
                Overseerr: Overseerr(), 
                PlexWatchlist: PlexWatchlist(), 
                Listrr: Listrr(), 
                Mdblist: Mdblist(),
            }
            self.metadata_services = {
                TraktMetadata: TraktMetadata()
            }
            self.processing_services = {
                Scraping: Scraping(), 
                Debrid: Debrid(), 
                Symlinker: Symlinker(),
                PlexUpdater: PlexUpdater()
            }
            self.services = {
                **self.metadata_services,
                **self.content_services,
                **self.processing_services
            }
        except Exception as e:
            raise
        # seed initial MIC with Library State
        for item in self.services[PlexLibrary].run():
            self.media_items.append(item)

        if self.validate():
            logger.info("Iceberg started!")
        else:
            logger.info("----------------------------------------------")
            logger.info("Iceberg is waiting for configuration to start!")
            logger.info("----------------------------------------------")
        self.scheduler = BackgroundScheduler()
        self.executor = ThreadPoolExecutor(thread_name_prefix="Worker") 
        self._schedule_services()
        super().start()
        self.scheduler.start()
        self.running = True
        self.initialized = True

    def _schedule_services(self) -> None:
        """Schedule each service based on its update interval."""
        for service_cls, service_instance in self.content_services.items():
            if not service_instance.initialized:
                logger.info("Not scheduling %s due to not being initialized", service_cls.__name__)
                continue
            update_interval = service_instance.settings.update_interval
            self.scheduler.add_job(
                self._submit_job,
                'interval',
                seconds=update_interval,
                args=[service_cls, None],
                id=f'{service_cls.__name__}_update',
                max_instances=1,
                replace_existing=True,  # Replace existing jobs with the same ID
                next_run_time=datetime.now()
            )
            logger.info("Scheduled %s to run every %s seconds.", service_cls.__name__, update_interval)
        return None

    def _process_future_item(self, future: Future, service: Service, input_item: MediaItem) -> None:
        try:
            for item in future.result():
                if item is None:
                    continue
                self.job_queue.put(Event(emitted_by=service, item=item))
                break
            else:
                logger.debug("No results from submitting %s to %s", getattr(input_item, 'title', None), service.__name__)
        except Exception as e:
            logger.error("Service %s failed with exception %s", service.__name__, traceback.format_exc())

    def _service_run_item(self, func: Callable, item: MediaItem | None) -> MediaItemGenerator:
        if item is None:
            yield from func()
            return None
        yield from func(item)
        
    def _submit_job(self, service: Service, item: MediaItem | None) -> None:
        logger.debug(
            f"Submitting service {service.__name__} to the pool" +
            (f" with {item.title}" if item else "")
        )
        func = self.services[service].run
        future = self.executor.submit(self._service_run_item, func, item)
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
            if not isinstance(item, MediaItem):
                logger.error("Service %s emitted item %s of type %s", service.__name__, item, item.__class__.__name__)
                continue
            # update database to current state
            item = self.media_items.append(item)
            if service in get_args(Content):
                if not getattr(item, 'title', None):
                    next_service = TraktMetadata
                    items_to_submit = [item]
                else:
                    next_service = Scraping
                    items_to_submit = [item]
            elif service == TraktMetadata:
                next_service = Scraping
                items_to_submit = [item]
            elif service == Scraping:
                if item.streams:
                    next_service = Debrid
                    items_to_submit = [item]
                # if we didn't get a stream then we have to dive into the components
                # and try to get a stream for each one separately
                elif isinstance(item, Show):
                    next_service = Scraping
                    items_to_submit = item.seasons
                elif isinstance(item, Season):
                    next_service = Scraping
                    items_to_submit = item.episodes
            elif service == Debrid:
                next_service =  Symlinker
                if isinstance(item, Season):
                    items_to_submit = [e for e in item.episodes]
                elif isinstance(item, (Movie, Episode)):
                    items_to_submit = [item]
                items_to_submit = filter(lambda i: i.folder and i.file, items_to_submit)
                if not items_to_submit:
                    continue
            elif service == Symlinker:
                if item.symlinked:
                    items_to_submit = [item]
                next_service = PlexUpdater
            elif service == PlexUpdater:
                continue

            for item in items_to_submit:
                self._submit_job(next_service, item)

    def validate(self):
        return any(
            service.initialized 
            for service in self.content_services.values()
        ) and all(
            service.initialized 
            for service in self.processing_services.values()
        )

    def stop(self):
        if hasattr(self, 'pickly'):
            self.pickly.stop()
        settings_manager.save()
        self.scheduler.shutdown(wait=False)  # Don't block, doesn't contain data to consume
        self.executor.shutdown(wait=True)  # Shutdown the executor
        self.running = False
