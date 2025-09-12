import linecache
import os
import threading
import time
from datetime import datetime
from typing import Any, Dict

from apscheduler.schedulers.background import BackgroundScheduler
from kink import di

from program.db.symlink_handler import _init_db_from_symlinks
from program.media.item import Episode, MediaItem, Movie, Season, Show
from program.queue.queue_manager import QueueManager
from program.service_manager import service_manager
from program.services.content import (
    Listrr,
    Mdblist,
    Overseerr,
    PlexWatchlist,
    TraktContent,
)
from program.services.downloaders import Downloader
from program.services.indexers import CompositeIndexer, TMDBIndexer, TVDBIndexer
from program.services.libraries.symlink import fix_broken_symlinks
from program.services.post_processing import PostProcessing
from program.services.scrapers import Scraping
from program.services.updaters import Updater
from program.settings.manager import settings_manager
from program.settings.models import get_version
from program.utils import data_dir_path
from program.utils.logging import log_cleaner, logger

from .symlink import Symlinker

if settings_manager.settings.tracemalloc:
    import tracemalloc

from sqlalchemy import func, select, text

from program.db import db_functions
from program.db.db import (
    create_database_if_not_exists,
    db,
    run_migrations,
    vacuum_and_analyze_index_maintenance,
)


class Program(threading.Thread):
    """Program class"""

    def __init__(self):
        super().__init__(name="Riven")
        self.initialized = False
        self.running = False
        self.services = {}
        self.scheduled_services = {}
        self.enable_trace = settings_manager.settings.tracemalloc
        self.qm = QueueManager()
        if self.enable_trace:
            tracemalloc.start()
            self.malloc_time = time.monotonic()-50
            self.last_snapshot = None

    def initialize_services(self):
        """Initialize all services."""
        # Initialize shared service manager and use its instances first
        # This registers APIs in the DI container that services depend on
        service_manager.initialize()
        
        self.requesting_services = {
            Overseerr: Overseerr(),
            PlexWatchlist: PlexWatchlist(),
            Listrr: Listrr(),
            Mdblist: Mdblist(),
            TraktContent: TraktContent(),
        }
        core_services = service_manager.get_services()

        self.services = {
            CompositeIndexer: core_services[CompositeIndexer],
            Scraping: core_services[Scraping],
            Symlinker: core_services[Symlinker],
            Updater: core_services[Updater],
            Downloader: core_services[Downloader],
            # Depends on Symlinker having created the file structure so needs
            # to run after it
            PostProcessing: core_services[PostProcessing],
        }

        self.all_services = {
            **self.requesting_services,
            **self.services,
            TMDBIndexer: di[TMDBIndexer],
            TVDBIndexer: di[TVDBIndexer],
        }

        if len([service for service in self.requesting_services.values() if service.initialized]) == 0:
            logger.warning("No content services initialized, items need to be added manually.")
        if not self.services[Scraping].initialized:
            logger.error("No Scraping service initialized, you must enable at least one.")
        if not self.services[Downloader].initialized:
            logger.error("No Downloader service initialized, you must enable at least one.")
        if not self.services[Updater].initialized:
            logger.error("No Updater service initialized, you must enable at least one.")

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
            logger.error("Database connection failed. Is the database running?")
            return False

    def validate_lavinmq(self) -> bool:
        """Validate that LavinMQ is accessible and ready."""
        try:
            import asyncio

            from program.queue.health import health_checker

            # Run the health check synchronously
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                health_status = loop.run_until_complete(health_checker.check_lavinmq_connection())
                return health_status.status == "healthy"
            finally:
                loop.close()
                
        except Exception as e:
            logger.error(f"LavinMQ validation failed: {e}")
            return False

    def start(self):
        latest_version = get_version()
        logger.log("PROGRAM", f"Riven v{latest_version} starting!")

        from program.queue.broker import setup_dramatiq_broker
        setup_dramatiq_broker()

        os.makedirs(data_dir_path, exist_ok=True)

        if not settings_manager.settings_file.exists():
            logger.log("PROGRAM", "Settings file not found, creating default settings")
            settings_manager.save()

        self.initialize_services()
        self._test_broker_connection()

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

        if not self.validate_lavinmq():
            logger.log("PROGRAM", "----------------------------------------------")
            logger.error("LavinMQ is not accessible! Waiting for LavinMQ to become available...")
            logger.log("PROGRAM", "Make sure LavinMQ is running and the URL is correct.")
            logger.log("PROGRAM", f"Current URL: {settings_manager.settings.lavinmq_url}")
            logger.log("PROGRAM", "Retrying every 10 seconds...")
            logger.log("PROGRAM", "----------------------------------------------")
            
            # Keep retrying until LavinMQ becomes available
            while not self.validate_lavinmq():
                logger.log("PROGRAM", "Waiting for LavinMQ... (retrying in 10 seconds)")
                time.sleep(10)

            logger.success("LavinMQ is available! Continuing startup...")

        # Indexer cache cleanup
        self._cleanup_cache()

        run_migrations()
        _init_db_from_symlinks()

        with db.Session() as session:
            movies_symlinks = session.execute(select(func.count(Movie.id)).where(Movie.symlinked == True)).scalar_one() # noqa
            episodes_symlinks = session.execute(select(func.count(Episode.id)).where(Episode.symlinked == True)).scalar_one() # noqa
            total_symlinks = movies_symlinks + episodes_symlinks
            total_movies = session.execute(select(func.count(Movie.id))).scalar_one()
            total_shows = session.execute(select(func.count(Show.id))).scalar_one()
            total_seasons = session.execute(select(func.count(Season.id))).scalar_one()
            total_episodes = session.execute(select(func.count(Episode.id))).scalar_one()
            total_items = session.execute(select(func.count(MediaItem.id))).scalar_one()

            logger.log("ITEM", f"Movies: {total_movies} (Symlinks: {movies_symlinks})")
            logger.log("ITEM", f"Shows: {total_shows}")
            logger.log("ITEM", f"Seasons: {total_seasons}")
            logger.log("ITEM", f"Episodes: {total_episodes} (Symlinks: {episodes_symlinks})")
            logger.log("ITEM", f"Total Items: {total_items} (Symlinks: {total_symlinks})")

        # Wait for Dramatiq workers to be ready (consumers attached) before scheduling jobs
        try:
            from program.queue.health import health_checker
            from program.queue.models import QUEUE_NAMES
            expected_queues = list(QUEUE_NAMES.values())
            timeout_seconds = int(os.getenv("RIVEN_WORKER_READY_TIMEOUT", "60"))
            min_consumers = int(os.getenv("RIVEN_MIN_CONSUMERS", "1"))
            degraded_on_timeout = os.getenv("RIVEN_DEGRADED_ON_WORKER_TIMEOUT", "1") != "0"

            logger.log(
                "PROGRAM",
                f"Waiting for workers to be ready up to {timeout_seconds}s...",
            )
            ready = health_checker.wait_for_workers_ready(
                expected_queues,
                min_consumers=min_consumers,
                timeout_seconds=timeout_seconds,
                poll_interval=1.0,
            )
            if not ready:
                if degraded_on_timeout:
                    logger.error("Workers not ready within timeout — starting in DEGRADED mode (queue submissions paused)")
                    self.qm.pause_processing()
                else:
                    logger.error("Workers not ready within timeout — exiting (set RIVEN_DEGRADED_ON_WORKER_TIMEOUT=1 to start in degraded mode)")
                    return
            else:
                # Ensure resumed if previously paused
                if self.qm.is_processing_paused():
                    self.qm.resume_processing()
                logger.success("Workers are ready — proceeding with service scheduling")
        except Exception as e:
            logger.error(f"Worker readiness check failed unexpectedly: {e}")
            # Be safe by pausing submissions; scheduler still runs but enqueues are skipped
            if not self.qm.is_processing_paused():
                self.qm.pause_processing()

        self.executors = []
        self.scheduler = BackgroundScheduler()
        self._schedule_services()
        self._schedule_functions()

        super().start()
        self.scheduler.start()

        logger.success("Riven is running!")
        self.initialized = True

    def _retry_library(self) -> None:
        """Retry items that failed to download."""
        with db.Session() as session:
            item_ids = db_functions.retry_library(session)
            for item_id in item_ids:
                # Get the item and submit for processing
                item = db_functions.get_item_by_id(item_id, session=session)
                if item:
                    self.qm.submit_item(item, "RetryLibrary")

            if item_ids:
                logger.log("PROGRAM", f"Successfully retried {len(item_ids)} incomplete items")
            else:
                logger.log("PROGRAM", "No items required retrying")

    def _update_ongoing(self) -> None:
        """Update state for ongoing and unreleased items."""
        with db.Session() as session:
            updated_items = db_functions.update_ongoing(session)
            for item_id in updated_items:
                # Get the item and submit for processing
                item = db_functions.get_item_by_id(item_id, session=session)
                if item:
                    self.qm.submit_item(item, "UpdateOngoing")

            if updated_items:
                logger.log("PROGRAM", f"Successfully updated {len(updated_items)} items with a new state")
            else:
                logger.log("PROGRAM", "No items required state updates")

    def _test_broker_connection(self) -> None:
        """Test connection to LavinMQ broker"""
        try:
            from program.queue.broker import test_broker_connection

            logger.log("PROGRAM", "Testing LavinMQ broker connection...")
            if test_broker_connection():
                logger.log("PROGRAM", "LavinMQ broker connection successful")
            else:
                logger.warning("Failed to connect to LavinMQ broker - workers may have connection issues")
        except Exception as e:
            logger.error(f"Error testing broker connection: {e}")
    
    def _cleanup_cache(self) -> None:
        """Cleanup expired indexer cache entries on startup"""
        try:
            from program.services.indexers.cache import tmdb_cache, tvdb_cache
            
            logger.log("PROGRAM", "Cleaning up expired cache entries...")
            
            # Cleanup expired entries
            tmdb_cleaned = tmdb_cache.clear_expired()
            tvdb_cleaned = tvdb_cache.clear_expired()
            
            total_cleaned = tmdb_cleaned + tvdb_cleaned
            
            if total_cleaned > 0:
                logger.success(f"Cleaned {total_cleaned} expired cache entries (TMDB: {tmdb_cleaned}, TVDB: {tvdb_cleaned})")
            
            # Log cache statistics
            tmdb_stats = tmdb_cache.get_stats()
            tvdb_stats = tvdb_cache.get_stats()
            
            logger.log("PROGRAM", f"Cache stats - TMDB: {tmdb_stats.get('active_entries', 0)} entries ({tmdb_stats.get('cache_size_mb', 0)}MB), TVDB: {tvdb_stats.get('active_entries', 0)} entries ({tvdb_stats.get('cache_size_mb', 0)}MB)")
            
        except Exception as e:
            logger.error(f"Cache cleanup failed: {e}")
    
    def _cleanup_queue_system(self) -> None:
        """Scheduled cleanup of queue system"""
        try:
            from program.queue.monitoring import dependency_manager, queue_monitor

            orphaned_cleaned = queue_monitor.cleanup_orphaned_jobs()
            old_cleaned = queue_monitor.cleanup_old_jobs()
            dependency_cleaned = dependency_manager.cleanup_old_jobs()
            
            # Handle None values safely
            total_cleaned = (orphaned_cleaned or 0) + (old_cleaned or 0) + (dependency_cleaned or 0)
            if total_cleaned > 0:
                logger.log("PROGRAM", f"Scheduled cleanup: {total_cleaned} jobs cleaned")
                
        except Exception as e:
            logger.error(f"Scheduled queue cleanup failed: {e}")
    
    def _check_lavinmq_health(self) -> None:
        """Periodic health check for LavinMQ to detect runtime issues."""
        try:
            if not self.validate_lavinmq():
                logger.warning("LavinMQ health check failed - service may be down")
                # Pause queue processing to prevent failed job submissions
                if not self.qm.is_processing_paused():
                    self.qm.pause_processing()
            else:
                # Resume processing if it was paused
                if self.qm.is_processing_paused():
                    self.qm.resume_processing()
        except Exception as e:
            logger.error(f"LavinMQ health check error: {e}")
            # Pause processing on any error
            if not self.qm.is_processing_paused():
                self.qm.pause_processing()

    def _schedule_functions(self) -> None:
        """Schedule each service based on its update interval."""
        scheduled_functions = {
            self._update_ongoing: {"interval": 60 * 60 * 4},
            self._retry_library: {"interval": 60 * 60 * 24},
            log_cleaner: {"interval": 60 * 60},
            vacuum_and_analyze_index_maintenance: {"interval": 60 * 60 * 24},
            self._check_lavinmq_health: {"interval": 60 * 5},  # Check every 5 minutes
            self._cleanup_queue_system: {"interval": 60 * 15},  # Cleanup every 15 minutes
        }

        if settings_manager.settings.symlink.repair_symlinks:
            scheduled_functions[fix_broken_symlinks] = {
                "interval": 60 * 60 * settings_manager.settings.symlink.repair_interval,
                "args": [settings_manager.settings.symlink.library_path, settings_manager.settings.symlink.rclone_path]
            }

        for scheduled_func, config in scheduled_functions.items():
            self.scheduler.add_job(
                scheduled_func,
                "interval",
                seconds=config["interval"],
                args=config.get("args"),
                id=f"{scheduled_func.__name__}",
                max_instances=config.get("max_instances", 1),
                replace_existing=True,
                next_run_time=datetime.now(),
                misfire_grace_time=30
            )
            logger.debug(f"Scheduled {scheduled_func.__name__} to run every {config['interval']} seconds.")

    def _schedule_services(self) -> None:
        """Schedule each service based on its update interval."""
        self.scheduled_services = {**self.requesting_services}
        for service_cls, service_instance in self.scheduled_services.items():
            if not service_instance.initialized:
                continue
            if not (update_interval := getattr(service_instance.settings, "update_interval", False)):
                continue

            self.scheduler.add_job(
                self._run_scheduled_service,
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

    def _run_scheduled_service(self, service_cls, program):
        """Run a scheduled service (replaces EventManager.submit_job)"""
        try:
            service_instance = program.scheduled_services[service_cls]
            logger.debug(f"Running scheduled service {service_cls.__name__}")

            service_results = service_instance.run()
            if service_results:
                # Convert generator to list to handle it properly
                items = list(service_results) if hasattr(service_results, "__iter__") else [service_results]
                for item in items:
                    if isinstance(item, MediaItem):
                        self.qm.submit_item(item, service_cls.__name__)
                    elif isinstance(item, list):
                        for media_item in item:
                            if isinstance(media_item, MediaItem):
                                self.qm.submit_item(media_item, service_cls.__name__)
            
            # Check if service should be removed from scheduling after this run
            # This handles cases like Overseerr with webhook mode enabled
            if hasattr(service_instance, 'settings') and hasattr(service_instance.settings, 'use_webhook'):
                if service_instance.settings.use_webhook and hasattr(service_instance, 'run_once') and service_instance.run_once:
                    self._remove_service_from_scheduler(service_cls)
                    
        except Exception as e:
            logger.error(f"Error running scheduled service {service_cls.__name__}: {e}")

    def _remove_service_from_scheduler(self, service_cls):
        """Remove a service from the scheduler and scheduled_services dict."""
        try:
            # Remove from APScheduler
            job_id = f"{service_cls.__name__}_update"
            if self.scheduler.get_job(job_id):
                self.scheduler.remove_job(job_id)
                logger.debug(f"Removed job {job_id} from scheduler")
            
            # Remove from scheduled_services dict
            if service_cls in self.scheduled_services:
                del self.scheduled_services[service_cls]
                logger.debug(f"Removed {service_cls.__name__} from scheduled_services")
                
        except Exception as e:
            logger.error(f"Error removing {service_cls.__name__} from scheduler: {e}")

    def display_top_allocators(self, snapshot, _key_type="lineno", limit=10):
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
        if time.monotonic() - self.malloc_time > 60:
            self.malloc_time = time.monotonic()
            snapshot = tracemalloc.take_snapshot()
            self.display_top_allocators(snapshot)

    def run(self):
        """Main program loop - simplified for Dramatiq"""
        while self.initialized:
            if not self.validate():
                time.sleep(1)
                continue

            # With Dramatiq, we don't need to process events manually
            # The Dramatiq workers handle job processing
            # We just need to keep the main thread alive
            if self.enable_trace:
                self.dump_tracemalloc()
            
            time.sleep(1)  # Sleep to prevent busy waiting

    def add_item(self, item: MediaItem, service: str = "Manual") -> bool:
        """Add an item for processing (replaces EventManager.add_item)"""
        return self.qm.submit_item(item, service)

    def get_queue_status(self) -> Dict[str, Any]:
        """Get current queue status"""
        return self.qm.get_queue_status()
    
    def test_workers(self) -> Dict[str, Any]:
        """Test if Dramatiq workers are running by submitting a test job"""
        try:
            from datetime import datetime

            from program.queue.models import JobType, create_job_message

            # Create a test job message
            test_job = create_job_message(
                job_type=JobType.INDEX,
                payload_kind="content_item",
                content_item_data={
                    "title": "Test Worker Job",
                    "type": "movie",
                    "tmdb_id": 999999,
                    "year": 2024,
                    "requested_by": "TestUser",
                    "requested_at": datetime.now().isoformat(),
                },
                emitted_by="WorkerTest",
                priority=1,
            )
            
            # Submit the test job
            success = self.qm.submit_job(test_job)
            
            if success:
                logger.info(f"Test job {test_job.job_id} submitted successfully")
                return {
                    "status": "success",
                    "message": f"Test job {test_job.job_id} submitted successfully",
                    "job_id": test_job.job_id,
                    "note": "Check logs to see if workers process this job"
                }
            else:
                logger.warning("Failed to submit test job")
                return {
                    "status": "failed",
                    "message": "Failed to submit test job",
                    "note": "Workers may not be running or broker is not connected"
                }
                
        except Exception as e:
            logger.error(f"Worker test failed: {e}")
            return {
                "status": "error",
                "message": f"Worker test failed: {str(e)}"
            }

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
