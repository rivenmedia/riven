"""Tests for the scheduling system's edge cases and durability."""
from __future__ import annotations

import os
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine, text
from testcontainers.postgres import PostgresContainer

from program.db.db import db, run_migrations
from program.media.item import Episode, Movie, Show, Season
from program.media.state import States
from program.scheduling.models import ScheduledTask, ScheduledStatus


@pytest.fixture(scope="session")
def test_container():
    """One container for the whole test session."""
    with PostgresContainer(
        "postgres:16.4-alpine3.20",
        username="postgres",
        password="postgres",
        dbname="riven",
    ) as pg:
        yield pg


@pytest.fixture(scope="session")
def db_engine(test_container):
    """One engine + one migrated schema for the whole test session."""
    url = test_container.get_connection_url()
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg2://", 1)

    # Ensure Alembic env.py uses this test URL (it reads from settings_manager)
    from program.settings.manager import settings_manager
    settings_manager.settings.database.host = url

    run_migrations(database_url=url)

    engine = create_engine(url, future=True, pool_pre_ping=True)

    with engine.connect() as conn:
        conn = conn.execution_options(isolation_level="AUTOCOMMIT")
        conn.execute(text("SET synchronous_commit = OFF"))

    db.engine = engine
    db.Session.configure(bind=engine)

    yield engine
    engine.dispose()


@pytest.fixture(scope="function")
def test_scoped_db_session(db_engine):
    """Hand out a Session for each test. After each test, TRUNCATE all tables."""
    session = db.Session()
    try:
        yield session
    finally:
        session.close()
        with db_engine.connect() as conn:
            tables = conn.execute(
                text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
            ).scalars().all()
            if tables:
                quoted = ", ".join(f'"public"."{t}"' for t in tables)
                conn.execute(text(f"TRUNCATE {quoted} RESTART IDENTITY CASCADE"))
                conn.commit()


# Helper functions

def _create_episode(session, aired_at: datetime | None = None, **kwargs) -> Episode:
    """Create and persist an episode with required parent hierarchy.

    Creates a Show -> Season -> Episode chain and returns the persisted Episode.
    Respects optional overrides like number, last_state, and season_number.
    """
    # Create parent Show
    show = Show({"title": "Test Show"})
    session.add(show)
    session.flush()

    # Create parent Season
    season_number = kwargs.pop("season_number", 1)
    season = Season({"number": season_number})  # type: ignore[name-defined]
    season.parent = show
    session.add(season)
    session.flush()

    # Create Episode
    defaults = {
        "title": "Test Episode",
        "number": kwargs.pop("number", 1),
        "aired_at": aired_at,
    }
    ep = Episode(defaults)
    ep.parent = season

    # Optional last_state handling for tests
    last_state = kwargs.pop("last_state", None)
    if last_state is not None:
        ep.last_state = last_state  # type: ignore[assignment]

    session.add(ep)
    session.commit()
    session.refresh(ep)
    return ep


def _create_movie(session, aired_at: datetime | None = None, **kwargs) -> Movie:
    """Create and persist a movie with optional aired_at time and last_state."""
    defaults = {
        "title": "Test Movie",
        "tmdb_id": "12345",
        "aired_at": aired_at,
    }
    mv = Movie(defaults)

    # Optional last_state
    last_state = kwargs.pop("last_state", None)
    if last_state is not None:
        mv.last_state = last_state  # type: ignore[assignment]

    session.add(mv)
    session.commit()
    session.refresh(mv)
    return mv


def _create_show(session, release_data: dict | None = None, **kwargs) -> Show:
    """Create and persist a show with optional release_data and last_state."""
    defaults = {
        "title": "Test Show",
        "tvdb_id": "67890",
        "release_data": release_data or {},
    }
    show = Show(defaults)

    # Optional last_state
    last_state = kwargs.pop("last_state", None)
    if last_state is not None:
        show.last_state = last_state  # type: ignore[assignment]

    session.add(show)
    session.commit()
    session.refresh(show)
    return show


