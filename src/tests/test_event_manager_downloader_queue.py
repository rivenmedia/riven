import threading
from concurrent.futures import Future
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch

from program.managers.event_manager import EventManager, FutureWithEvent
from program.media.state import States
from program.services.downloaders import Downloader
from program.types import Event


def test_event_has_queued_at():
    before = datetime.now()
    event = Event(emitted_by="StateTransition", item_id=1)
    after = datetime.now()
    assert before <= event.queued_at <= after
    assert before <= event.run_at <= after


def test_get_downloader_queued_items_filters_and_defers():
    em = EventManager()
    now = datetime.now()

    scraped_event = Event(
        emitted_by="StateTransition",
        item_id=10,
        item_state=States.Scraped,
        run_at=now,
    )
    downloader_deferred = Event(
        emitted_by="Downloader",
        item_id=11,
        item_state=States.Downloaded,
        run_at=now + timedelta(minutes=5),
    )

    indexer_event = Event(
        emitted_by="StateTransition",
        item_id=12,
        item_state=States.Indexed,
        run_at=now,
    )

    em._queued_events = [scraped_event, downloader_deferred, indexer_event]

    rows = em.get_downloader_queued_items()
    ids = {r["item_id"] for r in rows}

    assert 10 in ids
    assert 11 in ids
    assert 12 not in ids

    deferred_row = next(r for r in rows if r["item_id"] == 11)
    assert deferred_row["deferred"] is True
    assert deferred_row["emitted_by"] == "Downloader"

    ready_row = next(r for r in rows if r["item_id"] == 10)
    assert ready_row["deferred"] is False


def test_add_event_to_queue_upserts_duplicate_item_id():
    em = EventManager()
    now = datetime.now()

    first = Event(emitted_by="RetryLibrary", item_id=42, run_at=now)
    second = Event(
        emitted_by="Downloader",
        item_id=42,
        run_at=now + timedelta(minutes=5),
    )

    em.add_event_to_queue(first)
    em.add_event_to_queue(second, log_message=False)

    assert len(em._queued_events) == 1
    assert em._queued_events[0].run_at == second.run_at


def test_get_downloader_queue_snapshot_dedupes_by_item_id():
    em = EventManager()
    now = datetime.now()

    em._queued_events = [
        Event(
            emitted_by="RetryLibrary",
            item_id=7,
            item_state=States.Scraped,
            run_at=now + timedelta(minutes=10),
        ),
        Event(
            emitted_by="RetryLibrary",
            item_id=7,
            item_state=States.Scraped,
            run_at=now + timedelta(minutes=1),
        ),
        Event(
            emitted_by="RetryLibrary",
            item_id=7,
            item_state=States.Scraped,
            run_at=now,
        ),
    ]

    stats, rows = em.get_downloader_queue_snapshot()

    assert stats["total_queued"] == 1
    assert len(rows) == 1
    assert rows[0]["item_id"] == 7
    assert rows[0]["deferred"] is False


def test_get_downloader_queued_items_orders_due_before_deferred():
    em = EventManager()
    now = datetime.now()

    deferred_far = Event(
        emitted_by="StateTransition",
        item_id=20,
        item_state=States.Scraped,
        run_at=now + timedelta(hours=2),
    )
    due_soon = Event(
        emitted_by="StateTransition",
        item_id=21,
        item_state=States.Scraped,
        run_at=now - timedelta(minutes=1),
    )
    deferred_soon = Event(
        emitted_by="Downloader",
        item_id=22,
        item_state=States.Scraped,
        run_at=now + timedelta(minutes=1),
    )

    em._queued_events = [deferred_far, due_soon, deferred_soon]

    rows = em.get_downloader_queued_items()
    assert [r["item_id"] for r in rows] == [21, 22, 20]


def test_get_event_updates_ignores_completed_futures():
    em = EventManager()
    done_future: Future[int] = Future()
    done_future.set_result(99)
    pending_future: Future[int] = Future()

    em._futures = [
        FutureWithEvent(
            future=done_future,
            event=Event(emitted_by="Downloader", item_id=1),
            cancellation_event=threading.Event(),
        ),
        FutureWithEvent(
            future=pending_future,
            event=Event(emitted_by="Downloader", item_id=2),
            cancellation_event=threading.Event(),
        ),
    ]

    updates = em.get_event_updates()

    assert updates["Downloader"] == [2]


def test_get_downloader_queue_snapshot_queue_by_source():
    em = EventManager()
    now = datetime.now()

    em._queued_events = [
        Event(
            emitted_by="StateTransition",
            item_id=1,
            item_state=States.Scraped,
            run_at=now,
        ),
        Event(
            emitted_by="RetryLibrary",
            item_id=2,
            item_state=States.Scraped,
            run_at=now,
        ),
        Event(
            emitted_by="Downloader",
            item_id=3,
            item_state=States.Downloaded,
            run_at=now + timedelta(minutes=1),
        ),
    ]

    stats, _ = em.get_downloader_queue_snapshot()

    assert stats["queue_by_source"] == {
        "StateTransition": 1,
        "RetryLibrary": 1,
        "Downloader": 1,
    }
    assert stats["downloader_emitted"] == 1


