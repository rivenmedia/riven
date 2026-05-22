from datetime import datetime, timedelta

from program.media.state import States
from program.queue.mapping import stage_for_state
from program.queue.models import EnqueueResult, PipelineStage, QueueEntry
from program.queue.store import PipelineQueueStore, _sort_tuple


def _entry(
    item_id: int,
    state: States,
    *,
    run_at: datetime | None = None,
    emitted_by: str = "StateTransition",
) -> QueueEntry:
    now = datetime.now()
    return QueueEntry(
        item_id=item_id,
        item_state=state,
        run_at=run_at or now,
        queued_at=now,
        emitted_by=emitted_by,
    )


def test_enqueue_dedupes_and_merges_run_at():
    store = PipelineQueueStore()
    now = datetime.now()
    store.enqueue(_entry(1, States.Scraped, run_at=now))
    result = store.enqueue(
        _entry(1, States.Scraped, run_at=now + timedelta(minutes=5))
    )
    assert result == EnqueueResult.merged
    assert store.contains_item(1)
    assert len(store.all_item_entries()) == 1
    assert store.get(1).run_at == now + timedelta(minutes=5)


def test_enqueue_moves_stage_when_state_changes():
    store = PipelineQueueStore()
    store.enqueue(_entry(2, States.Indexed))
    store.update_state(2, States.Scraped)
    assert store.get(2).item_state == States.Scraped
    assert stage_for_state(States.Scraped) == PipelineStage.download
    counts = store.count_by_stage()
    assert counts[PipelineStage.scrape] == 0
    assert counts[PipelineStage.download] == 1


def test_pop_due_orders_due_before_deferred():
    store = PipelineQueueStore()
    now = datetime.now()
    store.enqueue(
        _entry(10, States.Scraped, run_at=now + timedelta(minutes=10))
    )
    store.enqueue(_entry(11, States.Scraped, run_at=now))
    first = store.pop_due(PipelineStage.download, now)
    assert first is not None
    assert first.item_id == 11
    second = store.pop_due(PipelineStage.download, now)
    assert second is None


def test_peek_ordered_does_not_remove():
    store = PipelineQueueStore()
    now = datetime.now()
    store.enqueue(_entry(20, States.Scraped, run_at=now + timedelta(minutes=1)))
    store.enqueue(_entry(21, States.Scraped, run_at=now))
    peeked = store.peek_ordered(PipelineStage.download, now, limit=5)
    assert [e.item_id for e in peeked] == [21, 20]
    assert store.contains_item(20)
    popped = store.pop_due(PipelineStage.download, now)
    assert popped.item_id == 21


def test_peek_then_pop_due_same_head():
    store = PipelineQueueStore()
    now = datetime.now()
    store.enqueue(_entry(30, States.Symlinked, run_at=now))
    due_peek = store.peek_due(PipelineStage.update, now, limit=1)
    assert due_peek[0].item_id == 30
    popped = store.pop_due(PipelineStage.update, now)
    assert popped.item_id == 30


def test_update_run_at_reprioritizes():
    store = PipelineQueueStore()
    now = datetime.now()
    store.enqueue(_entry(40, States.Scraped, run_at=now))
    store.enqueue(_entry(41, States.Scraped, run_at=now + timedelta(minutes=5)))
    store.update_run_at(41, now - timedelta(seconds=1))
    first = store.pop_due(PipelineStage.download, now)
    assert first.item_id == 41


def test_stats_and_display_truncation():
    store = PipelineQueueStore()
    now = datetime.now()
    for i in range(60):
        store.enqueue(_entry(100 + i, States.Indexed, run_at=now))
    stats = store.stats(now)
    assert stats.total_queued == 60
    assert stats.column_counts["scrape"] == 60
    rows, truncated = store.peek_display_for_kanban("scrape", now, limit=50)
    assert truncated is True
    assert len(rows) == 50


def test_lazy_heap_after_many_updates():
    store = PipelineQueueStore()
    now = datetime.now()
    store.enqueue(_entry(50, States.Completed))
    for _ in range(20):
        store.update_run_at(50, now + timedelta(seconds=1))
    popped = store.pop_due(PipelineStage.post_process, now + timedelta(seconds=2))
    assert popped is not None
    assert popped.item_id == 50


def test_enqueue_many_skips_existing():
    store = PipelineQueueStore()
    store.enqueue(_entry(60, States.Scraped))
    added = store.enqueue_many(
        [_entry(60, States.Scraped), _entry(61, States.Scraped)]
    )
    assert added == 1
    assert len(store.all_item_entries()) == 2
