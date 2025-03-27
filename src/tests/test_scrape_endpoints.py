import io
import json
import hashlib
from unittest.mock import MagicMock, patch, AsyncMock

import pytest
from fastapi.testclient import TestClient
from fastapi import BackgroundTasks, FastAPI

from src.main import app
from src.program.media.item import MediaItem
from src.program.services.downloaders import Downloader
from src.program.services.indexers.trakt import TraktIndexer
from src.routers.secure.scrape import session_manager, _process_infohash, StartSessionResponse

# Ensure we're using a test client
client = TestClient(app)

# Mock the bencodepy library functions
@pytest.fixture
def mock_bencodepy():
    with patch("src.routers.secure.scrape.decode") as mock_decode, \
         patch("src.routers.secure.scrape.encode") as mock_encode:
        # Set up the mock to return a dictionary with an 'info' key when decode is called
        mock_decode.return_value = {b'info': b'fake_info_data'}
        # Set up the mock to return the original data when encode is called
        mock_encode.side_effect = lambda x: x
        # Create a mock for hashlib.sha1 that returns a fixed hash
        with patch("hashlib.sha1") as mock_sha1:
            mock_sha1_instance = MagicMock()
            mock_sha1_instance.hexdigest.return_value = "3648baf850d5930510c1f172b534200ebb5496e6"  # Use the same hash as in test_alldebrid_downloader
            mock_sha1.return_value = mock_sha1_instance
            yield

# Mock for testing invalid torrent decode scenario
@pytest.fixture
def mock_bencodepy_error():
    with patch("src.routers.secure.scrape.decode") as mock_decode:
        mock_decode.side_effect = Exception("Invalid torrent format")
        yield

# Mock the necessary services and background tasks
@pytest.fixture
def mock_services():
    # Mock the TraktIndexer
    mock_indexer = MagicMock(spec=TraktIndexer)
    mock_item = MagicMock(spec=MediaItem)
    mock_item.type = "movie"
    mock_indexer.run.return_value = [mock_item]
    
    # Mock the Downloader
    mock_downloader = MagicMock(spec=Downloader)
    mock_container = MagicMock()
    mock_container.cached = True
    mock_downloader.get_instant_availability.return_value = mock_container
    mock_downloader.add_torrent.return_value = "12345"
    mock_downloader.get_torrent_info.return_value = {
        "id": "12345",
        "name": "Test Movie",
        "size": 1000000000,
        "ready": True,
        "files": [{"id": "1", "name": "movie.mkv", "size": 1000000000}],
        "alternative_filename": "Test Movie"
    }
    
    # Mock BackgroundTasks
    mock_bg_tasks = MagicMock(spec=BackgroundTasks)
    
    # Clear any existing sessions
    session_manager.sessions = {}
    
    with patch("src.routers.secure.scrape._process_infohash", new_callable=AsyncMock) as mock_process:
        # Configure the mock to return a valid response
        mock_process.return_value = StartSessionResponse(
            message="Started manual scraping session from uploaded torrent file",
            session_id="fake-session-id",
            torrent_id="12345",
            torrent_info={
                "id": "12345",
                "name": "Test Movie",
                "size": 1000000000,
                "ready": True,
                "files": [{"id": "1", "name": "movie.mkv", "size": 1000000000}],
                "alternative_filename": "Test Movie"
            },
            containers=None,
            expires_at="2025-03-27T20:00:00.000000"
        )
        yield mock_indexer, mock_downloader, mock_bg_tasks, mock_process

def test_upload_torrent_endpoint(mock_bencodepy, mock_services):
    """Test the /scrape/upload_torrent endpoint for .torrent file uploads"""
    mock_indexer, mock_downloader, mock_bg_tasks, mock_process = mock_services
    
    # Create a fake torrent file
    fake_torrent_content = b'some binary torrent data'
    fake_torrent_file = io.BytesIO(fake_torrent_content)
    
    # Mock app.program.services to return our mocked services
    with patch.object(app, "program") as mock_program:
        mock_program.services = {
            TraktIndexer: mock_indexer,
            Downloader: mock_downloader
        }
        
        # Make the request to upload the torrent
        response = client.post(
            "/scrape/upload_torrent",
            params={"item_id": "tt1234567"},  # Using an IMDb ID format
            files={"torrent_file": ("test.torrent", fake_torrent_file, "application/x-bittorrent")}
        )
        
        # Assert the response
        assert response.status_code == 200
        response_data = response.json()
        assert response_data["message"] == "Started manual scraping session from uploaded torrent file"
        assert "session_id" in response_data
        assert response_data["torrent_id"] == "12345"
        
        # Verify the _process_infohash function was called with the correct arguments
        mock_process.assert_called_once()
        _, kwargs = mock_process.call_args
        assert kwargs["item_id"] == "tt1234567"
        assert kwargs["info_hash"] == "3648baf850d5930510c1f172b534200ebb5496e6"
        assert kwargs["source_description"] == "uploaded torrent file"

def test_upload_torrent_invalid_file(mock_services):
    """Test the /scrape/upload_torrent endpoint with an invalid file"""
    mock_indexer, mock_downloader, mock_bg_tasks, mock_process = mock_services
    
    # Create a non-torrent file
    fake_file = io.BytesIO(b'not a torrent file')
    
    # Mock app.program.services to return our mocked services
    with patch.object(app, "program") as mock_program:
        mock_program.services = {
            TraktIndexer: mock_indexer,
            Downloader: mock_downloader
        }
        
        # Make the request with a non-torrent file
        response = client.post(
            "/scrape/upload_torrent",
            params={"item_id": "tt1234567"},
            files={"torrent_file": ("test.txt", fake_file, "text/plain")}
        )
        
        # Assert the response indicates an error
        assert response.status_code == 400
        assert "File must be a .torrent file" in response.json()["detail"]
        
        # Verify that _process_infohash was not called
        mock_process.assert_not_called()

def test_upload_torrent_invalid_format(mock_bencodepy_error, mock_services):
    """Test the /scrape/upload_torrent endpoint with a file that cannot be decoded"""
    mock_indexer, mock_downloader, mock_bg_tasks, mock_process = mock_services
    
    # Create a torrent file with invalid format
    fake_file = io.BytesIO(b'invalid torrent binary data')
    
    # Mock app.program.services to return our mocked services
    with patch.object(app, "program") as mock_program:
        mock_program.services = {
            TraktIndexer: mock_indexer,
            Downloader: mock_downloader
        }
        
        # Make the request with an invalid torrent file
        response = client.post(
            "/scrape/upload_torrent",
            params={"item_id": "tt1234567"},
            files={"torrent_file": ("test.torrent", fake_file, "application/x-bittorrent")}
        )
        
        # Assert the response indicates an error
        assert response.status_code == 400
        assert "Invalid torrent file format" in response.json()["detail"]
        
        # Verify that _process_infohash was not called
        mock_process.assert_not_called()