def test_get_downloader_queue_stats_ready_and_total():
    em = EventManager()
    now = datetime.now()

    em._queued_events = [
        Event(
            emitted_by="StateTransition",
            item_id=1,
            item_state=States.Scraped,
            run_at=now,
        ),
        Event(
            emitted_by="StateTransition",
            item_id=2,
            item_state=States.Scraped,
            run_at=now + timedelta(minutes=5),
        ),
        Event(
            emitted_by="StateTransition",
            item_id=3,
            item_state=States.Indexed,
            run_at=now,
        ),
    ]

    stats = em.get_downloader_queue_stats()

    assert stats["scraped_queued"] == 2
    assert stats["scraped_ready"] == 1
    assert stats["deferred"] == 1
    assert stats["total_queued"] == 2
    assert stats["next_ready_in_seconds"] is not None
    assert 4 * 60 <= stats["next_ready_in_seconds"] <= 5 * 60 + 1


def test_submit_job_requeues_when_downloader_busy():
    em = EventManager()
    downloader = Downloader()
    downloader.initialized = True
    downloader.min_job_interval_seconds = 0.2

    pending_future: Future[int] = Future()
    em._futures = [
        FutureWithEvent(
            future=pending_future,
            event=Event(emitted_by=downloader, item_id=99),
            cancellation_event=threading.Event(),
        )
    ]

    program = Mock()
    program.services = Mock()
    program.services.downloader = downloader
    program.services.__getitem__ = lambda _self, key: downloader

    event = Event(emitted_by=downloader, item_id=42)

    with (
        patch.object(em, "add_event_to_queue") as mock_queue,
        patch.object(downloader, "pause_until", return_value=None),
        patch.object(em, "_find_or_create_executor"),
    ):
        em.submit_job(downloader, program, event)

    mock_queue.assert_called_once()
    assert len(em._futures) == 1
    queued_event = mock_queue.call_args[0][0]
    assert queued_event.item_id == 42


def test_add_event_skips_when_item_running():
    em = EventManager()
    running = Event(emitted_by=Downloader, item_id=7)
    em._running_events = [running]

    assert em.add_event(Event(emitted_by="StateTransition", item_id=7)) is False
    assert not em._queued_events


def _three_due_scraped_events(now: datetime) -> list[Event]:
    return [
        Event(
            emitted_by="StateTransition",
            item_id=1,
            item_state=States.Scraped,
            run_at=now - timedelta(minutes=3),
        ),
        Event(
            emitted_by="StateTransition",
            item_id=2,
            item_state=States.Scraped,
            run_at=now - timedelta(minutes=2),
        ),
        Event(
            emitted_by="StateTransition",
            item_id=3,
            item_state=States.Scraped,
            run_at=now - timedelta(minutes=1),
        ),
    ]


def test_prioritize_downloader_queue_item_moves_to_front():
    em = EventManager()
    now = datetime.now()
    em._queued_events = _three_due_scraped_events(now)

    assert em.prioritize_downloader_queue_item(3) is True
    assert [r["item_id"] for r in em.get_downloader_queued_items()] == [3, 1, 2]


def test_deprioritize_downloader_queue_item_moves_to_back():
    em = EventManager()
    now = datetime.now()
    em._queued_events = _three_due_scraped_events(now)

    assert em.deprioritize_downloader_queue_item(1) is True
    assert [r["item_id"] for r in em.get_downloader_queued_items()] == [2, 3, 1]


def test_prioritize_deferred_only_queue_makes_item_due_and_first():
    em = EventManager()
    now = datetime.now()
    em._queued_events = [
        Event(
            emitted_by="StateTransition",
            item_id=10,
            item_state=States.Scraped,
            run_at=now + timedelta(minutes=10),
        ),
        Event(
            emitted_by="StateTransition",
            item_id=11,
            item_state=States.Scraped,
            run_at=now + timedelta(minutes=20),
        ),
    ]

    assert em.prioritize_downloader_queue_item(11) is True
    rows = em.get_downloader_queued_items()
    assert rows[0]["item_id"] == 11
    assert rows[0]["deferred"] is False


def test_reorder_returns_false_for_unknown_or_running():
    em = EventManager()
    now = datetime.now()
    em._queued_events = _three_due_scraped_events(now)

    assert em.prioritize_downloader_queue_item(99) is False
    assert em.deprioritize_downloader_queue_item(99) is False

    em._running_events = [Event(emitted_by=Downloader, item_id=2)]
    assert em.prioritize_downloader_queue_item(2) is False
    assert em.deprioritize_downloader_queue_item(2) is False
