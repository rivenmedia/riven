"""Pipeline transitions for States.Unknown."""

from unittest.mock import Mock, patch

from program.media.state import States
from program.services.indexers import IndexerService
from program.state_transition import process_event


def test_process_event_unknown_routes_to_indexer():
    movie = Mock()
    movie.last_state = States.Unknown
    movie.log_string = "BEEF"

    services = Mock()
    services.indexer = Mock(spec=IndexerService)

    program = Mock()
    program.services = services

    with patch("program.state_transition.di") as mock_di:
        mock_di.__getitem__.return_value = program
        result = process_event("StateTransition", movie, None, None)

    assert result.service is services.indexer
    assert result.related_media_items == [movie]
