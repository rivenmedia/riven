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
        patch.object(EventManager, "_pipeline_max_workers", return_value=1),
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


def test_pipeline_executor_uses_configured_max_workers():
    class FakeScraping:
        pass

    em = EventManager()
    with patch.object(EventManager, "_pipeline_max_workers", return_value=6):
        executor = em._find_or_create_executor(FakeScraping())
    assert executor._max_workers == 6


def test_submit_job_requeues_when_scraping_at_capacity():
    em = EventManager()
    pending_future: Future[int] = Future()
    em._futures = [
        FutureWithEvent(
            future=pending_future,
            event=Event(emitted_by="Scraping", item_id=1),
            cancellation_event=threading.Event(),
        )
    ]

    program = Mock()
    program.services = Mock()
    program.services.downloader = Mock()
    program.services.downloader.initialized = True
    program.services.downloader.pause_until = Mock(return_value=None)

    scraping = Mock()
    scraping.__class__.__name__ = "Scraping"
    scraping.get_key = Mock(return_value="scraping")

    event = Event(emitted_by=scraping, item_id=42)

    with (
        patch.object(em, "add_event_to_queue") as mock_queue,
        patch.object(EventManager, "_pipeline_max_workers", return_value=1),
        patch.object(em, "_find_or_create_executor"),
    ):
        em.submit_job(scraping, program, event)

    mock_queue.assert_called_once()
    assert event.item_id == 42


def test_dispatch_due_jobs_dispatches_unknown_state_to_indexer():
    em = EventManager()
    now = datetime.now()
    indexer = Mock()
    indexer.initialized = True
    indexer.__class__.__name__ = "IndexerService"

    em._queued_events = [
        Event(
            emitted_by="IndexerService",
            item_id=24182,
            item_state=States.Unknown,
            run_at=now,
        ),
    ]

    program = Mock()
    program.services = Mock()
    program.services.indexer = indexer
    program.services.scraping = Mock()
    program.services.scraping.initialized = True
    program.services.downloader = Mock()
    program.services.downloader.initialized = True
    program.services.downloader.pause_until = Mock(return_value=None)
    program.services.filesystem = Mock()
    program.services.filesystem.initialized = True
    program.services.updater = Mock()
    program.services.updater.initialized = True
    program.services.post_processing = Mock()
    program.services.post_processing.initialized = True

    unknown_item = Mock()
    unknown_item.id = 24182
    unknown_item.last_state = States.Unknown
    unknown_item.log_string = "BEEF"

    submitted: list[Event | None] = []

    def fake_submit(_service, _program, event):
        submitted.append(event)
        pending = Future()
        em._futures.append(
            FutureWithEvent(
                future=pending,
                event=event,
                cancellation_event=threading.Event(),
            )
        )

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
    assert len(submitted) == 1
    assert submitted[0] is not None
    assert submitted[0].item_id == 24182
    assert len(em._queued_events) == 0


def test_dispatch_due_jobs_removes_paused_items_from_queue():
    em = EventManager()
    now = datetime.now()

    em._queued_events = [
        Event(
            emitted_by="IndexerService",
            item_id=99,
            item_state=States.Unknown,
            run_at=now,
        ),
    ]

    program = Mock()
    program.services = Mock()
    program.services.indexer = Mock()
    program.services.indexer.initialized = True
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

    paused_item = Mock()
    paused_item.last_state = States.Paused
    paused_item.log_string = "Paused Show"

    with patch(
        "program.managers.event_manager.db_functions.get_item_by_id",
        return_value=paused_item,
    ):
        dispatched = em.dispatch_due_jobs(program)

    assert dispatched == 0
    assert len(em._queued_events) == 0