# Core scheduling functionality tests

class TestCoreScheduling:
    """Test core scheduling functionality."""

    def test_schedule_creates_task_with_valid_aired_at(self, test_scoped_db_session):
        """Scheduling tasks with valid aired_at times creates ScheduledTask entries."""
        session = test_scoped_db_session
        future_time = datetime.now() + timedelta(hours=2)
        ep = _create_episode(session, aired_at=future_time)

        run_at = future_time + timedelta(minutes=30)
        result = ep.schedule(run_at, task_type="episode_release", offset_seconds=1800)

        assert result is True
        task = session.query(ScheduledTask).filter_by(item_id=ep.id).first()
        assert task is not None
        assert task.task_type == "episode_release"
        assert task.scheduled_for == run_at
        assert task.status == ScheduledStatus.Pending
        assert task.offset_seconds == 1800

    def test_schedule_idempotency_via_unique_index(self, test_scoped_db_session):
        """Scheduling the same task twice doesn't create duplicates (via unique index)."""
        session = test_scoped_db_session
        future_time = datetime.now() + timedelta(hours=2)
        ep = _create_episode(session, aired_at=future_time)

        run_at = future_time + timedelta(minutes=30)
        result1 = ep.schedule(run_at, task_type="episode_release")
        result2 = ep.schedule(run_at, task_type="episode_release")

        assert result1 is True
        assert result2 is False  # Should return False due to duplicate
        task_count = session.query(ScheduledTask).filter_by(item_id=ep.id).count()
        assert task_count == 1

    def test_schedule_refuses_past_tasks(self, test_scoped_db_session):
        """Refusing to schedule tasks in the past."""
        session = test_scoped_db_session
        past_time = datetime.now() - timedelta(hours=1)
        ep = _create_episode(session)

        result = ep.schedule(past_time, task_type="episode_release")

        assert result is False
        task_count = session.query(ScheduledTask).filter_by(item_id=ep.id).count()
        assert task_count == 0

    def test_schedule_refuses_now_tasks(self, test_scoped_db_session):
        """Refusing to schedule tasks at exactly now."""
        session = test_scoped_db_session
        now = datetime.now()
        ep = _create_episode(session)

        result = ep.schedule(now, task_type="episode_release")

        assert result is False
        task_count = session.query(ScheduledTask).filter_by(item_id=ep.id).count()
        assert task_count == 0


# Tests for _compute_next_air_datetime edge cases

