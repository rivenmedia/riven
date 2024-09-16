import asyncio
from concurrent.futures import ThreadPoolExecutor, as_completed
import linecache
import os
import threading
import time
from datetime import datetime
from queue import Empty

from apscheduler.schedulers.background import BackgroundScheduler
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeRemainingColumn
from rich.live import Live

from program.content import Listrr, Mdblist, Overseerr, PlexWatchlist, TraktContent
from program.downloaders import Downloader
from program.indexers.trakt import TraktIndexer
from program.libraries import SymlinkLibrary
from program.libraries.symlink import fix_broken_symlinks
from program.media.item import Episode, MediaItem, Movie, Season, Show
from program.media.state import States
from program.post_processing import PostProcessing
from program.scrapers import Scraping
from program.settings.manager import settings_manager
from program.settings.models import get_version
from program.updaters import Updater
from utils import data_dir_path
from utils.logger import logger, log_cleaner
from utils.event_manager import EventManager
import utils.websockets.manager as ws_manager

from .state_transition import process_event
from .symlink import Symlinker
from .types import Event

if settings_manager.settings.tracemalloc:
    import tracemalloc

from sqlalchemy import and_, exists, func, select, or_
from sqlalchemy.orm import joinedload

import program.db.db_functions as DB
from program.db.db import db, run_migrations, vacuum_and_analyze_index_maintenance
from sqlalchemy import func, select, text


