"""Unit tests for pipeline queue stage / kanban mapping helpers."""

from program.media.state import States
from program.queue.mapping import (
    KANBAN_COLUMN_ORDER,
    dispatch_priority,
    pipeline_phase_for_entry,
    pipeline_phase_to_kanban,
    stage_for_state,
    stage_to_kanban,
    states_for_stage,
)
from program.queue.models import PipelineStage, QueueEntry
from datetime import datetime


def _entry(state: States, *, emitted_by: str = "StateTransition") -> QueueEntry:
    now = datetime.now()
    return QueueEntry(
        item_id=1,
        item_state=state,
        run_at=now,
        queued_at=now,
        emitted_by=emitted_by,
    )


def test_stage_for_state_pipeline_order():
    assert stage_for_state(States.Unknown) == PipelineStage.index
    assert stage_for_state(States.Indexed) == PipelineStage.scrape
    assert stage_for_state(States.Scraped) == PipelineStage.download
    assert stage_for_state(States.Downloaded) == PipelineStage.symlink
    assert stage_for_state(States.Symlinked) == PipelineStage.update
    assert stage_for_state(States.Completed) == PipelineStage.post_process


def test_states_for_stage_roundtrip_subset():
    scrape_states = states_for_stage(PipelineStage.scrape)
    assert States.Indexed in scrape_states
    assert States.Scraped not in scrape_states


def test_stage_to_kanban_known_columns():
    assert stage_to_kanban(PipelineStage.download) == "download"
    assert pipeline_phase_to_kanban("queued_download") == "download"


def test_pipeline_phase_for_entry_in_flight():
    now = datetime.now()
    entry = _entry(States.Scraped, emitted_by="Downloader")
    assert (
        pipeline_phase_for_entry(entry, now=now, in_flight_service="Downloader")
        == "downloading"
    )


def test_dispatch_priority_orders_by_state():
    scraped = _entry(States.Scraped)
    indexed = _entry(States.Indexed)
    assert dispatch_priority(scraped)[0] < dispatch_priority(indexed)[0]


def test_kanban_column_order_is_stable():
    assert KANBAN_COLUMN_ORDER[0] == "added"
    assert KANBAN_COLUMN_ORDER[-1] == "finish"
