import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, MagicMock, patch

from program.managers.event_manager import EventManager
from program.types import Event
from program.symlink import Symlinker


def test_db_functions_uses_add_event_for_delayed_execution():
    """Test that db_functions.run_thread_with_db_item uses add_event instead of add_event_to_queue for delayed execution."""
    from program.db.db_functions import run_thread_with_db_item

    # Create a mock program with event manager
    mock_program = Mock()
    mock_em = Mock()
    mock_program.em = mock_em

    # Create a mock service that returns delayed execution
    def mock_service_with_delay(item):
        next_attempt = datetime.now() + timedelta(seconds=8)
        yield (item, next_attempt)

    # Create a mock item
    mock_item = Mock()
    mock_item.id = "movie_123"
    mock_item.log_string = "Test Movie"

    # Create an event
    event = Event(Symlinker, item_id="movie_123")

    # Mock cancellation event
    cancellation_event = Mock()
    cancellation_event.is_set.return_value = False

    # Mock database session and item retrieval
    with patch('program.db.db_functions.get_item_by_id', return_value=mock_item), \
         patch('program.db.db_functions.db.Session'):

        # Run the function
        result = run_thread_with_db_item(
            mock_service_with_delay,
            Symlinker,
            mock_program,
            event,
            cancellation_event
        )

        # Verify that add_event was called (not add_event_to_queue)
        mock_em.add_event.assert_called_once()
        mock_em.add_event_to_queue.assert_not_called()

        # Verify the delayed event was created correctly
        call_args = mock_em.add_event.call_args[0][0]  # Get the event argument
        assert call_args.item_id == "movie_123"
        assert call_args.emitted_by == Symlinker
        assert call_args.run_at > datetime.now()


def test_symlinker_delayed_execution_scenario():
    """Test the specific scenario from the bug report - symlinker returning delayed execution."""
    from program.db.db_functions import run_thread_with_db_item

    # Create a mock program with event manager
    mock_program = Mock()
    mock_em = Mock()
    mock_program.em = mock_em

    # Create a mock symlinker service that returns delayed execution (like when file isn't available)
    def mock_symlinker_waiting_for_file(item):
        # This simulates the symlinker waiting for a file to become available
        # It returns a tuple with the item and a future timestamp
        next_attempt = datetime.now() + timedelta(seconds=8)
        yield (item, next_attempt)

    # Create a mock item
    mock_item = Mock()
    mock_item.id = "movie_813190"  # Same ID from the bug report
    mock_item.log_string = "Karate Kid: Legends"

    # Create an event
    event = Event(Symlinker, item_id="movie_813190")

    # Mock cancellation event
    cancellation_event = Mock()
    cancellation_event.is_set.return_value = False

    # Mock database session and item retrieval
    with patch('program.db.db_functions.get_item_by_id', return_value=mock_item), \
         patch('program.db.db_functions.db.Session'):

        # Run the function - this should create a delayed event
        result = run_thread_with_db_item(
            mock_symlinker_waiting_for_file,
            Symlinker,
            mock_program,
            event,
            cancellation_event
        )

        # Verify that add_event was called (not add_event_to_queue)
        # This is the key fix - using add_event enables duplicate prevention
        mock_em.add_event.assert_called_once()
        mock_em.add_event_to_queue.assert_not_called()

        # Verify the delayed event was created correctly
        call_args = mock_em.add_event.call_args[0][0]  # Get the event argument
        assert call_args.item_id == "movie_813190"
        assert call_args.emitted_by == Symlinker
        assert call_args.run_at > datetime.now()

        # Verify the current event was removed from running
        mock_em.remove_event_from_running.assert_called_once_with(event)


def test_event_manager_duplicate_detection():
    """Test that EventManager can detect duplicates in queue and running events."""
    em = EventManager()

    # Create test events
    event1 = Event(Symlinker, item_id="movie_123")
    event2 = Event(Symlinker, item_id="movie_456")

    # Manually add event to queue (bypassing validation)
    em._queued_events.append((datetime.now(), 1, event1))

    # Test _id_in_queue method
    assert em._id_in_queue("movie_123") is True
    assert em._id_in_queue("movie_456") is False

    # Manually add event to running events
    em._running_events.append(event2)

    # Test _id_in_running_events method
    assert em._id_in_running_events("movie_456") is True
    assert em._id_in_running_events("movie_123") is False
