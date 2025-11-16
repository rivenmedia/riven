from dataclasses import dataclass
import linecache
import os
import threading
import time
from queue import Empty

from program.apis import bootstrap_apis
from program.managers.event_manager import EventManager
from program.media.item import Episode, MediaItem, Movie, Season, Show
from program.media.filesystem_entry import FilesystemEntry
from program.services.content import (
    Listrr,
    Mdblist,
    Overseerr,
    PlexWatchlist,
    TraktContent,
)
from program.services.downloaders import Downloader
from program.services.indexers import IndexerService
from program.services.notifications import NotificationService
from program.services.post_processing import PostProcessing
from program.services.scrapers import Scraping
from program.services.updaters import Updater
from program.settings.manager import settings_manager
from program.settings.models import get_version
from program.utils import data_dir_path
from program.utils.logging import logger
from program.scheduling import ProgramScheduler
from program.core.runner import Runner
from program.core.content_service import ContentService

from .state_transition import process_event
from .services.filesystem import FilesystemService
from .types import Event

from sqlalchemy import func, select, text

from program.db import db_functions
from program.db.db import (
    create_database_if_not_exists,
    db,
    run_migrations,
)


@dataclass
class Services:
    overseerr: Overseerr
    plex_watchlist: PlexWatchlist
    listrr: Listrr
    mdblist: Mdblist
    trakt: TraktContent
    indexer: IndexerService
    scraping: Scraping
    updater: Updater
    downloader: Downloader
    filesystem: FilesystemService
    post_processing: PostProcessing
    notifications: NotificationService

    @property
    def enabled_services(self) -> list[Runner]:
        """Get a list of enabled services."""

        return [service for service in self.to_dict().values() if service.enabled]

    @property
    def initialized_services(self) -> list[Runner]:
        """Get a list of initialized services."""

        return [service for service in self.enabled_services if service.initialized]

    @property
    def content_services(self) -> list[ContentService]:
        """Get all services that are content services."""

        return [
            service
            for service in self.enabled_services
            if service.initialized and isinstance(service, ContentService)
        ]

    def to_dict(self) -> dict[str, Runner]:
        return self.__dict__

    def __getitem__(self, key: str) -> Runner:
        return getattr(self, key)


