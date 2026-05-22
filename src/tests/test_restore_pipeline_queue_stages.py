from datetime import datetime
from unittest.mock import MagicMock, patch

from program.managers.event_manager import EventManager
from program.media.state import States
from program.queue.mapping import stage_for_state
from program.queue.models import PipelineStage


def test_restore_places_items_in_correct_stage_heaps():
    em = EventManager()
    program = MagicMock()
    program.services = MagicMock()
    program.services.updater.initialized = False
    program.services.filesystem.initialized = False
    program.services.downloader.initialized = False
    program.services.scraping.initialized = False
    program.services.indexer.initialized = False
    program.services.post_processing.initialized = False

    rows = [
        (1, States.Scraped, "movie"),
        (2, States.Symlinked, "movie"),
        (3, States.Indexed, "movie"),
    ]
    session = MagicMock()
    query_result = MagicMock()
    query_result.all.return_value = rows
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

    assert sorted(restored) == [1, 2, 3]
    counts = em._queue.count_by_stage()
    assert counts[PipelineStage.download] == 1
    assert counts[PipelineStage.update] == 1
    assert counts[PipelineStage.scrape] == 1
    assert counts.get(PipelineStage.post_process, 0) == 0
    assert stage_for_state(States.Scraped) == PipelineStage.download
