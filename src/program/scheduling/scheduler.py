"""Scheduling subsystem for Program.

Encapsulates APScheduler setup, background jobs, and time-based orchestration
for content services and item-specific schedules.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Callable, Dict

from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from program.db import db_functions
from program.db.db import db, vacuum_and_analyze_index_maintenance
from program.media.item import Episode, Movie, Show
from program.media.state import States
from program.scheduling.models import ScheduledStatus, ScheduledTask
from program.services.indexers import IndexerService
from program.settings.manager import settings_manager
from program.types import Event
from program.utils.logging import log_cleaner, logger


class ProgramScheduler:
    """Owns the BackgroundScheduler and all scheduling concerns for Program.

    This class keeps scheduling logic out of Program and wires jobs to the
    Program instance via dependency injection.
    """

    def __init__(self, program) -> None:
        self.program = program
        self.scheduler: BackgroundScheduler | None = None

    def start(self) -> None:
        """Create and start the background scheduler with all jobs registered."""
        self.scheduler = BackgroundScheduler()
        self._schedule_services()
        self._schedule_functions()
        self.scheduler.start()

    def stop(self) -> None:
        """Stop the background scheduler if running."""
        if self.scheduler and self.scheduler.running:
            self.scheduler.shutdown(wait=False)

    def _schedule_functions(self) -> None:
        """Register internal periodic functions and maintenance tasks."""
        assert self.scheduler is not None

        scheduled_functions: Dict[Callable[..., None], dict] = {
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
                misfire_grace_time=30,
            )
            logger.debug(
                f"Scheduled {func.__name__} to run every {config['interval']} seconds."
            )

    def _schedule_services(self) -> None:
        """Schedule each content service based on its update interval or webhook mode."""
        assert self.scheduler is not None

        scheduled_services = {**self.program.requesting_services}
        for service_cls, service_instance in scheduled_services.items():
            if not service_instance.initialized:
                continue

            # If the service supports webhooks and webhook mode is enabled, run once now
            use_webhook = getattr(
                getattr(service_instance, "settings", object()), "use_webhook", False
            )
            if use_webhook:
                self.scheduler.add_job(
                    self.program.em.submit_job,
                    "date",
                    run_date=datetime.now(),
                    args=[service_cls, self.program],
                    id=f"{service_cls.__name__}_update_once",
                    replace_existing=True,
                    misfire_grace_time=30,
                )
                logger.debug(
                    f"Scheduled {service_cls.__name__} to run once (webhook mode enabled)."
                )
                continue

            update_interval = getattr(service_instance.settings, "update_interval", False)
            if not update_interval:
                continue

            self.scheduler.add_job(
                self.program.em.submit_job,
                "interval",
                seconds=update_interval,
                args=[service_cls, self.program],
                id=f"{service_cls.__name__}_update",
                max_instances=1,
                replace_existing=True,
                next_run_time=datetime.now(),
                coalesce=False,
            )
            logger.debug(
                f"Scheduled {service_cls.__name__} to run every {update_interval} seconds."
            )

    def _retry_library(self) -> None:
        """Retry items that failed to download by emitting events into the EM."""
        item_ids = db_functions.retry_library()
        for item_id in item_ids:
            self.program.em.add_event(Event(emitted_by="RetryLibrary", item_id=item_id))

        if item_ids:
            logger.log("PROGRAM", f"Successfully retried {len(item_ids)} incomplete items")
        else:
            logger.log("NOT_FOUND", "No items required retrying")

    def _schedule_callback(self, task: ScheduledTask, callback: Callable) -> None:
        """Schedule a callback to run at the task's scheduled_for time."""
        try:        
            self.scheduler.add_job(
                callback,
                "date",
                run_date=task.scheduled_for,
                args=[task],
                id=f"task_{task.id}",
                replace_existing=True,
                misfire_grace_time=30,
            )
        except Exception as e:
            if task:
                logger.error(f"Failed to schedule callback for task {task.id}: {e}")
            else:
                logger.error(f"Failed to schedule callback: {e}")

    def _get_pending_scheduled_tasks(self, session: Session) -> list[ScheduledTask]:
        """Return all pending scheduled tasks."""
        try:
            return (
                session.execute(
                    select(ScheduledTask)
                    .where(ScheduledTask.status == ScheduledStatus.Pending)
                    .where(ScheduledTask.scheduled_for <= datetime.now())
                    .order_by(ScheduledTask.scheduled_for.asc())
                )
                .unique()
                .scalars()
                .all()
            )
        except SQLAlchemyError as e:
            logger.error(f"Scheduler DB error: {e}")
            return []

    def _process_scheduled_tasks(self) -> None:
        """Process due scheduled tasks by delegating to focused helpers.

        Responsibilities split into:
        - fetching due tasks;
        - loading/merging the target item for a task;
        - handling reindex vs. release tasks;
        - updating task status with consistent error handling.
        """
        try:
            with db.Session() as session:
                now = datetime.now()
                due_tasks = self._get_pending_scheduled_tasks(session)
                if not due_tasks:
                    return

                for task in due_tasks:
                    self._process_single_scheduled_task(session, task, now)
        except SQLAlchemyError as e:
            logger.error(f"Scheduler DB error: {e}")

    def _process_single_scheduled_task(self, session: Session, task: ScheduledTask, now: datetime) -> None:
        """Process a single ScheduledTask instance.

        Args:
            session: Active SQLAlchemy session.
            task: The scheduled task to process.
            now: Current timestamp used for status updates.
        """
        try:
            item = self._load_item_for_task(session, task)
            if not item:
                self._mark_task_status(session, task, ScheduledStatus.Failed, now)
                logger.debug(f"ScheduledTask {task.id} item {task.item_id} no longer exists")
                return

            if task.task_type in ("reindex_show", "reindex", "reindex_movie"):
                self._run_reindex_for_item(session, item)
            else:
                self._enqueue_item_if_needed(session, item)

            self._mark_task_status(session, task, ScheduledStatus.Completed, datetime.now())
        except Exception as e:
            session.rollback()
            self._mark_task_status(session, task, ScheduledStatus.Failed, datetime.now())
            logger.error(f"Failed processing ScheduledTask {getattr(task,'id',None)}: {e}")

    def _load_item_for_task(self, session: Session, task: ScheduledTask):
        """Load and merge the MediaItem for a scheduled task.

        Returns:
            The merged item or None if missing.
        """
        item = db_functions.get_item_by_id(task.item_id, session=session, load_tree=False)
        if not item:
            return None
        return session.merge(item)

    def _run_reindex_for_item(self, session: Session, item) -> None:
        """Run indexer service for an item if available and persist updates."""
        indexer_service = self.program.services.get(IndexerService)
        if not indexer_service:
            raise RuntimeError("IndexerService not available")
        updated = next(indexer_service.run(item, log_msg=False), None)
        if updated:
            session.merge(updated)
            session.commit()
            logger.info(f"Reindexed {item.log_string} from scheduler")

    def _enqueue_item_if_needed(self, session: Session, item) -> None:
        """Refresh state and enqueue item to the event manager if not completed."""
        was_completed = getattr(item, "last_state", None) == States.Completed
        item.store_state()
        session.commit()
        if not was_completed:
            self.program.em.add_event(Event(emitted_by="Scheduler", item_id=item.id))
            logger.info(f"Enqueued {item.log_string} from scheduler")

    @staticmethod
    def _mark_task_status(session: Session, task: ScheduledTask, status: ScheduledStatus, executed_at: datetime) -> None:
        """Persist a task status update in a single place."""
        task.status = status
        task.executed_at = executed_at
        session.add(task)
        session.commit()

    def _monitor_ongoing_schedules(self) -> None:
        """Ensure schedules exist for upcoming releases and metadata refreshes.

        Decomposed into helpers for clarity:
        - schedule upcoming episodes
        - schedule upcoming movies (known release date)
        - schedule ongoing/unreleased shows (computed next air)
        - schedule unknown-date movies (daily reindex)
        """
        offset_seconds = settings_manager.settings.indexer.schedule_offset_minutes * 60
        now = datetime.now()
        try:
            with db.Session() as session:
                self._schedule_upcoming_episodes(session, now, offset_seconds)
                self._schedule_upcoming_movies(session, now, offset_seconds)
                self._schedule_ongoing_shows(session, now)
                self._schedule_unknown_movies(session, now)
        except Exception as e:
            logger.error(f"Monitor ongoing schedules failed: {e}")

    def _has_future_task(self, session: Session, item_id: int, task_type: str, now: datetime) -> bool:
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

    def _schedule_upcoming_episodes(self, session: Session, now: datetime, offset_seconds: int) -> None:
        """Schedule episode_release for future-dated episodes that are not completed."""
        upcoming_eps = (
            session.execute(
                select(Episode)
                .where(Episode.aired_at.is_not(None))
                .where(Episode.aired_at >= now)
                .where(~(Episode.last_state == States.Completed))
            )
            .unique()
            .scalars()
            .all()
        )
        for ep in upcoming_eps:
            run_at = ep.aired_at + timedelta(seconds=offset_seconds)
            if not self._has_future_task(session, ep.id, "episode_release", now):
                try:
                    ep.schedule(
                        run_at,
                        task_type="episode_release",
                        offset_seconds=offset_seconds,
                        reason="monitor:episode_air",
                    )
                except Exception as e:
                    logger.debug(f"Skipping schedule for {ep.log_string}: {e}")

    def _schedule_upcoming_movies(self, session: Session, now: datetime, offset_seconds: int) -> None:
        """Schedule movie_release for future-dated movies that are not completed."""
        upcoming_movies = (
            session.execute(
                select(Movie)
                .where(Movie.aired_at.is_not(None))
                .where(Movie.aired_at >= now)
                .where(~(Movie.last_state == States.Completed))
            )
            .unique()
            .scalars()
            .all()
        )
        for mv in upcoming_movies:
            run_at = mv.aired_at + timedelta(seconds=offset_seconds)
            if not self._has_future_task(session, mv.id, "movie_release", now):
                try:
                    mv.schedule(
                        run_at,
                        task_type="movie_release",
                        offset_seconds=offset_seconds,
                        reason="monitor:movie_release",
                    )
                except Exception as e:
                    logger.debug(f"Skipping schedule for {mv.log_string}: {e}")

    def _schedule_ongoing_shows(self, session: Session, now: datetime) -> None:
        """Schedule reindex_show for ongoing/unreleased shows based on next air, with daily fallback."""
        ongoing_shows = (
            session.execute(select(Show).where(Show.last_state.in_([States.Ongoing, States.Unreleased])))
            .unique()
            .scalars()
            .all()
        )
        for show in ongoing_shows:
            rd = show.release_data or {}
            next_air = self._compute_next_air_datetime(rd, now)
            if next_air and next_air > now:
                if not self._has_future_task(session, show.id, "reindex_show", now):
                    try:
                        show.schedule(next_air, task_type="reindex_show", reason="monitor:next_air")
                    except Exception as e:
                        logger.debug(f"Skipping reindex schedule for {show.log_string}: {e}")
            else:
                fallback_time = (now + timedelta(days=1)).replace(minute=0, second=0, microsecond=0)
                if not self._has_future_task(session, show.id, "reindex_show", now):
                    try:
                        show.schedule(fallback_time, task_type="reindex_show", reason="monitor:fallback_daily")
                    except Exception as e:
                        logger.debug(f"Skipping fallback reindex for {show.log_string}: {e}")

    def _schedule_unknown_movies(self, session: Session, now: datetime) -> None:
        """Schedule daily reindex for movies without any known release date."""
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
            if not self._has_future_task(session, mv.id, "reindex_movie", now):
                try:
                    mv.schedule(fallback_time, task_type="reindex_movie", reason="monitor:fallback_daily")
                except Exception as e:
                    logger.debug(f"Skipping fallback reindex for {mv.log_string}: {e}")

    @staticmethod
    def _compute_next_air_datetime(release_data: dict, ref: datetime) -> datetime | None:
        """Compute the next air datetime from a TVDB-like payload.

        Strategy:
        1) Try explicit next_aired (date or datetime). If date-only, combine with airs_time.
        2) Otherwise, use airs_days + airs_time to find the next matching weekday.
        All times honor release_data['timezone'] when provided, then converted to local naive.
        """
        if not release_data:
            return None

        dt = ProgramScheduler._parse_next_aired_datetime(release_data)
        if dt is not None:
            dt_local = ProgramScheduler._to_local_naive(release_data, dt)
            if dt_local and dt_local >= ref:
                return dt_local
            # fall through to weekday computation if next_aired is in the past

        hm = ProgramScheduler._parse_airs_time(release_data)
        if hm is None:
            return None
        hour, minute = hm

        valid_days = ProgramScheduler._valid_weekdays(release_data)
        if not valid_days:
            return None

        # Find next occurrence >= ref within 3 weeks
        for i in range(0, 21):
            candidate = ref + timedelta(days=i)
            if candidate.weekday() in valid_days:
                candidate_dt = candidate.replace(hour=hour, minute=minute, second=0, microsecond=0)
                candidate_dt = ProgramScheduler._to_local_naive(release_data, candidate_dt)
                if candidate_dt and candidate_dt >= ref:
                    return candidate_dt
        return None

    @staticmethod
    def _to_local_naive(release_data: dict, dt: datetime) -> datetime:
        """Convert a naive datetime in a source timezone (if provided) to local naive.

        If release_data['timezone'] is provided and recognized by zoneinfo, interpret
        the naive datetime in that zone and convert to local time. Otherwise, treat
        as already-local naive.
        """
        try:
            from zoneinfo import ZoneInfo  # Python 3.9+
        except Exception:
            ZoneInfo = None  # type: ignore[assignment]

        if not isinstance(dt, datetime):
            return dt
        tz_name = (release_data or {}).get("timezone")
        if tz_name and ZoneInfo is not None:
            try:
                tz = ZoneInfo(tz_name)
                aware = dt.replace(tzinfo=tz)
                local_tz = datetime.now().astimezone().tzinfo
                if local_tz:
                    aware_local = aware.astimezone(local_tz)
                    return aware_local.replace(tzinfo=None)
            except Exception:
                return dt
        return dt

    @staticmethod
    def _parse_next_aired_datetime(release_data: dict) -> datetime | None:
        """Parse release_data['next_aired'] into a datetime, combining with airs_time if needed."""
        next_aired = (release_data or {}).get("next_aired")
        airs_time = (release_data or {}).get("airs_time")
        if not next_aired:
            return None
        na_str = str(next_aired)
        # If datetime-like
        if "T" in na_str or " " in na_str:
            try:
                return datetime.fromisoformat(na_str)
            except Exception:
                return None
        # Date-only
        try:
            base = datetime.fromisoformat(na_str + "T00:00:00")
            if airs_time:
                try:
                    hour, minute = [int(x) for x in str(airs_time).split(":", 1)]
                except Exception:
                    hour, minute = 0, 0
                return base.replace(hour=hour, minute=minute)
            return base
        except Exception:
            return None

    @staticmethod
    def _parse_airs_time(release_data: dict) -> tuple[int, int] | None:
        """Parse HH:MM from release_data['airs_time'] if present and valid."""
        airs_time = (release_data or {}).get("airs_time")
        if not airs_time:
            return None
        try:
            hour, minute = [int(x) for x in str(airs_time).split(":", 1)]
            return hour, minute
        except Exception:
            return None

    @staticmethod
    def _valid_weekdays(release_data: dict) -> list[int]:
        """Return list of weekday indices [0..6] marked True in release_data['airs_days']."""
        airs_days = (release_data or {}).get("airs_days") or {}
        day_map = [
            "monday",
            "tuesday",
            "wednesday",
            "thursday",
            "friday",
            "saturday",
            "sunday",
        ]
        return [i for i, name in enumerate(day_map) if airs_days.get(name) is True]