def test_dispatch_due_jobs_respects_scraping_capacity():
    from program.services.scrapers import Scraping
    from program.types import ProcessedEvent

    em = EventManager()
    now = datetime.now()
    scraping = Scraping()
    scraping.initialized = True

    em._queued_events = [
        Event(
            emitted_by="StateTransition",
            item_id=10,
            item_state=States.Indexed,
            run_at=now,
        ),
        Event(
            emitted_by="StateTransition",
            item_id=11,
            item_state=States.Indexed,
            run_at=now,
        ),
    ]

    program = Mock()
    program.services = Mock()
    program.services.indexer = Mock()
    program.services.indexer.initialized = True
    program.services.scraping = scraping
    program.services.downloader = Mock()
    program.services.downloader.initialized = True
    program.services.downloader.pause_until = Mock(return_value=None)
    program.services.filesystem = Mock()
    program.services.filesystem.initialized = True
    program.services.updater = Mock()
    program.services.updater.initialized = True
    program.services.post_processing = Mock()
    program.services.post_processing.initialized = True

    item = Mock()
    item.id = 10

    processed = ProcessedEvent(
        service=scraping,
        related_media_items=[item],
        overrides=None,
    )

    def fake_submit(_service, _program, event):
        pending = Future()
        em._futures.append(
            FutureWithEvent(
                future=pending,
                event=event,
                cancellation_event=threading.Event(),
            )
        )

    with (
        patch.object(EventManager, "_pipeline_max_workers", return_value=1),
        patch(
            "program.state_transition.process_event",
            return_value=processed,
        ),
        patch.object(em, "submit_job", side_effect=fake_submit),
    ):
        dispatched = em.dispatch_due_jobs(program)

    assert dispatched == 1
    assert len(em._queued_events) == 1


def test_restore_pipeline_from_db_enqueues_actionable_items():
    em = EventManager()
    scraping = Mock()
    scraping.initialized = True
    scraping.__class__.__name__ = "Scraping"

    program = Mock()
    program.services = Mock()
    program.services.updater = Mock()
    program.services.updater.initialized = False
    program.services.filesystem = Mock()
    program.services.filesystem.initialized = False
    program.services.downloader = Mock()
    program.services.downloader.initialized = False
    program.services.scraping = scraping
    program.services.indexer = Mock()
    program.services.indexer.initialized = False

    session = MagicMock()
    query_result = MagicMock()
    query_result.all.return_value = [(42, States.Indexed)]
    session.execute.return_value = query_result

    with (
        patch(
            "program.managers.event_manager.db_session",
            return_value=MagicMock(
                __enter__=MagicMock(return_value=session), __exit__=MagicMock()
            ),
        ),
        patch.object(em, "_item_id_in_pipeline", return_value=False),
        patch.object(em, "add_event", return_value=True) as mock_add,
    ):
        restored = em.restore_pipeline_from_db(program, source="startup")

    assert restored == [42]
    mock_add.assert_called_once()
    call_event = mock_add.call_args[0][0]
    assert call_event.item_id == 42
    assert call_event.item_state == States.Indexed


def test_restore_pipeline_queues_via_state_transition_when_service_down():
    em = EventManager()
    program = Mock()
    program.services = Mock()
    program.services.updater = Mock()
    program.services.updater.initialized = False
    program.services.filesystem = Mock()
    program.services.filesystem.initialized = False
    program.services.downloader = Mock()
    program.services.downloader.initialized = False
    program.services.scraping = Mock()
    program.services.scraping.initialized = False
    program.services.indexer = Mock()
    program.services.indexer.initialized = False

    session = MagicMock()
    query_result = MagicMock()
    query_result.all.return_value = [(7, States.Indexed)]
    session.execute.return_value = query_result

    with (
        patch(
            "program.managers.event_manager.db_session",
            return_value=MagicMock(
                __enter__=MagicMock(return_value=session), __exit__=MagicMock()
            ),
        ),
        patch.object(em, "_item_id_in_pipeline", return_value=False),
        patch.object(em, "add_event", return_value=True) as mock_add,
    ):
        restored = em.restore_pipeline_from_db(program, source="startup")

    assert restored == [7]
    call_event = mock_add.call_args[0][0]
    assert call_event.emitted_by == "StateTransition"


def test_pipeline_activity_set_and_clear():
    em = EventManager()
    em.set_pipeline_activity(99, "Downloading on Real-Debrid")
    assert em.get_pipeline_activities()[99] == "Downloading on Real-Debrid"
    em.clear_pipeline_activity(99)
    assert 99 not in em.get_pipeline_activities()