class Program(threading.Thread):
    """Program class"""

    def __init__(self):
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

    def initialize_services(self):

        self.requesting_services = {
            Overseerr: Overseerr(),
            PlexWatchlist: PlexWatchlist(),
            Listrr: Listrr(),
            Mdblist: Mdblist(),
            TraktContent: TraktContent(),
        }

        self.services = {
            TraktIndexer: TraktIndexer(),
            Scraping: Scraping(),
            Symlinker: Symlinker(),
            Updater: Updater(),
            Downloader: Downloader(),
            # Depends on Symlinker having created the file structure so needs
            # to run after it
            SymlinkLibrary: SymlinkLibrary(),
            PostProcessing: PostProcessing(),
        }

        self.all_services = {
            **self.requesting_services,
            **self.services
        }

        if len([service for service in self.requesting_services.values() if service.initialized]) == 0:
            logger.warning("No content services initialized, items need to be added manually.")
        if not self.services[Scraping].initialized:
            logger.error("No Scraping service initialized, you must enable at least one.")
        if not self.services[Downloader].initialized:
            logger.error("No Downloader service initialized, you must enable at least one.")
        if not self.services[Updater].initialized:
            logger.error("No Updater service initialized, you must enable at least one.")

        if self.enable_trace:
            self.last_snapshot = tracemalloc.take_snapshot()


    def validate(self) -> bool:
        """Validate that all required services are initialized."""
        return all(s.initialized for s in self.services.values())

    def validate_database(self) -> bool:
        """Validate that the database is accessible."""
        try:
            with db.Session() as session:
                session.execute(text("SELECT 1"))
                return True
        except Exception:
            logger.error(f"Database connection failed. Is the database running?")
            return False

    def start(self):
        latest_version = get_version()
        logger.log("PROGRAM", f"Riven v{latest_version} starting!")

        settings_manager.register_observer(self.initialize_services)
        os.makedirs(data_dir_path, exist_ok=True)

        if not settings_manager.settings_file.exists():
            logger.log("PROGRAM", "Settings file not found, creating default settings")
            settings_manager.save()

        self.initialize_services()

        max_worker_env_vars = [var for var in os.environ if var.endswith("_MAX_WORKERS")]
        if max_worker_env_vars:
            for var in max_worker_env_vars:
                logger.log("PROGRAM", f"{var} is set to {os.environ[var]} workers")

        if not self.validate():
            logger.log("PROGRAM", "----------------------------------------------")
            logger.error("Riven is waiting for configuration to start!")
            logger.log("PROGRAM", "----------------------------------------------")

        while not self.validate():
            time.sleep(1)

        if not self.validate_database():
            # We should really make this configurable via frontend...
            return

        run_migrations()
        self._init_db_from_symlinks()

        with db.Session() as session:
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
        logger.success("Riven is running!")
        ws_manager.send_health_update("running")
        self.initialized = True

    def _retry_library(self) -> None:
        count = 0
        with db.Session() as session:
            count = session.execute(
                select(func.count(MediaItem._id))
                .where(MediaItem.last_state.not_in([States.Completed, States.Unreleased]))
                .where(MediaItem.type.in_(["movie", "show"]))
            ).scalar_one()

        if count == 0:
            return

        logger.log("PROGRAM", f"Found {count} items to retry")

        number_of_rows_per_page = 10
        for page_number in range(0, (count // number_of_rows_per_page) + 1):
            with db.Session() as session:
                items_to_submit = []
                items_to_submit += session.execute(
                    select(MediaItem)
                    .where(MediaItem.last_state.not_in([States.Completed, States.Unreleased]))
                    .where(MediaItem.type.in_(["movie", "show"]))
                    .order_by(MediaItem.requested_at.desc())
                    .limit(number_of_rows_per_page)
                    .offset(page_number * number_of_rows_per_page)
                ).unique().scalars().all()

                session.expunge_all()
                session.close()
                for item in items_to_submit:
                    self.em.add_event(Event(emitted_by="RetryLibrary", item=item))

    def _schedule_functions(self) -> None:
        """Schedule each service based on its update interval."""
        scheduled_functions = {
            self._retry_library: {"interval": 60 * 10},
            log_cleaner: {"interval": 60 * 60},
            vacuum_and_analyze_index_maintenance: {"interval": 60 * 60 * 24},
        }

        if settings_manager.settings.symlink.repair_symlinks:
            scheduled_functions[fix_broken_symlinks] = {
                "interval": 60 * 60 * settings_manager.settings.symlink.repair_interval,
                "args": [settings_manager.settings.symlink.library_path, settings_manager.settings.symlink.rclone_path]
            }

        if settings_manager.settings.post_processing.subliminal.enabled:
            pass
            # scheduled_functions[self._download_subtitles] = {"interval": 60 * 60 * 24}
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
        """Schedule each service based on its update interval."""
        scheduled_services = {**self.requesting_services, SymlinkLibrary: self.services[SymlinkLibrary]}
        for service_cls, service_instance in scheduled_services.items():
            if not service_instance.initialized:
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
                next_run_time=datetime.now() if service_cls != SymlinkLibrary else None,
                coalesce=False,
            )
            logger.debug(f"Scheduled {service_cls.__name__} to run every {update_interval} seconds.")

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
        while self.initialized:
            if not self.validate():
                time.sleep(1)
                continue

            try:
                event: Event = self.em.next()
                self.em.add_event_to_running(event)
                if self.enable_trace:
                    self.dump_tracemalloc()
            except Empty:
                if self.enable_trace:
                    self.dump_tracemalloc()
                time.sleep(0.1)
                continue


            with db.Session() as session:
                existing_item: MediaItem | None = DB._get_item_from_db(session, event.item)
                processed_item, next_service, items_to_submit = process_event(
                    existing_item, event.emitted_by, existing_item if existing_item is not None else event.item
                )

                self.em.remove_item_from_running(event.item)

                if items_to_submit:
                    for item_to_submit in items_to_submit:
                        if not next_service:
                            self.em.add_event_to_queue(Event("StateTransition", item_to_submit))
                        else:
                            event = Event(next_service.__name__, item_to_submit)
                            self.em.add_event_to_running(Event(next_service.__name__, item_to_submit))
                            self.em.submit_job(next_service, self, event)
                if isinstance(processed_item, MediaItem):
                    processed_item.store_state()
                session.commit()

    def stop(self):
        if not self.initialized:
            return

        if hasattr(self, "executors"):
            for executor in self.executors:
                if not executor["_executor"]._shutdown:
                    executor["_executor"].shutdown(wait=False)
        if hasattr(self, "scheduler") and self.scheduler.running:
            self.scheduler.shutdown(wait=False)
        logger.log("PROGRAM", "Riven has been stopped.")

    # def _init_db_from_symlinks(self):
    #     with db.Session() as session:
    #         res = session.execute(select(func.count(MediaItem._id))).scalar_one()
    #         added = []
    #         if res == 0:
    #             logger.log("PROGRAM", "Collecting items from symlinks")
    #             items = self.services[SymlinkLibrary].run()
    #             logger.log("PROGRAM", f"Found {len(items)} symlinks to add to database")
    #             if settings_manager.settings.map_metadata:
    #                 console = Console()
    #                 progress = Progress(
    #                     SpinnerColumn(),
    #                     TextColumn("[progress.description]{task.description}"),
    #                     BarColumn(),
    #                     TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
    #                     TimeRemainingColumn(),
    #                     console=console,
    #                     transient=True,
    #                 )

    #                 task = progress.add_task("Enriching items with metadata", total=len(items))
    #                 with Live(progress, console=console, refresh_per_second=10):
    #                     for item in items:
    #                         if isinstance(item, (Movie, Show)):
    #                             try:
    #                                 enhanced_item = next(self.services[TraktIndexer].run(item, log_msg=False))
    #                             except StopIteration as e:
    #                                 logger.error(f"Failed to enhance metadata for {item.title} ({item.item_id}): {e}")
    #                                 continue
    #                             if enhanced_item.item_id in added:
    #                                 logger.error(f"Cannot enhance metadata, {item.title} ({item.item_id}) contains multiple folders. Manual resolution required. Skipping.")
    #                                 continue
    #                             added.append(enhanced_item.item_id)
    #                             enhanced_item.store_state()
    #                             session.add(enhanced_item)
    #                             progress.update(task, advance=1)
    #                 session.commit()
    #             logger.log("PROGRAM", "Database initialized")

    def _enhance_item(self, item: MediaItem) -> MediaItem | None:
        try:
            enhanced_item = next(self.services[TraktIndexer].run(item, log_msg=False))
            return enhanced_item
        except StopIteration as e:
            logger.error(f"Failed to enhance metadata for {item.title} ({item.item_id}): {e}")
            return None

    def _init_db_from_symlinks(self):
        with db.Session() as session:
            res = session.execute(select(func.count(MediaItem._id))).scalar_one()
            added = []
            errors = []
            if res == 0:
                logger.log("PROGRAM", "Collecting items from symlinks")
                items = self.services[SymlinkLibrary].run()
                logger.log("PROGRAM", f"Found {len(items)} Movie and Show symlinks to add to database")
                if settings_manager.settings.map_metadata:
                    console = Console()
                    progress = Progress(
                        SpinnerColumn(),
                        TextColumn("[progress.description]{task.description}"),
                        BarColumn(),
                        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
                        TimeRemainingColumn(),
                        console=console,
                        transient=True,
                    )

                    task = progress.add_task("Enriching items with metadata", total=len(items))
                    with Live(progress, console=console, refresh_per_second=10):
                        with ThreadPoolExecutor(max_workers=4) as executor:
                            future_to_item = {executor.submit(self._enhance_item, item): item for item in items if isinstance(item, (Movie, Show))}
                            for future in as_completed(future_to_item):
                                item = future_to_item[future]
                                try:
                                    enhanced_item = future.result()
                                    if enhanced_item:
                                        if enhanced_item.item_id in added:
                                            errors.append(f"Duplicate symlink found for {item.title} ({item.item_id}), skipping...")
                                            continue
                                        else:
                                            added.append(enhanced_item.item_id)
                                            enhanced_item.store_state()
                                            session.add(enhanced_item)
                                except Exception as e:
                                    errors.append(f"Error processing {item.title} ({item.item_id}): {e}")
                                finally:
                                    progress.update(task, advance=1)
                    session.commit()

                if errors:
                    logger.error("Errors encountered during initialization")
                    for error in errors:
                        logger.error(error)

                logger.log("PROGRAM", "Database initialized")