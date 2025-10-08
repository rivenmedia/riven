"""
Riven Program - Main application orchestrator.

This module contains the Program class which:
- Initializes and manages all services (content, indexers, scrapers, downloaders, etc.)
- Manages the event queue and state machine
- Schedules periodic tasks (retry library, update ongoing, new releases, maintenance)
- Processes MediaItem and MediaEntry events through the state machine
- Handles database initialization and migrations
- Provides tracemalloc debugging support

The Program runs as a thread and continuously processes events from the EventManager,
routing them through the appropriate services based on the state machine logic.
"""
import linecache
import os
import threading
import time
from datetime import datetime
from queue import Empty

from apscheduler.schedulers.background import BackgroundScheduler
from kink import di

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
from program.services.indexers import IndexerService, TMDBIndexer, TVDBIndexer
from program.services.post_processing import PostProcessing
from program.services.scrapers import Scraping
from program.services.updaters import Updater
from program.services.entry_creator import EntryCreator
from program.services.notifier import Notifier
from program.settings.manager import settings_manager
from program.settings.models import get_version
from program.utils import data_dir_path
from program.utils.logging import log_cleaner, logger

from .state_transition import process_event
from .services.filesystem import FilesystemService
from .types import Event

if settings_manager.settings.tracemalloc:
    import tracemalloc

from sqlalchemy import func, select, text

from program.db import db_functions
from program.db.db import (
    create_database_if_not_exists,
    db,
    run_migrations,
    dev_reset_database,
    vacuum_and_analyze_index_maintenance,
)


