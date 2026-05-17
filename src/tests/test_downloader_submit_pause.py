from datetime import datetime, timedelta
from unittest.mock import Mock, patch

from program.managers.event_manager import EventManager
from program.services.downloaders import Downloader
from program.types import Event


def test_submit_job_requeues_when_downloader_paused():
    em = EventManager()
    downloader = Downloader()
    downloader.initialized = True
    downloader.initialized_services = [Mock(key="torbox")]
    pause = datetime.now() + timedelta(minutes=1)
    downloader._service_cooldowns = {"torbox": pause}

    program = Mock()
    program.services = Mock()
    program.services.downloader = downloader
    program.services.__getitem__ = lambda _self, key: downloader

    event = Event("Scraping", item_id=42)
    event.run_at = datetime.now()

    with patch.object(em, "_find_or_create_executor") as mock_executor:
        with patch.object(em, "add_event_to_queue") as mock_enqueue:
            em.submit_job(downloader, program, event)

    mock_executor.assert_not_called()
    mock_enqueue.assert_called_once()
    queued = mock_enqueue.call_args[0][0]
    assert queued.run_at >= pause
    assert queued.item_id == 42