def test_get_pipeline_queue_snapshot_syncs_stale_item_state_from_db():
    """Activity columns must follow DB state, not cached state at enqueue time."""

    em = EventManager()
    now = datetime.now()

    em._queued_events = [
        Event(
            emitted_by="StateTransition",
            item_id=3369,
            item_state=States.Scraped,
            run_at=now,
        ),
    ]

    session = MagicMock()
    session.execute.return_value = [(3369, States.Downloaded)]

    with patch(
        "program.managers.event_manager.db_session",
        return_value=MagicMock(__enter__=MagicMock(return_value=session), __exit__=MagicMock()),
    ):
        _, rows = em.get_pipeline_queue_snapshot()

    row = next(r for r in rows if r["item_id"] == 3369)
    assert row["item_state"] == "Downloaded"
    assert row["kanban_column"] == "symlink"
    assert row["pipeline_phase"] == "queued_symlink"


def _patch_pipeline_db_states(states_by_id: dict[int, States]):
    session = MagicMock()
    session.execute.return_value = list(states_by_id.items())
    return patch(
        "program.managers.event_manager.db_session",
        return_value=MagicMock(
            __enter__=MagicMock(return_value=session), __exit__=MagicMock()
        ),
    )


def test_get_pipeline_queue_snapshot_includes_indexed():
    em = EventManager()
    now = datetime.now()

    em._queued_events = [
        Event(
            emitted_by="StateTransition",
            item_id=10,
            item_state=States.Scraped,
            run_at=now,
        ),
        Event(
            emitted_by="StateTransition",
            item_id=12,
            item_state=States.Indexed,
            run_at=now,
        ),
    ]

    with _patch_pipeline_db_states({10: States.Scraped, 12: States.Indexed}):
        stats, rows = em.get_pipeline_queue_snapshot()
    ids = {r["item_id"] for r in rows if r.get("item_id")}

    assert 10 in ids
    assert 12 in ids
    assert stats["phase_counts"].get("queued_scrape") == 1
    assert stats["column_counts"]["scrape"] == 1


def test_get_pipeline_queue_snapshot_in_flight_indexer():
    em = EventManager()
    pending_future: Future[int] = Future()

    em._futures = [
        FutureWithEvent(
            future=pending_future,
            event=Event(emitted_by="IndexerService", item_id=5),
            cancellation_event=threading.Event(),
        ),
    ]

    updates = em.get_event_updates()
    assert updates["IndexerService"] == [5]

    stats, rows = em.get_pipeline_queue_snapshot()
    in_flight = next(r for r in rows if r.get("item_id") == 5)
    assert in_flight["in_flight"] is True
    assert in_flight["pipeline_phase"] == "indexing"
    assert in_flight["kanban_column"] == "added"
    assert stats["column_counts"]["added"] == 1


def test_dequeue_pipeline_queue_item_removes_events_without_running():
    em = EventManager()
    now = datetime.now()
    em._queued_events = [
        Event(
            emitted_by="StateTransition",
            item_id=42,
            item_state=States.Indexed,
            run_at=now,
        ),
        Event(
            emitted_by="StateTransition",
            item_id=99,
            item_state=States.Scraped,
            run_at=now,
        ),
    ]

    assert em.dequeue_pipeline_queue_item(42) is True
    assert [e.item_id for e in em._queued_events] == [99]

    em._running_events = [
        Event(
            emitted_by="StateTransition",
            item_id=99,
            item_state=States.Scraped,
            run_at=now,
        )
    ]
    assert em.dequeue_pipeline_queue_item(99) is False
    assert [e.item_id for e in em._queued_events] == [99]


def test_prioritize_pipeline_queue_item_moves_indexed_peer():
    em = EventManager()
    now = datetime.now()

    em._queued_events = [
        Event(
            emitted_by="StateTransition",
            item_id=1,
            item_state=States.Indexed,
            run_at=now - timedelta(minutes=3),
        ),
        Event(
            emitted_by="StateTransition",
            item_id=2,
            item_state=States.Indexed,
            run_at=now - timedelta(minutes=1),
        ),
    ]

    assert em.prioritize_pipeline_queue_item(2) is True
    with _patch_pipeline_db_states({1: States.Indexed, 2: States.Indexed}):
        _, rows = em.get_pipeline_queue_snapshot()
    indexed_rows = [r for r in rows if r.get("pipeline_phase") == "queued_scrape"]
    assert [r["item_id"] for r in indexed_rows] == [2, 1]


