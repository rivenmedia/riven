from unittest.mock import MagicMock, patch

from program.managers.event_manager import EventManager
from program.media.state import States
from program.queue.models import PipelineStage


def test_restore_skips_completed_library_items():
    em = EventManager()
    program = MagicMock()
    program.services = MagicMock()
    for name in (
        "updater",
        "filesystem",
        "downloader",
        "scraping",
        "indexer",
        "post_processing",
    ):
        svc = MagicMock()
        svc.initialized = False
        setattr(program.services, name, svc)

    session = MagicMock()
    query_result = MagicMock()
    # DB query filters to _RESTORE_STATES; Completed rows are not returned.
    query_result.all.return_value = [(101, States.Scraped, "movie")]
    session.execute.return_value = query_result

    with (
        patch(
            "program.managers.event_manager.db_session",
            return_value=MagicMock(
                __enter__=MagicMock(return_value=session), __exit__=MagicMock()
            ),
        ),
        patch.object(em, "_item_id_in_pipeline", return_value=False),
        patch(
            "program.managers.event_manager.db_functions.get_item_ids",
            side_effect=lambda _session, item_id: (item_id, []),
        ),
    ):
        restored = em.restore_pipeline_from_db(program, source="startup")

    assert restored == [101]
    assert em._queue.count_by_stage().get(PipelineStage.post_process, 0) == 0


def test_restore_loop_skips_completed_if_row_present():
    """Defense in depth when last_state is Completed."""

    em = EventManager()
    program = MagicMock()
    program.services = MagicMock()
    program.services.post_processing = MagicMock()
    program.services.post_processing.initialized = False

    session = MagicMock()
    query_result = MagicMock()
    query_result.all.return_value = [(100, States.Completed, "movie")]
    session.execute.return_value = query_result

    with (
        patch(
            "program.managers.event_manager.db_session",
            return_value=MagicMock(
                __enter__=MagicMock(return_value=session), __exit__=MagicMock()
            ),
        ),
        patch.object(em, "_item_id_in_pipeline", return_value=False),
        patch(
            "program.managers.event_manager.db_functions.get_item_ids",
            return_value=(100, []),
        ),
    ):
        restored = em.restore_pipeline_from_db(program, source="startup")

    assert restored == []
