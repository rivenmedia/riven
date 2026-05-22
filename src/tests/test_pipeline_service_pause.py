"""Per-service pipeline dispatch pause (in-memory)."""

from __future__ import annotations

from concurrent.futures import Future
from datetime import datetime
from threading import Event as ThreadingEvent
from unittest.mock import Mock, patch

from program.managers.event_manager import EventManager, FutureWithEvent
from program.media.state import States
from program.queue.mapping import pipeline_phase_to_kanban
from program.queue.pipeline_services import PIPELINE_DISPATCH_SERVICES
from program.types import Event


def test_get_pipeline_services_paused_all_services():
    em = EventManager()
    paused = em.get_pipeline_services_paused()
    assert set(paused) == set(PIPELINE_DISPATCH_SERVICES)
    assert all(v is False for v in paused.values())


def test_pause_resume_pipeline_service():
    em = EventManager()
    assert em.pause_pipeline_service("IndexerService")
    assert em.is_pipeline_service_paused("IndexerService")
    assert em.get_pipeline_services_paused()["IndexerService"] is True
    assert not em.pause_pipeline_service("NotAService")
    em.resume_pipeline_service("IndexerService")
    assert not em.is_pipeline_service_paused("IndexerService")


def test_dispatch_due_jobs_skips_paused_service():
    em = EventManager()
    now = datetime.now()
    indexer = Mock()
    indexer.initialized = True
    indexer.__class__.__name__ = "IndexerService"

    em._queued_events = [
        Event(
            emitted_by="IndexerService",
            item_id=42,
            item_state=States.Unknown,
            run_at=now,
        ),
    ]

    program = Mock()
    program.services = Mock()
    program.services.indexer = indexer
    program.services.scraping = Mock()
    program.services.scraping.initialized = False
    program.services.downloader = Mock()
    program.services.downloader.initialized = False
    program.services.filesystem = Mock()
    program.services.filesystem.initialized = False
    program.services.updater = Mock()
    program.services.updater.initialized = False
    program.services.post_processing = Mock()
    program.services.post_processing.initialized = False

    submitted: list[Event | None] = []

    def fake_submit(_service, _program, event):
        submitted.append(event)
        pending = Future()
        em._futures.append(
            FutureWithEvent(
                future=pending,
                event=event,
                cancellation_event=ThreadingEvent(),
            )
        )

    em.pause_pipeline_service("IndexerService")

    with patch.object(em, "submit_job", side_effect=fake_submit):
        dispatched = em.dispatch_due_jobs(program)

    assert dispatched == 0
    assert not submitted
    assert len(em._queued_events) == 1

    em.resume_pipeline_service("IndexerService")

    unknown_item = Mock()
    unknown_item.id = 42
    unknown_item.last_state = States.Unknown
    unknown_item.log_string = "item"

    with (
        patch(
            "program.managers.event_manager.db_functions.get_item_by_id",
            return_value=unknown_item,
        ),
        patch("program.state_transition.di") as mock_di,
        patch.object(em, "submit_job", side_effect=fake_submit),
    ):
        mock_di.__getitem__.return_value = program
        dispatched = em.dispatch_due_jobs(program)

    assert dispatched == 1
    assert submitted and submitted[0].item_id == 42


def test_completed_state_maps_to_post_process_column():
    from program.queue.mapping import resolve_pipeline_phase

    phase = resolve_pipeline_phase(
        item_state=States.Completed,
        deferred=False,
        in_flight_service=None,
    )
    assert pipeline_phase_to_kanban(phase) == "post_process"