def test_limit_pipeline_rows_per_column_keeps_download_visible():
    from program.managers.event_manager import limit_pipeline_rows_per_column

    now = datetime.now()
    rows = []
    for i in range(60):
        rows.append(
            {
                "kanban_column": "scrape",
                "in_flight": False,
                "deferred": False,
                "run_at": now + timedelta(seconds=i),
            }
        )
    rows.append(
        {
            "kanban_column": "download",
            "in_flight": False,
            "deferred": False,
            "run_at": now,
            "item_id": 999,
        }
    )

    limited, truncated = limit_pipeline_rows_per_column(rows, per_column_limit=50)
    download_rows = [r for r in limited if r["kanban_column"] == "download"]

    assert truncated is True
    assert len(download_rows) == 1
    assert download_rows[0]["item_id"] == 999


def test_pipeline_snapshot_column_counts_before_display_limit():
    em = EventManager()
    now = datetime.now()
    em._queued_events = [
        Event(
            emitted_by="StateTransition",
            item_id=i,
            item_state=States.Indexed,
            run_at=now + timedelta(seconds=i),
        )
        for i in range(1, 61)
    ]

    with _patch_pipeline_db_states({i: States.Indexed for i in range(1, 61)}):
        stats, rows = em.get_pipeline_queue_snapshot()

    assert stats["column_counts"]["scrape"] == 60
    assert len([r for r in rows if r["kanban_column"] == "scrape"]) == 50
    assert stats["total_items"] == 60


def test_post_process_phases_map_to_update_kanban():
    from program.managers.event_manager import pipeline_phase_to_kanban

    assert pipeline_phase_to_kanban("queued_post_process") == "update"
    assert pipeline_phase_to_kanban("post_processing") == "update"
    assert pipeline_phase_to_kanban("symlinking") == "symlink"


def test_record_recently_finished_failed_outcome():
    em = EventManager()
    em.record_recently_finished(
        7,
        outcome="failed",
        service_name="Downloader",
        failure_service="Downloader",
        completion_detail="No streams",
    )
    rows = em.get_recently_finished_rows()
    assert rows[0]["completion_outcome"] == "failed"
    assert rows[0]["failure_service"] == "Downloader"
    assert rows[0]["item_state"] == States.Failed.name


def test_retry_failed_pipeline_item_downloader(monkeypatch):
    from program.db import db_functions

    em = EventManager()
    em.record_recently_finished(
        5,
        outcome="failed",
        failure_service="Downloader",
        completion_detail="failed",
    )

    class FakeItem:
        id = 5
        last_state = States.Failed

        def store_state(self, state):
            self.last_state = state

    fake = FakeItem()
    monkeypatch.setattr(db_functions, "get_item_by_id", lambda i: fake if i == 5 else None)

    assert em.retry_failed_pipeline_item(5) is True
    assert fake.last_state == States.Scraped
    assert any(e.item_id == 5 for e in em._queued_events)
    assert 5 not in em._recently_finished


def test_recently_finished_rows_expire():
    em = EventManager()
    now = datetime.now()

    em.record_recently_finished(99, outcome="success", service_name="PostProcessing")
    rows = em.get_recently_finished_rows()
    assert len(rows) == 1
    assert rows[0]["item_id"] == 99
    assert rows[0]["pipeline_phase"] == "recently_finished"
    assert rows[0]["kanban_column"] == "finish"
    assert rows[0]["completion_outcome"] == "success"

    em._recently_finished[99] = em._recently_finished[99].__class__(
        item_id=99,
        completed_at=now - timedelta(minutes=3),
        outcome="success",
        service_name="PostProcessing",
    )
    assert em.get_recently_finished_rows() == []