class Program(threading.Thread):
    """
    Main Riven application orchestrator.

    Manages the entire application lifecycle:
    - Service initialization and scheduling
    - Event queue processing
    - State machine transitions
    - Database management
    - Background task scheduling

    Runs as a thread that continuously processes events from the EventManager,
    routing MediaItem and MediaEntry events through the appropriate services.
    """

    def __init__(self):
        """
        Initialize the Program.

        Sets up:
        - Thread name
        - EventManager for event queue
        - Tracemalloc debugging (if enabled)
        - Service dictionaries (populated later)
        """
        super().__init__(name="Riven")
        self.initialized = False
        self.running = False
        self.services = {}
        self.enable_trace = settings_manager.settings.tracemalloc
        self.em = EventManager()
        if self.enable_trace:
            tracemalloc.start()
            self.malloc_time = time.monotonic()-50
            self.last_snapshot = None

    def initialize_apis(self):
        """Initialize external API integrations (Plex, Overseerr, etc.)."""
        bootstrap_apis()

    def initialize_services(self):
        """
        Initialize all Riven services.

        Creates instances of:
        - Content services (Overseerr, PlexWatchlist, Listrr, Mdblist, TraktContent)
        - Indexers (TMDB, TVDB)
        - Core services (Scraping, Downloader, FilesystemService, PostProcessing, EntryCreator, Notifier)

        Services are registered with dependency injection and stored in service dictionaries.
        Settings observers trigger reinitialization when settings change.
        """
        self.requesting_services = {
            Overseerr: Overseerr(),
            PlexWatchlist: PlexWatchlist(),
            Listrr: Listrr(),
            Mdblist: Mdblist(),
            TraktContent: TraktContent(),
        }

        tmdb_indexer = TMDBIndexer()
        tvdb_indexer = TVDBIndexer()
        di[TMDBIndexer] = tmdb_indexer
        di[TVDBIndexer] = tvdb_indexer
        composite_indexer = IndexerService()

        # Instantiate services fresh on each settings change; settings_manager observers handle reinit
        _downloader = Downloader()
        self.services = {
            IndexerService: composite_indexer,
            Scraping: Scraping(),
            Updater: Updater(),
            Downloader: _downloader,
            FilesystemService: FilesystemService(_downloader),
            PostProcessing: PostProcessing(),
            EntryCreator: EntryCreator(),
            Notifier: Notifier(),
        }

        self.all_services = {
            **self.requesting_services,
            **self.services,
            TMDBIndexer: tmdb_indexer,
            TVDBIndexer: tvdb_indexer,
        }

        if len([service for service in self.requesting_services.values() if service.initialized]) == 0:
            logger.warning("No content services initialized, items need to be added manually.")
        if not self.services[Scraping].initialized:
            logger.error("No Scraping service initialized, you must enable at least one.")
        if not self.services[Downloader].initialized:
            logger.error("No Downloader service initialized, you must enable at least one.")
        if not self.services[FilesystemService].initialized:
            logger.error("Filesystem service failed to initialize, check your settings.")
        if not self.services[Updater].initialized:
            logger.error("No Updater service initialized, you must enable at least one.")

        if self.enable_trace:
            self.last_snapshot = tracemalloc.take_snapshot()


    def validate(self) -> bool:
        """
        Validate that all required services are initialized.

        Returns:
            bool: True if all services are initialized, False otherwise.
        """
        return all(s.initialized for s in self.services.values())

    def validate_database(self) -> bool:
        """
        Validate that the database is accessible.

        Returns:
            bool: True if database connection succeeds, False otherwise.
        """
        try:
            with db.Session() as session:
                session.execute(text("SELECT 1"))
                return True
        except Exception:
            logger.error("Database connection failed. Is the database running?")
            return False

    def start(self, dev_reset_db: bool = False):
        """
        Start the Riven program: ensure configuration and database readiness, initialize APIs and services, schedule background jobs, and start the main thread and scheduler.

        This method prepares runtime state and external integrations by registering settings observers, creating the data directory and default settings if missing, initializing APIs and services after database migrations, computing and logging item counts (including filesystem-backed items), configuring executors and the background scheduler, scheduling periodic service and maintenance tasks, starting the thread and scheduler, and marking the program as initialized.

        Parameters:
            dev_reset_db (bool): If True, drop all tables and recreate from models without migrations (DEV ONLY!)
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

        if not self.validate():
            logger.log("PROGRAM", "----------------------------------------------")
            logger.error("Riven is waiting for configuration to start!")
            logger.log("PROGRAM", "----------------------------------------------")

        while not self.validate():
            time.sleep(1)

        if not self.validate_database():
            # We should really make this configurable via frontend...
            logger.log("PROGRAM", "Database not found, trying to create database")
            if not create_database_if_not_exists():
                logger.error("Failed to create database, exiting")
                return
            logger.success("Database created successfully")

        # Handle dev mode database reset
        if dev_reset_db:
            dev_reset_database()
        else:
            run_migrations()

        # Initialize services AFTER database schema is ready
        self.initialize_services()

        with db.Session() as session:
            # Count items with filesystem entries
            # Use exists() to check if any filesystem_entries exist for the item
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
            total_episodes = session.execute(select(func.count(Episode.id))).scalar_one()
            total_items = session.execute(select(func.count(MediaItem.id))).scalar_one()

            logger.log("ITEM", f"Movies: {total_movies} (With filesystem: {movies_with_fs})")
            logger.log("ITEM", f"Shows: {total_shows}")
            logger.log("ITEM", f"Seasons: {total_seasons}")
            logger.log("ITEM", f"Episodes: {total_episodes} (With filesystem: {episodes_with_fs})")
            logger.log("ITEM", f"Total Items: {total_items} (With filesystem: {total_with_fs})")

        self.executors = []
        self.scheduler = BackgroundScheduler()
        self._schedule_services()
        self._schedule_functions()

        super().start()
        self.scheduler.start()
        logger.success("Riven is running!")
        self.initialized = True

    def _retry_library(self) -> None:
        """
        Retry items that failed to download.

        Queries database for incomplete items and re-enqueues them for processing.
        Scheduled to run every 24 hours.
        """
        with db.Session() as session:
            item_ids = db_functions.retry_library(session)
            for item_id in item_ids:
                self.em.add_event(Event(emitted_by="RetryLibrary", item_id=item_id))

            if item_ids:
                logger.log("PROGRAM", f"Successfully retried {len(item_ids)} incomplete items")
            else:
                logger.log("NOT_FOUND", "No items required retrying")

    def _update_ongoing(self) -> None:
        """
        Update state for ongoing and unreleased items.

        Checks for shows/seasons with new episodes or state changes.
        Scheduled to run every 4 hours.
        """
        with db.Session() as session:
            updated_items = db_functions.update_ongoing(session)
            for item_id in updated_items:
                self.em.add_event(Event(emitted_by="UpdateOngoing", item_id=item_id))

            if updated_items:
                logger.log("PROGRAM", f"Successfully updated {len(updated_items)} items with a new state")
            else:
                logger.log("NOT_FOUND", "No ongoing items required state updates")

    def _update_new_releases(self) -> None:
        """
        Update state for new releases.

        Checks for newly released episodes in the last 24 hours.
        Scheduled to run every hour.
        """
        with db.Session() as session:
            changed_items = db_functions.update_new_releases(session, update_type="episodes", hours=24)
            for item_id in changed_items:
                self.em.add_event(Event(emitted_by="UpdateNewReleases", item_id=item_id))

            if changed_items:
                logger.log("PROGRAM", f"Successfully fetched {len(changed_items)} new releases")
            else:
                logger.log("NOT_FOUND", "No new releases found")

    def _schedule_functions(self) -> None:
        """
        Schedule periodic maintenance and update functions.

        Schedules:
        - _update_ongoing: Every 4 hours (check for state changes)
        - _retry_library: Every 24 hours (retry failed items)
        - _update_new_releases: Every hour (check for new episodes)
        - log_cleaner: Every hour (clean old logs)
        - vacuum_and_analyze_index_maintenance: Every 24 hours (database maintenance)
        """
        scheduled_functions = {
            self._update_ongoing: {"interval": 60 * 60 * 4},
            self._retry_library: {"interval": 60 * 60 * 24},
            self._update_new_releases: {"interval": 60 * 60},
            log_cleaner: {"interval": 60 * 60},
            vacuum_and_analyze_index_maintenance: {"interval": 60 * 60 * 24},
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
            logger.debug(f"Scheduled {func.__name__} to run every {config['interval']} seconds.")

    def _schedule_services(self) -> None:
        """
        Schedule content services based on their update intervals.

        Services can run in two modes:
        - Webhook mode: Run once at startup, then triggered by webhooks
        - Polling mode: Run periodically based on update_interval setting
        """
        scheduled_services = {**self.requesting_services}
        for service_cls, service_instance in scheduled_services.items():
            if not service_instance.initialized:
                continue

            # If the service supports webhooks and webhook mode is enabled, run it once now and do not schedule periodically
            use_webhook = getattr(getattr(service_instance, "settings", object()), "use_webhook", False)
            if use_webhook:
                self.scheduler.add_job(
                    self.em.submit_job,
                    "date",
                    run_date=datetime.now(),
                    args=[service_cls, self],
                    id=f"{service_cls.__name__}_update_once",
                    replace_existing=True,
                    misfire_grace_time=30,
                )
                logger.debug(f"Scheduled {service_cls.__name__} to run once (webhook mode enabled).")
                continue

            if not (update_interval := getattr(service_instance.settings, "update_interval", False)):
                continue

            self.scheduler.add_job(
                self.em.submit_job,
                "interval",
                seconds=update_interval,
                args=[service_cls, self],
                id=f"{service_cls.__name__}_update",
                max_instances=1,
                replace_existing=True,
                next_run_time=datetime.now(),
                coalesce=False,
            )
            logger.debug(f"Scheduled {service_cls.__name__} to run every {update_interval} seconds.")

    def display_top_allocators(self, snapshot, key_type="lineno", limit=10):
        """
        Display top memory allocators for debugging.

        Args:
            snapshot: Tracemalloc snapshot to analyze.
            key_type: Type of grouping (default: "lineno").
            limit: Number of top allocators to display (default: 10).
        """
        import psutil
        process = psutil.Process(os.getpid())
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
            logger.debug("%s other: %.1f MiB" % (len(other), size / (1024 * 1024)))
        total = sum(stat.size for stat in top_stats)
        logger.debug("Total allocated size: %.1f MiB" % (total / (1024 * 1024)))
        logger.debug(f"Process memory: {process.memory_info().rss / (1024 * 1024):.2f} MiB")

    def dump_tracemalloc(self):
        """
        Dump tracemalloc snapshot every 60 seconds (if enabled).

        Used for debugging memory leaks and allocation patterns.
        """
        if time.monotonic() - self.malloc_time > 60:
            self.malloc_time = time.monotonic()
            snapshot = tracemalloc.take_snapshot()
            self.display_top_allocators(snapshot)

    def run(self):
        """
        Main event processing loop.

        Continuously processes events from the EventManager queue:
        1. Fetch next event from queue
        2. Determine if it's a MediaEntry or MediaItem event
        3. Load existing item/entry from database (if ID provided)
        4. Call state transition logic to determine next service
        5. Submit items/entries to next service or back to queue

        Runs until Program is stopped.
        """
        while self.initialized:
            if not self.validate():
                time.sleep(1)
                continue

            try:
                event: Event = self.em.next()
                if self.enable_trace:
                    self.dump_tracemalloc()
            except Empty:
                if self.enable_trace:
                    self.dump_tracemalloc()
                time.sleep(0.1)
                continue

            # Check if this is a MediaEntry event or MediaItem event
            if event.is_entry_event:
                # Handle MediaEntry events
                from program.media.media_entry import MediaEntry
                from program.state_transition import process_entry_event

                existing_entry: MediaEntry = None
                if event.entry_id:
                    existing_entry = db_functions.get_entry_by_id(event.entry_id)

                next_service, entries_to_submit = process_entry_event(
                    event.emitted_by, existing_entry, event.content_entry
                )

                for entry_to_submit in entries_to_submit:
                    if not next_service:
                        self.em.add_event_to_queue(Event("StateTransition", entry_id=entry_to_submit.id))
                    else:
                        # Check if we're submitting a MediaEntry or MediaItem
                        from program.media.item import MediaItem
                        if isinstance(entry_to_submit, MediaEntry):
                            # Submit MediaEntry event
                            if entry_to_submit.id:
                                event = Event(next_service, entry_id=entry_to_submit.id)
                            else:
                                event = Event(next_service, content_entry=entry_to_submit)
                        elif isinstance(entry_to_submit, MediaItem):
                            # Submit MediaItem event (e.g., for PostProcessing)
                            if entry_to_submit.id:
                                event = Event(next_service, item_id=entry_to_submit.id)
                            else:
                                event = Event(next_service, content_item=entry_to_submit)
                        else:
                            logger.error(f"Unknown type to submit: {type(entry_to_submit)}")
                            continue

                        # Event will be added to running when job actually starts in submit_job
                        self.em.submit_job(next_service, self, event)
            else:
                # Handle MediaItem events - call state transition logic
                existing_item: MediaItem = db_functions.get_item_by_id(event.item_id)

                next_service, items_to_submit = process_event(
                    event.emitted_by, existing_item, event.content_item
                )

                # Submit items to next service
                for item_to_submit in items_to_submit:
                    if not next_service:
                        # No next service - add back to queue for state transition
                        self.em.add_event_to_queue(Event("StateTransition", item_id=item_to_submit.id))
                    else:
                        # Submit to next service
                        if item_to_submit.id:
                            # Item is in database, pass ID
                            event = Event(next_service, item_id=item_to_submit.id)
                        else:
                            # Item not in database yet, pass object
                            event = Event(next_service, content_item=item_to_submit)

                        # Event will be added to running when job actually starts in submit_job
                        self.em.submit_job(next_service, self, event)

    def stop(self):
        """
        Stop the Program gracefully.

        Shuts down:
        - Thread pool executors
        - Background scheduler
        - FilesystemService (unmounts VFS)
        """
        if not self.initialized:
            return

        if hasattr(self, "executors"):
            for executor in self.executors:
                if not executor["_executor"]._shutdown:
                    executor["_executor"].shutdown(wait=False)
        if hasattr(self, "scheduler") and self.scheduler.running:
            self.scheduler.shutdown(wait=False)

        self.services[FilesystemService].close()
        logger.log("PROGRAM", "Riven has been stopped.")

    def _enhance_item(self, item: MediaItem) -> MediaItem | None:
        """
        Enhance a MediaItem with additional metadata from indexers.

        Args:
            item: MediaItem to enhance.

        Returns:
            MediaItem | None: Enhanced item or None if enhancement failed.
        """
        try:
            enhanced_item = next(self.services[IndexerService].run(item, log_msg=False))
            return enhanced_item
        except StopIteration:
            return None


# Global Program instance
riven = Program()