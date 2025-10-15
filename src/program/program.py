import linecache
import os
import threading
import time
from datetime import datetime
from queue import Empty

from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy import select

from program.scheduling.models import ScheduledTask, ScheduledStatus
from program.media.state import States

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
from program.utils.logging import log_cleaner, logger

from .state_transition import process_event
from .services.filesystem import FilesystemService
from .types import Event

# Defer importing tracemalloc until runtime to avoid issues during tests that patch settings_manager
if bool(getattr(settings_manager.settings, "tracemalloc", False)):
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
        self.enable_trace = settings_manager.settings.tracemalloc
        self.em = EventManager()
        if self.enable_trace:
            try:
                import tracemalloc as _tracemalloc
            except Exception:
                # Disable tracing if tracemalloc isn't available or import failed under test mocks
                self.enable_trace = False
            else:
                _tracemalloc.start()
                self.malloc_time = time.monotonic() - 50
                self.last_snapshot = None

    def initialize_apis(self):
        bootstrap_apis()

    def initialize_services(self):
        """Initialize all services."""
        self.requesting_services = {
            Overseerr: Overseerr(),
            PlexWatchlist: PlexWatchlist(),
            Listrr: Listrr(),
            Mdblist: Mdblist(),
            TraktContent: TraktContent(),
        }

        # Instantiate services fresh on each settings change; settings_manager observers handle reinit
        _downloader = Downloader()
        self.services = {
            IndexerService: IndexerService(),
            Scraping: Scraping(),
            Updater: Updater(),
            Downloader: _downloader,
            FilesystemService: FilesystemService(_downloader),
            PostProcessing: PostProcessing(),
            NotificationService: NotificationService(),
        }

        self.all_services = {
            **self.requesting_services,
            **self.services,
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
            try:
                import tracemalloc as _tracemalloc
            except Exception:
                self.enable_trace = False
            else:
                self.last_snapshot = _tracemalloc.take_snapshot()


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
        """Retry items that failed to download."""
        with db.Session() as session:
            item_ids = db_functions.retry_library(session)
            for item_id in item_ids:
                self.em.add_event(Event(emitted_by="RetryLibrary", item_id=item_id))

            if item_ids:
                logger.log("PROGRAM", f"Successfully retried {len(item_ids)} incomplete items")
            else:
                logger.log("NOT_FOUND", "No items required retrying")

    def _reindex_ongoing(self) -> None:
        """Reindex all ongoing items to fetch fresh metadata."""
        indexer_service = self.services.get(IndexerService)
        if not indexer_service:
            logger.error("IndexerService not available")
            return

        # Call the indexer's built-in reindex method; this will not enqueue events
        count = indexer_service.reindex_ongoing()
        if count:
            logger.log("PROGRAM", f"Reindexed {count} ongoing items")

    def _process_scheduled_tasks(self) -> None:
        """Process due scheduled tasks and emit appropriate events or actions.

        - For release tasks (episodes/movies): refresh state and enqueue to event manager
        - For reindex tasks: reindex the specific item via IndexerService
        """
        from datetime import datetime
        from sqlalchemy.exc import SQLAlchemyError
        from program.db import db_functions

        try:
            with db.Session() as session:
                now = datetime.now()
                due_tasks = (
                    session.execute(
                        select(ScheduledTask)
                        .where(ScheduledTask.status == ScheduledStatus.Pending)
                        .where(ScheduledTask.scheduled_for <= now)
                        .order_by(ScheduledTask.scheduled_for.asc())
                    )
                    .unique()
                    .scalars()
                    .all()
                )

                if not due_tasks:
                    return

                for task in due_tasks:
                    try:
                        # Load item by id (detached) then merge to this session
                        item = db_functions.get_item_by_id(task.item_id, session=session, load_tree=False)
                        if not item:
                            task.status = ScheduledStatus.Failed
                            task.executed_at = now
                            session.add(task)
                            session.commit()
                            logger.debug(f"ScheduledTask {task.id} item {task.item_id} no longer exists")
                            continue
                        item = session.merge(item)

                        # Reindex tasks: support shows and movies (and generic items)
                        if task.task_type in ("reindex_show", "reindex", "reindex_movie"):
                            indexer_service = self.services.get(IndexerService)
                            if not indexer_service:
                                raise RuntimeError("IndexerService not available")
                            updated = next(indexer_service.run(item, log_msg=False), None)
                            if updated:
                                session.merge(updated)
                                session.commit()
                                logger.info(f"Reindexed {item.log_string} from scheduler")
                        else:
                            # Refresh item state and enqueue for processing (idempotent pipeline)
                            was_completed = getattr(item, "last_state", None) == States.Completed
                            item.store_state()
                            session.commit()
                            # Avoid enqueuing items that were already fully completed
                            if not was_completed:
                                self.em.add_event(Event(emitted_by="Scheduler", item_id=item.id))
                                logger.info(f"Enqueued {item.log_string} from scheduler")

                        task.status = ScheduledStatus.Completed
                        task.executed_at = datetime.now()
                        session.add(task)
                        session.commit()
                    except Exception as e:
                        session.rollback()
                        task.status = ScheduledStatus.Failed
                        task.executed_at = datetime.now()
                        session.add(task)
                        session.commit()
                        logger.error(f"Failed processing ScheduledTask {getattr(task,'id',None)}: {e}")
        except SQLAlchemyError as e:
            logger.error(f"Scheduler DB error: {e}")

    def _monitor_ongoing_schedules(self) -> None:
        """Ensure schedules exist for upcoming releases and metadata refreshes.

        - Episodes with a future aired_at: schedule "episode_release" at aired_at + offset
        - Movies with a future aired_at: schedule "movie_release" at aired_at + offset
        - Ongoing/Unreleased shows: schedule a targeted reindex at the next air time computed from release_data
          (preferring release_data.next_aired when present; otherwise compute from airs_days/time).
        - For items missing any air hints: schedule a daily reindex (idempotent) to discover updates.
        """
        from datetime import datetime, timedelta
        from sqlalchemy import and_, not_
        from program.media.item import Episode, Show, Movie
        from program.scheduling.models import ScheduledTask, ScheduledStatus

        offset_seconds = settings_manager.settings.indexer.schedule_offset_minutes * 60
        now = datetime.now()

        def has_future_task(session, item_id: int, task_type: str) -> bool:
            """Return True if a pending future task of this type already exists for item."""
            existing = (
                session.execute(
                    select(ScheduledTask)
                    .where(ScheduledTask.item_id == item_id)
                    .where(ScheduledTask.task_type == task_type)
                    .where(ScheduledTask.status == ScheduledStatus.Pending)
                    .where(ScheduledTask.scheduled_for >= now)
                    .limit(1)
                )
                .scalars()
                .first()
            )
            return existing is not None

        try:
            with db.Session() as session:
                # 1) Episodes with a future air date (skip already-completed)
                upcoming_eps = (
                    session.execute(
                        select(Episode)
                        .where(Episode.aired_at.is_not(None))
                        .where(Episode.aired_at >= now)
                        .where(not_(Episode.last_state == States.Completed))
                    )
                    .unique()
                    .scalars()
                    .all()
                )
                for ep in upcoming_eps:
                    run_at = ep.aired_at + timedelta(seconds=offset_seconds)
                    if not has_future_task(session, ep.id, "episode_release"):
                        try:
                            ep.schedule(
                                run_at,
                                task_type="episode_release",
                                offset_seconds=offset_seconds,
                                reason="monitor:episode_air",
                            )
                        except Exception as e:
                            logger.debug(f"Skipping schedule for {ep.log_string}: {e}")

                # 2) Movies with a future release date (skip already-completed)
                upcoming_movies = (
                    session.execute(
                        select(Movie)
                        .where(Movie.aired_at.is_not(None))
                        .where(Movie.aired_at >= now)
                        .where(not_(Movie.last_state == States.Completed))
                    )
                    .unique()
                    .scalars()
                    .all()
                )
                for mv in upcoming_movies:
                    run_at = mv.aired_at + timedelta(seconds=offset_seconds)
                    if not has_future_task(session, mv.id, "movie_release"):
                        try:
                            mv.schedule(
                                run_at,
                                task_type="movie_release",
                                offset_seconds=offset_seconds,
                                reason="monitor:movie_release",
                            )
                        except Exception as e:
                            logger.debug(f"Skipping schedule for {mv.log_string}: {e}")

                # 3) Ongoing/unreleased shows: compute next air time; schedule reindex
                ongoing_shows = (
                    session.execute(
                        select(Show).where(Show.last_state.in_([States.Ongoing, States.Unreleased]))
                    )
                    .unique()
                    .scalars()
                    .all()
                )
                for show in ongoing_shows:
                    rd = show.release_data or {}
                    next_air = self._compute_next_air_datetime(rd, now)
                    if next_air and next_air > now:
                        if not has_future_task(session, show.id, "reindex_show"):
                            try:
                                show.schedule(next_air, task_type="reindex_show", reason="monitor:next_air")
                            except Exception as e:
                                logger.debug(f"Skipping reindex schedule for {show.log_string}: {e}")
                    else:
                        # No hint available; schedule a daily reindex to discover updates
                        fallback_time = (now + timedelta(days=1)).replace(minute=0, second=0, microsecond=0)
                        if not has_future_task(session, show.id, "reindex_show"):
                            try:
                                show.schedule(fallback_time, task_type="reindex_show", reason="monitor:fallback_daily")
                            except Exception as e:
                                logger.debug(f"Skipping fallback reindex for {show.log_string}: {e}")

                # 4) Movies without a known release date: daily reindex to discover updates
                unknown_movies = (
                    session.execute(
                        select(Movie)
                        .where(Movie.aired_at.is_(None))
                        .where(Movie.last_state.in_([States.Unreleased, States.Indexed, States.Requested, States.Unknown]))
                    )
                    .unique()
                    .scalars()
                    .all()
                )
                for mv in unknown_movies:
                    fallback_time = (now + timedelta(days=1)).replace(minute=0, second=0, microsecond=0)
                    if not has_future_task(session, mv.id, "reindex_movie"):
                        try:
                            mv.schedule(fallback_time, task_type="reindex_movie", reason="monitor:fallback_daily")
                        except Exception as e:
                            logger.debug(f"Skipping fallback reindex for {mv.log_string}: {e}")
        except Exception as e:
            logger.error(f"Monitor ongoing schedules failed: {e}")

    @staticmethod
    def _compute_next_air_datetime(release_data: dict, ref: datetime) -> datetime | None:
        """Compute the next air datetime from a TVDB-like release_data payload.

        Preferred order:
        1) Use release_data['next_aired'] (ISO date or datetime string). If it's a date-only string, combine with 'airs_time'.
        2) Otherwise, compute from 'airs_days' + 'airs_time'.

        Timezone handling:
        - If release_data['timezone'] is present and recognized, interpret times in that zone and convert to local naive datetime.
        - Otherwise, treat times as local naive.
        """
        from datetime import datetime, timedelta
        try:
            from zoneinfo import ZoneInfo  # Python 3.9+
        except Exception:
            ZoneInfo = None

        if not release_data:
            return None

        # Helper to localize a naive datetime based on provided timezone and convert to local naive
        def to_local_naive(dt: datetime) -> datetime:
            if not isinstance(dt, datetime):
                return None
            tz_name = (release_data or {}).get("timezone")
            if tz_name and ZoneInfo is not None:
                try:
                    tz = ZoneInfo(tz_name)
                    aware = dt.replace(tzinfo=tz)
                    # Convert to local timezone then drop tzinfo
                    local = datetime.now().astimezone().tzinfo
                    if local:
                        aware_local = aware.astimezone(local)
                        return aware_local.replace(tzinfo=None)
                except Exception:
                    pass
            # Fallback: treat as local naive
            return dt

        # 1) Prefer explicit next_aired
        next_aired = (release_data or {}).get("next_aired")
        airs_time = (release_data or {}).get("airs_time")
        if next_aired:
            na_str = str(next_aired)
            dt = None
            # Treat date-only specially so we can combine with airs_time
            if "T" in na_str or " " in na_str:
                try:
                    dt = datetime.fromisoformat(na_str)
                except Exception:
                    dt = None
            else:
                # Date-only string
                try:
                    date_only = datetime.fromisoformat(na_str + "T00:00:00")
                    if airs_time:
                        try:
                            hour, minute = [int(x) for x in str(airs_time).split(":", 1)]
                        except Exception:
                            hour, minute = 0, 0
                        date_only = date_only.replace(hour=hour, minute=minute)
                    dt = date_only
                except Exception:
                    dt = None
            if dt:
                dt_local = to_local_naive(dt)
                if dt_local and dt_local >= ref:
                    return dt_local
                # If next_aired was in the past, fall through to compute from airs_days/time

        # 2) Compute from airs_days + airs_time
        airs_days = (release_data or {}).get("airs_days") or {}
        if not airs_time:
            return None
        try:
            hour, minute = [int(x) for x in str(airs_time).split(":", 1)]
        except Exception:
            return None

        # Build list of weekdays [0=Monday..6=Sunday] that are True
        day_map = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
        valid_days: list[int] = [i for i, name in enumerate(day_map) if airs_days.get(name) is True]
        if not valid_days:
            return None

        # Find next occurrence >= ref (limit search to 3 weeks)
        for i in range(0, 21):
            candidate = ref + timedelta(days=i)
            if candidate.weekday() in valid_days:
                candidate_dt = candidate.replace(hour=hour, minute=minute, second=0, microsecond=0)
                candidate_dt = to_local_naive(candidate_dt)
                if candidate_dt and candidate_dt >= ref:
                    return candidate_dt
        return None

    def _schedule_functions(self) -> None:
        """Schedule each service based on its update interval."""
        scheduled_functions = {
            vacuum_and_analyze_index_maintenance: {"interval": 60 * 60 * 24},
        }

        # Add retry_library if enabled (interval > 0)
        retry_interval = settings_manager.settings.retry_interval
        if retry_interval > 0:
            scheduled_functions[self._retry_library] = {"interval": retry_interval}

        # Add log_cleaner if enabled (interval > 0)
        clean_interval = settings_manager.settings.logging.clean_interval
        if clean_interval > 0:
            scheduled_functions[log_cleaner] = {"interval": clean_interval}

        # Add scheduler processing and monitoring
        scheduled_functions[self._process_scheduled_tasks] = {"interval": 60}
        scheduled_functions[self._monitor_ongoing_schedules] = {"interval": 15 * 60}

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

            existing_item: MediaItem = db_functions.get_item_by_id(event.item_id)

            next_service, items_to_submit = process_event(
                event.emitted_by, existing_item, event.content_item
            )

            for item_to_submit in items_to_submit:
                if not next_service:
                    self.em.add_event_to_queue(Event("StateTransition", item_id=item_to_submit.id))
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
        if hasattr(self, "scheduler") and self.scheduler.running:
            self.scheduler.shutdown(wait=False)

        self.services[FilesystemService].close()
        logger.log("PROGRAM", "Riven has been stopped.")

riven = Program()