class TestComputeNextAirDatetime:
    """Test edge cases for _compute_next_air_datetime()."""

    def test_compute_from_airs_days_and_time_when_next_aired_missing(self):
        """Computing next air time from airs_days + airs_time when next_aired is missing."""
        from program.program import Program

        now = datetime(2025, 1, 13, 10, 0, 0)  # Monday 10:00 AM
        release_data = {
            "airs_days": {
                "monday": False,
                "tuesday": True,
                "wednesday": False,
                "thursday": False,
                "friday": False,
                "saturday": False,
                "sunday": False,
            },
            "airs_time": "20:00",
        }

        result = Program._compute_next_air_datetime(release_data, now)

        assert result is not None
        assert result.weekday() == 1  # Tuesday
        assert result.hour == 20
        assert result.minute == 0
        # Should be next Tuesday at 20:00
        expected = datetime(2025, 1, 14, 20, 0, 0)
        assert result == expected

    def test_handle_next_aired_as_date_only_string(self):
        """Handling next_aired as a date-only string (should combine with airs_time)."""
        from program.program import Program

        now = datetime(2025, 1, 13, 10, 0, 0)
        release_data = {
            "next_aired": "2025-01-15",
            "airs_time": "21:30",
        }

        result = Program._compute_next_air_datetime(release_data, now)

        assert result is not None
        assert result.year == 2025
        assert result.month == 1
        assert result.day == 15
        assert result.hour == 21
        assert result.minute == 30

    def test_handle_next_aired_as_full_iso_datetime(self):
        """Handling next_aired as a full ISO datetime string."""
        from program.program import Program

        now = datetime(2025, 1, 13, 10, 0, 0)
        release_data = {
            "next_aired": "2025-01-15T22:00:00",
        }

        result = Program._compute_next_air_datetime(release_data, now)

        assert result is not None
        assert result == datetime(2025, 1, 15, 22, 0, 0)

    def test_graceful_fallback_when_timezone_invalid(self):
        """Graceful fallback when timezone is invalid or missing."""
        from program.program import Program

        now = datetime(2025, 1, 13, 10, 0, 0)
        release_data = {
            "next_aired": "2025-01-15T22:00:00",
            "timezone": "Invalid/Timezone",
        }

        result = Program._compute_next_air_datetime(release_data, now)

        # Should still return a result, treating as local naive
        assert result is not None
        assert result == datetime(2025, 1, 15, 22, 0, 0)

    def test_return_none_when_no_valid_air_time(self):
        """Returning None when no valid air time can be computed."""
        from program.program import Program

        now = datetime(2025, 1, 13, 10, 0, 0)
        release_data = {}

        result = Program._compute_next_air_datetime(release_data, now)

        assert result is None

    def test_handle_malformed_airs_time(self):
        """Handling malformed or missing airs_time values."""
        from program.program import Program

        now = datetime(2025, 1, 13, 10, 0, 0)
        release_data = {
            "airs_days": {"monday": True},
            "airs_time": "invalid",
        }

        result = Program._compute_next_air_datetime(release_data, now)

        assert result is None


# Monitoring and processing tests