class Program(threading.Thread):
    """Program class"""

    def __init__(self):
        super().__init__(name="Riven")

        self.initialized = False
        self.running = False
        self.services = None
        self.enable_trace = settings_manager.settings.tracemalloc
        self.em = EventManager()

        if self.enable_trace:
            import tracemalloc

            tracemalloc.start()
            self.malloc_time = time.monotonic() - 50
            self.last_snapshot = None

    def initialize_apis(self):
        bootstrap_apis()

    def initialize_services(self):
        """Initialize all services."""

        # Instantiate services fresh on each settings change; settings_manager observers handle reinit
        _downloader = Downloader()

        self.services = Services(
            overseerr=Overseerr(),
            plex_watchlist=PlexWatchlist(),
            listrr=Listrr(),
            mdblist=Mdblist(),
            trakt=TraktContent(),
            indexer=IndexerService(),
            scraping=Scraping(),
            updater=Updater(),
            downloader=_downloader,
            filesystem=FilesystemService(_downloader),
            post_processing=PostProcessing(),
            notifications=NotificationService(),
        )

        if (
            len(
                [
                    service
                    for service in self.services.enabled_services
                    if service.initialized
                ]
            )
            == 0
        ):
            logger.warning(
                "No content services initialized, items need to be added manually."
            )

        if not self.services.scraping or not self.services.scraping.initialized:
            logger.error(
                "No Scraping service initialized, you must enable at least one."
            )

        if not self.services.downloader or not self.services.downloader.initialized:
            logger.error(
                "No Downloader service initialized, you must enable at least one."
            )

        if not self.services.filesystem or not self.services.filesystem.initialized:
            logger.error(
                "Filesystem service failed to initialize, check your settings."
            )

        if not self.services.updater or not self.services.updater.initialized:
            logger.error(
                "No Updater service initialized, you must enable at least one."
            )

        if self.enable_trace:
            import tracemalloc

            self.last_snapshot = tracemalloc.take_snapshot()

    @property
    def is_valid(self) -> bool:
        """Validate that all required services are initialized."""

        if not self.services:
            return True

        return all(s.initialized for s in self.services.enabled_services)

    def validate_database(self) -> bool:
        """Validate that the database is accessible."""
        try:
            with db.Session() as session:
                session.execute(text("SELECT 1"))
                return True
        except Exception:
            logger.error("Database connection failed. Is the database running?")
            return False

    def start(self):
        """
        Start the Riven program: ensure configuration and database readiness, initialize APIs and services, schedule background jobs, and start the main thread and scheduler.

        This method prepares runtime state and external integrations by registering settings observers, creating the data directory and default settings if missing, initializing APIs and services after database migrations, computing and logging item counts (including filesystem-backed items), configuring executors and the background scheduler, scheduling periodic service and maintenance tasks, starting the thread and scheduler, and marking the program as initialized.
        """

        latest_version = get_version()

        logger.log("PROGRAM", f"Riven v{latest_version} starting!")

        settings_manager.register_observer(self.initialize_apis)
        settings_manager.register_observer(self.initialize_services)

        os.makedirs(data_dir_path, exist_ok=True)

        if not settings_manager.settings_file.exists():
            logger.log("PROGRAM", "Settings file not found, creating default settings")
            settings_manager.save()

        self.initialize_apis()

        if not self.validate_database():
            # TODO: We should really make this configurable via frontend...
            logger.log("PROGRAM", "Database not found, trying to create database")
            if not create_database_if_not_exists():
                logger.error("Failed to create database, exiting")
                return
            logger.success("Database created successfully")

        run_migrations()

        self.initialize_services()

        with db.Session() as session:
            from sqlalchemy import exists

            movies_with_fs = session.execute(
                select(func.count(Movie.id)).where(
                    exists().where(FilesystemEntry.media_item_id == Movie.id)
                )
            ).scalar_one()
            episodes_with_fs = session.execute(
                select(func.count(Episode.id)).where(
                    exists().where(FilesystemEntry.media_item_id == Episode.id)
                )
            ).scalar_one()
            total_with_fs = movies_with_fs + episodes_with_fs
            total_movies = session.execute(select(func.count(Movie.id))).scalar_one()
            total_shows = session.execute(select(func.count(Show.id))).scalar_one()
            total_seasons = session.execute(select(func.count(Season.id))).scalar_one()
            total_episodes = session.execute(
                select(func.count(Episode.id))
            ).scalar_one()
            total_items = session.execute(select(func.count(MediaItem.id))).scalar_one()

            logger.log(
                "ITEM", f"Movies: {total_movies} (With filesystem: {movies_with_fs})"
            )
            logger.log("ITEM", f"Shows: {total_shows}")
            logger.log("ITEM", f"Seasons: {total_seasons}")
            logger.log(
                "ITEM",
                f"Episodes: {total_episodes} (With filesystem: {episodes_with_fs})",
            )
            logger.log(
                "ITEM", f"Total Items: {total_items} (With filesystem: {total_with_fs})"
            )

        self.executors = []
        self.scheduler_manager = ProgramScheduler(self)
        self.scheduler_manager.start()

        super().start()
        logger.success("Riven is running!")
        self.initialized = True

    def display_top_allocators(self, snapshot, key_type="lineno", limit=10):
        import psutil

        process = psutil.Process(os.getpid())
        top_stats = snapshot.compare_to(self.last_snapshot, "lineno")

        logger.debug("Top %s lines" % limit)

        for index, stat in enumerate(top_stats[:limit], 1):
            frame = stat.traceback[0]
            # replace "/path/to/module/file.py" with "module/file.py"
            filename = os.sep.join(frame.filename.split(os.sep)[-2:])
            logger.debug(
                "#%s: %s:%s: %.1f KiB"
                % (index, filename, frame.lineno, stat.size / 1024)
            )
            line = linecache.getline(frame.filename, frame.lineno).strip()

            if line:
                logger.debug("    %s" % line)

        other = top_stats[limit:]

        if other:
            size = sum(stat.size for stat in other)
            logger.debug("%s other: %.1f MiB" % (len(other), size / (1024 * 1024)))

        total = sum(stat.size for stat in top_stats)
        logger.debug("Total allocated size: %.1f MiB" % (total / (1024 * 1024)))
        logger.debug(
            f"Process memory: {process.memory_info().rss / (1024 * 1024):.2f} MiB"
        )

    def dump_tracemalloc(self):
        import tracemalloc

        if time.monotonic() - self.malloc_time > 60:
            self.malloc_time = time.monotonic()
            snapshot = tracemalloc.take_snapshot()
            self.display_top_allocators(snapshot)

    def run(self):
        while self.initialized:
            if not self.is_valid:
                time.sleep(1)
                continue

            try:
                event = self.em.next()

                if self.enable_trace:
                    self.dump_tracemalloc()
            except Empty:
                if self.enable_trace:
                    self.dump_tracemalloc()

                time.sleep(0.1)
                continue

            if event.item_id:
                existing_item = db_functions.get_item_by_id(event.item_id)
            else:
                existing_item = None

            processed_event = process_event(
                event.emitted_by,
                existing_item,
                event.content_item,
            )

            next_service = processed_event.service
            items_to_submit = processed_event.related_media_items

            logger.debug(f"Event processed: {processed_event}")

            for item_to_submit in items_to_submit:
                if not next_service:
                    self.em.add_event_to_queue(
                        Event(emitted_by="StateTransition", item_id=item_to_submit.id)
                    )
                else:
                    # We are in the database, pass on id.
                    if item_to_submit.id:
                        event = Event(next_service, item_id=item_to_submit.id)
                    # We are not, lets pass the MediaItem
                    else:
                        event = Event(next_service, content_item=item_to_submit)

                    # Event will be added to running when job actually starts in submit_job
                    self.em.submit_job(next_service, self, event)

    def stop(self):
        if not self.initialized:
            return

        if hasattr(self, "executors"):
            for executor in self.executors:
                if not executor["_executor"]._shutdown:
                    executor["_executor"].shutdown(wait=False)
        if hasattr(self, "scheduler_manager"):
            self.scheduler_manager.stop()

        if self.services:
            self.services.filesystem.close()

        logger.log("PROGRAM", "Riven has been stopped.")


riven = Program()
