"""
Scheduling subsystem for Program.

Encapsulates APScheduler setup, background jobs, and time-based orchestration
for content services and item-specific schedules.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, TypedDict

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
import trio
import trio_util

from program.db import db_functions
from program.db.db import db_session, vacuum_and_analyze_index_maintenance
from program.media.item import Episode, MediaItem, Movie, Show
from program.media.state import States
from program.scheduling.models import ScheduledStatus, ScheduledTask
from program.settings import settings_manager
from program.types import Event
from program.utils.logging import log_cleaner, logger
from program.apis.tvdb_api import SeriesRelease
from schemas.tvdb.models.series_airs_days import SeriesAirsDays
from program.core.runner import Runner

if TYPE_CHECKING:
    from program.program import Program


class ScheduledFunctionConfig(TypedDict):
    interval: int


class ProgramScheduler:
    """
    Owns the BackgroundScheduler and all scheduling concerns for Program.

    This class keeps scheduling logic out of Program and wires jobs to the
    Program instance via dependency injection.
    """

    def __init__(self, program: "Program") -> None:
        self.program = program
        self.stop_requested = trio_util.AsyncBool(False)

    async def start(
        self,
        *,
        task_status: trio.TaskStatus = trio.TASK_STATUS_IGNORED,
    ) -> None:
        """Create and start the background scheduler with all jobs registered."""

        async with trio.open_nursery() as nursery:
            self._schedule_services(nursery)
            self._schedule_functions(nursery)

            task_status.started()

            await self.stop_requested.wait_value(True)

            logger.debug(f"Shutting down ProgramScheduler")

            nursery.cancel_scope.cancel()

    async def stop(self) -> None:
        """Stop the background scheduler if running."""

        self.stop_requested.value = True

    def _add_job(
        self,
        func: Callable[..., Awaitable[None] | None],
        config: ScheduledFunctionConfig,
        nursery: trio.Nursery,
    ) -> None:
        """Add a job to the scheduler."""

        async def job_wrapper():
            async for _ in trio_util.periodic(config["interval"]):
                result = func()

                if isinstance(result, Awaitable):
                    await result

                logger.debug(f"Scheduled job {func.__name__} completed, sleeping")

        nursery.start_soon(job_wrapper)

    def _schedule_functions(self, nursery: trio.Nursery) -> None:
        """Register internal periodic functions and maintenance tasks."""

        scheduled_functions = dict[
            Callable[..., Awaitable[None] | None], ScheduledFunctionConfig
        ](
            {
                vacuum_and_analyze_index_maintenance: {"interval": 60 * 60 * 24},
            }
        )

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
            self._add_job(func, config, nursery)

            logger.debug(
                f"Scheduled {func.__name__} to run every {config['interval']} seconds."
            )

    def _schedule_services(self, nursery: trio.Nursery) -> None:
        """Schedule each content service based on its update interval or webhook mode."""

        assert self.program.services

        for service_instance in self.program.services.content_services:
            service_name = service_instance.__class__.__name__

            # If the service supports webhooks and webhook mode is enabled, run once now
            use_webhook = getattr(
                getattr(service_instance, "settings", object()), "use_webhook", False
            )

            if use_webhook:
                nursery.start_soon(
                    self.program.em.submit_job,
                    service_instance,
                    self.program,
                )

                logger.debug(
                    f"Scheduled {service_name} to run once (webhook mode enabled)."
                )

                continue

            update_interval = getattr(
                service_instance.settings, "update_interval", False
            )

            if not update_interval:
                continue

            async def run_task(
                service_instance: Runner = service_instance,
            ) -> None:
                """Wrapper to submit the service job to the EM."""

                await self.program.em.submit_job(
                    service_instance,
                    self.program,
                )

            self._add_job(
                func=run_task,
                config={"interval": update_interval},
                nursery=nursery,
            )

            logger.debug(
                f"Scheduled {service_name} to run every {update_interval} seconds."
            )

    async def _retry_library(self) -> None:
        """Retry items that failed to download by emitting events into the EM."""

        item_ids = db_functions.retry_library()

        for item_id in item_ids:
            await self.program.em.add_event(
                Event(
                    emitted_by="RetryLibrary",
                    item_id=item_id,
                )
            )

        if item_ids:
            logger.log(
                "PROGRAM",
                f"Successfully retried {len(item_ids)} incomplete items",
            )
        else:
            logger.log("NOT_FOUND", "No items required retrying")

    def _get_pending_scheduled_tasks(self, session: Session) -> Sequence[ScheduledTask]:
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

    async def _process_scheduled_tasks(self) -> None:
        """
        Process due scheduled tasks by delegating to focused helpers.

        Responsibilities split into:
        - fetching due tasks;
        - loading/merging the target item for a task;
        - handling reindex vs. release tasks;
        - updating task status with consistent error handling.
        """

        try:
            with db_session() as session:
                now = datetime.now()
                due_tasks = self._get_pending_scheduled_tasks(session)

                if not due_tasks:
                    return

                for task in due_tasks:
                    await self._process_single_scheduled_task(session, task, now)
        except SQLAlchemyError as e:
            logger.error(f"Scheduler DB error: {e}")

    async def _process_single_scheduled_task(
        self,
        session: Session,
        task: ScheduledTask,
        now: datetime,
    ) -> None:
        """
        Process a single ScheduledTask instance.

        Args:
            session: Active SQLAlchemy session.
            task: The scheduled task to process.
            now: Current timestamp used for status updates.
        """
        try:
            item = self._load_item_for_task(session, task)

            if not item:
                self._mark_task_status(
                    session,
                    task,
                    ScheduledStatus.Failed,
                    now,
                )

                logger.debug(
                    f"ScheduledTask {task.id} item {task.item_id} no longer exists"
                )

                return

            if task.task_type in ("reindex_show", "reindex", "reindex_movie"):
                await self._run_reindex_for_item(session, item)
            else:
                await self._enqueue_item_if_needed(session, item)

            self._mark_task_status(
                session,
                task,
                ScheduledStatus.Completed,
                datetime.now(),
            )
        except Exception as e:
            session.rollback()
            self._mark_task_status(
                session, task, ScheduledStatus.Failed, datetime.now()
            )
            logger.exception(f"Failed processing ScheduledTask {task.id}: {e}")

    def _load_item_for_task(self, session: Session, task: ScheduledTask):
        """
        Load and merge the MediaItem for a scheduled task.

        Returns:
            The merged item or None if missing.
        """

        item = db_functions.get_item_by_id(task.item_id, session=session)

        if not item:
            return None

        return session.merge(item)

    async def _run_reindex_for_item(self, session: Session, item: MediaItem) -> None:
        """Run indexer service for an item if available and persist updates."""

        assert self.program.services, "Services not initialized in Program"

        indexer_service = self.program.services.indexer

        updated = await indexer_service.run(item, log_msg=False)

        if updated:
            session.merge(updated.media_items[0])
            session.commit()

            logger.info(f"Reindexed {item.log_string} from scheduler")

    async def _enqueue_item_if_needed(self, session: Session, item: MediaItem) -> None:
        """Refresh state and enqueue item to the event manager if not completed."""

        was_completed = item.last_state == States.Completed

        await item.store_state()

        session.commit()

        if not was_completed:
            await self.program.em.add_event(
                Event(
                    emitted_by="Scheduler",
                    item_id=item.id,
                )
            )

            logger.info(f"Enqueued {item.log_string} from scheduler")

    def _mark_task_status(
        self,
        session: Session,
        task: ScheduledTask,
        status: ScheduledStatus,
        executed_at: datetime,
    ) -> None:
        """Persist a task status update in a single place."""

        task.status = status
        task.executed_at = executed_at

        session.add(task)
        session.commit()

    def _monitor_ongoing_schedules(self) -> None:
        """
        Ensure schedules exist for upcoming releases and metadata refreshes.

        Decomposed into helpers for clarity:
        - schedule upcoming episodes
        - schedule upcoming movies (known release date)
        - schedule ongoing/unreleased shows (computed next air)
        - schedule unknown-date movies (daily reindex)
        """

        offset_seconds = settings_manager.settings.indexer.schedule_offset_minutes * 60
        now = datetime.now()

        try:
            with db_session() as session:
                self._schedule_upcoming_episodes(session, now, offset_seconds)
                self._schedule_upcoming_movies(session, now, offset_seconds)
                self._schedule_ongoing_shows(session, now)
                self._schedule_unknown_movies(session, now)
        except Exception as e:
            logger.error(f"Monitor ongoing schedules failed: {e}")

    def _has_future_task(
        self,
        session: Session,
        item_id: int,
        task_type: str,
        now: datetime,
    ) -> bool:
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

    def _schedule_upcoming_episodes(
        self,
        session: Session,
        now: datetime,
        offset_seconds: int,
    ) -> None:
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
            if (
                not self._has_future_task(session, ep.id, "episode_release", now)
                and ep.aired_at
            ):
                run_at = ep.aired_at + timedelta(seconds=offset_seconds)

                try:
                    ep.schedule(
                        run_at,
                        task_type="episode_release",
                        offset_seconds=offset_seconds,
                        reason="monitor:episode_air",
                    )
                except Exception as e:
                    logger.debug(f"Skipping schedule for {ep.log_string}: {e}")

    def _schedule_upcoming_movies(
        self, session: Session, now: datetime, offset_seconds: int
    ) -> None:
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
            if (
                not self._has_future_task(
                    session=session,
                    item_id=mv.id,
                    task_type="movie_release",
                    now=now,
                )
                and mv.aired_at
            ):
                run_at = mv.aired_at + timedelta(seconds=offset_seconds)

                try:
                    mv.schedule(
                        run_at=run_at,
                        task_type="movie_release",
                        offset_seconds=offset_seconds,
                        reason="monitor:movie_release",
                    )
                except Exception as e:
                    logger.debug(f"Skipping schedule for {mv.log_string}: {e}")

    def _schedule_ongoing_shows(self, session: Session, now: datetime) -> None:
        """Schedule reindex_show for ongoing/unreleased shows based on next air, with daily fallback."""

        ongoing_shows = (
            session.execute(
                select(Show).where(
                    Show.last_state.in_([States.Ongoing, States.Unreleased])
                )
            )
            .unique()
            .scalars()
            .all()
        )

        for show in ongoing_shows:
            rd = show.release_data
            next_air = self._compute_next_air_datetime(rd, now)

            if next_air and next_air > now:
                if not self._has_future_task(session, show.id, "reindex_show", now):
                    try:
                        show.schedule(
                            next_air,
                            task_type="reindex_show",
                            reason="monitor:next_air",
                        )
                    except Exception as e:
                        logger.debug(
                            f"Skipping reindex schedule for {show.log_string}: {e}"
                        )
            else:
                fallback_time = (now + timedelta(days=1)).replace(
                    minute=0,
                    second=0,
                    microsecond=0,
                )

                if not self._has_future_task(session, show.id, "reindex_show", now):
                    try:
                        show.schedule(
                            fallback_time,
                            task_type="reindex_show",
                            reason="monitor:fallback_daily",
                        )
                    except Exception as e:
                        logger.debug(
                            f"Skipping fallback reindex for {show.log_string}: {e}"
                        )

    def _schedule_unknown_movies(self, session: Session, now: datetime) -> None:
        """Schedule daily reindex for movies without any known release date."""

        unknown_movies = (
            session.execute(
                select(Movie)
                .where(Movie.aired_at.is_(None))
                .where(
                    Movie.last_state.in_(
                        [
                            States.Unreleased,
                            States.Indexed,
                            States.Requested,
                            States.Unknown,
                        ]
                    )
                )
            )
            .unique()
            .scalars()
            .all()
        )

        for mv in unknown_movies:
            fallback_time = (now + timedelta(days=1)).replace(
                minute=0, second=0, microsecond=0
            )

            if not self._has_future_task(session, mv.id, "reindex_movie", now):
                try:
                    mv.schedule(
                        fallback_time,
                        task_type="reindex_movie",
                        reason="monitor:fallback_daily",
                    )
                except Exception as e:
                    logger.debug(f"Skipping fallback reindex for {mv.log_string}: {e}")

    @staticmethod
    def _compute_next_air_datetime(
        release_data: SeriesRelease | None,
        ref: datetime,
    ) -> datetime | None:
        """Compute the next air datetime from a TVDB-like payload.

        Strategy:
        1) Try explicit next_aired (date or datetime). If date-only, combine with airs_time.
        2) Otherwise, use airs_days + airs_time to find the next matching weekday.
        All times honor release_data['timezone'] when provided, then converted to local naive.
        """

        if not release_data:
            return None

        dt = ProgramScheduler._parse_next_aired_datetime(release_data)

        if dt is not None and dt >= ref:
            return dt

        # Fall through to weekday computation if next_aired is in the past
        hm = ProgramScheduler._parse_airs_time(release_data.airs_time)

        if hm is None:
            return None

        hour, minute = hm

        valid_days = ProgramScheduler._valid_weekdays(release_data.airs_days)

        if not valid_days:
            return None

        # Find next occurrence >= ref within 3 weeks
        for i in range(0, 21):
            candidate = ref + timedelta(days=i)

            if candidate.weekday() in valid_days:
                candidate_dt = candidate.replace(
                    hour=hour,
                    minute=minute,
                    second=0,
                    microsecond=0,
                )

                if candidate_dt and candidate_dt >= ref:
                    return candidate_dt

        return None

    @staticmethod
    def _parse_next_aired_datetime(release_data: SeriesRelease) -> datetime | None:
        """Parse release_data['next_aired'] into a datetime, combining with airs_time if needed."""

        next_aired = release_data.next_aired

        if not next_aired:
            return None

        # If datetime-like
        if "T" in next_aired or " " in next_aired:
            try:
                return datetime.fromisoformat(next_aired)
            except Exception:
                return None

        airs_time = release_data.airs_time

        # Date-only
        try:
            base = datetime.fromisoformat(next_aired + "T00:00:00")

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
    def _parse_airs_time(airs_time: str | None) -> tuple[int, int] | None:
        """Parse HH:MM from release_data['airs_time'] if present and valid."""

        if not airs_time:
            return None

        try:
            hour, minute = [int(x) for x in str(airs_time).split(":", 1)]
            return hour, minute
        except Exception:
            return None

    @staticmethod
    def _valid_weekdays(series_airs_days: SeriesAirsDays | None) -> list[int]:
        """Return list of weekday indices [0..6] marked True in release_data['airs_days']."""

        if not series_airs_days:
            return []

        day_map = [
            "monday",
            "tuesday",
            "wednesday",
            "thursday",
            "friday",
            "saturday",
            "sunday",
        ]

        return [
            i
            for i, name in enumerate(day_map)
            if getattr(series_airs_days, name) is True
        ]