class TestMonitoringAndProcessing:
    """Test monitoring and processing of scheduled tasks."""

    @patch("program.program.settings_manager")
    def test_monitor_creates_tasks_for_upcoming_episodes(
        self, mock_settings, test_scoped_db_session
    ):
        """_monitor_ongoing_schedules() creates tasks for upcoming episodes with future aired_at."""
        from program.program import Program

        session = test_scoped_db_session
        future_time = datetime.now() + timedelta(hours=24)
        ep = _create_episode(session, aired_at=future_time)

        # Mock settings
        mock_settings.settings.indexer.schedule_offset_minutes = 30

        program = Program()
        program._monitor_ongoing_schedules()

        # Check that a task was created
        task = session.query(ScheduledTask).filter_by(item_id=ep.id).first()
        assert task is not None
        assert task.task_type == "episode_release"
        assert task.status == ScheduledStatus.Pending

    @patch("program.program.settings_manager")
    def test_monitor_creates_tasks_for_upcoming_movies(
        self, mock_settings, test_scoped_db_session
    ):
        """_monitor_ongoing_schedules() creates tasks for upcoming movies with future aired_at."""
        from program.program import Program

        session = test_scoped_db_session
        future_time = datetime.now() + timedelta(hours=48)
        mv = _create_movie(session, aired_at=future_time)

        mock_settings.settings.indexer.schedule_offset_minutes = 30

        program = Program()
        program._monitor_ongoing_schedules()

        task = session.query(ScheduledTask).filter_by(item_id=mv.id).first()
        assert task is not None
        assert task.task_type == "movie_release"
        assert task.status == ScheduledStatus.Pending

    @patch("program.program.settings_manager")
    def test_monitor_creates_reindex_for_ongoing_shows(
        self, mock_settings, test_scoped_db_session
    ):
        """_monitor_ongoing_schedules() creates reindex tasks for ongoing shows based on computed next air time."""
        from program.program import Program

        session = test_scoped_db_session
        now = datetime.now()
        # Create a show with airs_days/time that will compute a future air time
        release_data = {
            "airs_days": {
                "monday": True,
                "tuesday": False,
                "wednesday": False,
                "thursday": False,
                "friday": False,
                "saturday": False,
                "sunday": False,
            },
            "airs_time": "20:00",
        }
        show = _create_show(session, release_data=release_data, last_state=States.Ongoing)

        mock_settings.settings.indexer.schedule_offset_minutes = 30

        program = Program()
        program._monitor_ongoing_schedules()

        task = session.query(ScheduledTask).filter_by(item_id=show.id).first()
        assert task is not None
        assert task.task_type == "reindex_show"
        assert task.status == ScheduledStatus.Pending

    @patch("program.program.settings_manager")
    def test_monitor_creates_daily_fallback_for_shows_without_hints(
        self, mock_settings, test_scoped_db_session
    ):
        """_monitor_ongoing_schedules() creates daily fallback reindex tasks for shows with no air time hints."""
        from program.program import Program

        session = test_scoped_db_session
        # Show with no useful release_data
        show = _create_show(session, release_data={}, last_state=States.Ongoing)

        mock_settings.settings.indexer.schedule_offset_minutes = 30

        program = Program()
        program._monitor_ongoing_schedules()

        task = session.query(ScheduledTask).filter_by(item_id=show.id).first()
        assert task is not None
        assert task.task_type == "reindex_show"
        assert task.status == ScheduledStatus.Pending
        # Should be scheduled for tomorrow
        assert task.scheduled_for > datetime.now()

    @patch("program.program.settings_manager")
    def test_monitor_creates_daily_fallback_for_movies_without_release_date(
        self, mock_settings, test_scoped_db_session
    ):
        """_monitor_ongoing_schedules() creates daily fallback reindex tasks for movies with unknown release dates."""
        from program.program import Program

        session = test_scoped_db_session
        # Movie with no aired_at
        mv = _create_movie(session, aired_at=None, last_state=States.Unreleased)

        mock_settings.settings.indexer.schedule_offset_minutes = 30

        program = Program()
        program._monitor_ongoing_schedules()

        task = session.query(ScheduledTask).filter_by(item_id=mv.id).first()
        assert task is not None
        assert task.task_type == "reindex_movie"
        assert task.status == ScheduledStatus.Pending

    @patch("program.program.settings_manager")
    @patch("program.program.IndexerService")
    def test_process_scheduled_tasks_marks_completed(
        self, mock_indexer_service, mock_settings, test_scoped_db_session
    ):
        """_process_scheduled_tasks() correctly processes due tasks and updates their status to Completed."""
        from program.program import Program

        session = test_scoped_db_session
        ep = _create_episode(session)

        # Create a due task
        past_time = datetime.now() - timedelta(minutes=5)
        task = ScheduledTask(
            item_id=ep.id,
            task_type="episode_release",
            scheduled_for=past_time,
            status=ScheduledStatus.Pending,
        )
        session.add(task)
        session.commit()

        mock_settings.settings.indexer.schedule_offset_minutes = 30

        program = Program()
        program.em = MagicMock()  # Mock event manager
        program.services = MagicMock()
        program._process_scheduled_tasks()

        # Refresh task from DB
        session.refresh(task)
        assert task.status == ScheduledStatus.Completed
        assert task.executed_at is not None

    @patch("program.program.settings_manager")
    def test_process_scheduled_tasks_marks_failed_when_item_missing(
        self, mock_settings, test_scoped_db_session
    ):
        """_process_scheduled_tasks() marks tasks as Failed when the item no longer exists."""
        from program.program import Program

        session = test_scoped_db_session

        # Create a task for a non-existent item
        past_time = datetime.now() - timedelta(minutes=5)
        task = ScheduledTask(
            item_id=99999,  # Non-existent item
            task_type="episode_release",
            scheduled_for=past_time,
            status=ScheduledStatus.Pending,
        )
        session.add(task)
        session.commit()

        mock_settings.settings.indexer.schedule_offset_minutes = 30

        program = Program()
        program._process_scheduled_tasks()

        session.refresh(task)
        assert task.status == ScheduledStatus.Failed
        assert task.executed_at is not None

    @patch("program.program.settings_manager")
    @patch("program.program.IndexerService")
    def test_process_handles_exceptions_gracefully(
        self, mock_indexer_service, mock_settings, test_scoped_db_session
    ):
        """_process_scheduled_tasks() handles exceptions gracefully and marks tasks as Failed with proper rollback."""
        from program.program import Program

        session = test_scoped_db_session
        ep = _create_episode(session)

        past_time = datetime.now() - timedelta(minutes=5)
        task = ScheduledTask(
            item_id=ep.id,
            task_type="episode_release",
            scheduled_for=past_time,
            status=ScheduledStatus.Pending,
        )
        session.add(task)
        session.commit()

        mock_settings.settings.indexer.schedule_offset_minutes = 30

        program = Program()
        program.em = MagicMock()
        program.em.add_event.side_effect = Exception("Test exception")
        program.services = MagicMock()

        # Should not raise, should handle gracefully
        program._process_scheduled_tasks()

        session.refresh(task)
        assert task.status == ScheduledStatus.Failed
        assert task.executed_at is not None


