import threading
from concurrent.futures import Future
from datetime import datetime, timedelta

from program.managers.event_manager import EventManager, FutureWithEvent
from program.media.state import States
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
