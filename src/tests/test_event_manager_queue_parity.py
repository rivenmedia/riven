from unittest.mock import MagicMock, patch

from program.managers.event_manager import EventManager
from program.media.state import States
from program.queue.models import PipelineStage
from program.types import Event


def test_add_event_to_queue_writes_pipeline_store():
    em = EventManager()
    item = MagicMock()
    item.last_state = States.Scraped
    item.is_parent_blocked.return_value = False
    session = MagicMock()
    session.query.return_value.filter_by.return_value.options.return_value.one_or_none.return_value = (
        item
    )

    with (
        patch(
            "program.managers.event_manager.db_session",
            return_value=MagicMock(
                __enter__=MagicMock(return_value=session), __exit__=MagicMock()
            ),
        ),
        patch.object(EventManager, "_maybe_stagger_scraped_run_at", return_value=None),
    ):
        em.add_event_to_queue(
            Event(emitted_by="StateTransition", item_id=42, item_state=States.Scraped)
        )

    assert em._queue.contains_item(42)
    assert len(em._queued_events) == 1
    assert em._queue.count_by_stage()[PipelineStage.download] == 1