# State transition tests

class TestStateTransitions:
    """Test state transitions for scheduled tasks."""

    @patch("program.program.settings_manager")
    def test_scheduled_tasks_enqueue_events_for_episodes(
        self, mock_settings, test_scoped_db_session
    ):
        """Scheduled tasks for episodes/movies enqueue events to the EventManager."""
        from program.program import Program

        session = test_scoped_db_session
        ep = _create_episode(session, last_state=States.Indexed)

        past_time = datetime.now() - timedelta(minutes=5)
        task = ScheduledTask(
            item_id=ep.id,
            task_type="episode_release",
            scheduled_for=past_time,
            status=ScheduledStatus.Pending,
        )
        session.add(task)
        session.commit()

        mock_settings.settings.indexer.schedule_offset_minutes = 30

        program = Program()
        program.em = MagicMock()
        program.services = MagicMock()
        program._process_scheduled_tasks()

        # Verify event was enqueued
        program.em.add_event.assert_called_once()

    @patch("program.program.settings_manager")
    def test_reindex_tasks_call_indexer_service(
        self, mock_settings, test_scoped_db_session
    ):
        """Scheduled tasks for shows/movies with reindex_* task types call IndexerService."""
        from program.program import Program

        session = test_scoped_db_session
        show = _create_show(session, last_state=States.Ongoing)

        past_time = datetime.now() - timedelta(minutes=5)
        task = ScheduledTask(
            item_id=show.id,
            task_type="reindex_show",
            scheduled_for=past_time,
            status=ScheduledStatus.Pending,
        )
        session.add(task)
        session.commit()

        mock_settings.settings.indexer.schedule_offset_minutes = 30

        program = Program()
        mock_indexer = MagicMock()
        mock_indexer.run.return_value = iter([show])
        program.services = MagicMock()
        program.services.get.return_value = mock_indexer

        program._process_scheduled_tasks()

        # Verify indexer was called
        mock_indexer.run.assert_called_once()

    @patch("program.program.settings_manager")
    def test_completed_items_not_reenqueued(
        self, mock_settings, test_scoped_db_session
    ):
        """Completed items are not re-enqueued from scheduled tasks."""
        from program.program import Program

        session = test_scoped_db_session
        ep = _create_episode(session, last_state=States.Completed)

        past_time = datetime.now() - timedelta(minutes=5)
        task = ScheduledTask(
            item_id=ep.id,
            task_type="episode_release",
            scheduled_for=past_time,
            status=ScheduledStatus.Pending,
        )
        session.add(task)
        session.commit()

        mock_settings.settings.indexer.schedule_offset_minutes = 30

        program = Program()
        program.em = MagicMock()
        program.services = MagicMock()
        program._process_scheduled_tasks()

        # Verify event was NOT enqueued for completed item
        program.em.add_event.assert_not_called()


