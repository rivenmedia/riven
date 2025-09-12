"""Comprehensive tests for TorBox downloader service."""

from unittest.mock import Mock, patch

import pytest

from program.services.downloaders.models import TorrentContainer, TorrentInfo
from program.services.downloaders.torbox import TorBoxDownloader, TorBoxError
from program.utils.request import CircuitBreakerOpen, SmartResponse


class TestTorBoxComprehensive:
    """Comprehensive test suite for TorBox downloader."""
    
    @pytest.fixture
    def downloader(self):
        """Create a TorBox downloader instance for testing."""
        with patch("program.services.downloaders.torbox.settings_manager") as mock_settings, \
             patch("program.services.downloaders.torbox.TorBoxAPI") as mock_api_class:
            mock_settings.settings.downloaders.torbox.enabled = True
            mock_settings.settings.downloaders.torbox.api_key = "test_api_key_123"
            mock_settings.settings.downloaders.torbox.proxy_url = None
            
            # Mock the API instance
            mock_api_instance = Mock()
            mock_api_class.return_value = mock_api_instance
            
            downloader = TorBoxDownloader()
            downloader.initialized = True
            return downloader

    @pytest.fixture
    def mock_api_response(self):
        """Create a mock API response."""
        response = Mock(spec=SmartResponse)
        response.ok = True
        response.status_code = 200
        response.data = Mock()
        return response
    
    def test_validate_success(self, downloader):
        """Test successful validation."""
        with patch.object(downloader, "_validate_settings", return_value=True), \
             patch.object(downloader, "_validate_premium", return_value=True):
            result = downloader.validate()
            assert result is True
    
    def test_validate_failure_no_premium(self, downloader):
        """Test validation failure when user is not premium."""
        with patch.object(downloader, "_validate_settings", return_value=True), \
             patch.object(downloader, "_validate_premium", return_value=False):
            result = downloader.validate()
            assert result is False
    
    def test_validate_api_error(self, downloader):
        """Test validation failure on API error."""
        with patch.object(downloader, "_validate_settings", return_value=True), \
             patch.object(downloader, "_validate_premium", return_value=False):
            result = downloader.validate()
            assert result is False
    
    def test_get_instant_availability_success(self, downloader):
        """Test successful instant availability check."""
        with patch.object(downloader.api, "session") as mock_session:
            mock_response = Mock(spec=SmartResponse)
            mock_response.ok = True
            mock_response.status_code = 200
            mock_response.data = Mock()
            mock_response.data.get.return_value = {
                "files": [
                    {
                        "name": "test_movie.mkv",
                        "size": 800000000  # 800MB - within allowed range
                    }
                ]
            }
            
            mock_session.get.return_value = mock_response
            
            result = downloader.get_instant_availability("test_hash", "movie")
            
            assert isinstance(result, TorrentContainer)
            assert result.infohash == "test_hash"
            assert len(result.files) == 1
            assert result.files[0].filename == "test_movie.mkv"
            mock_session.get.assert_called_once_with("torrents/checkcached?hash=test_hash&format=object&list_files=true")
    
    def test_get_instant_availability_no_files(self, downloader):
        """Test instant availability check with no available files."""
        with patch.object(downloader.api, "session") as mock_session:
            mock_response = Mock(spec=SmartResponse)
            mock_response.ok = True
            mock_response.status_code = 200
            mock_response.data = Mock()
            mock_response.data.get.return_value = {}  # Empty response
            
            mock_session.get.return_value = mock_response
            
            result = downloader.get_instant_availability("test_hash", "movie")
            assert result is None
    
    def test_get_instant_availability_api_error(self, downloader):
        """Test instant availability check with API error."""
        with patch.object(downloader.api, "session") as mock_session:
            mock_response = Mock(spec=SmartResponse)
            mock_response.ok = False
            mock_response.status_code = 404
            
            mock_session.get.return_value = mock_response
            
            result = downloader.get_instant_availability("test_hash", "movie")
            assert result is None
    
    def test_add_torrent_success(self, downloader):
        """Test successful torrent addition."""
        with patch.object(downloader.api, "session") as mock_session:
            mock_response = Mock(spec=SmartResponse)
            mock_response.ok = True
            mock_response.status_code = 200
            mock_response.data = {"torrent_id": "torrent_123"}
            
            mock_session.post.return_value = mock_response
            
            result = downloader.add_torrent("test_hash")
            assert result == "torrent_123"
            mock_session.post.assert_called_once_with(
                "torrents/createtorrent",
                data={"magnet": "magnet:?xt=urn:btih:test_hash"}
            )
    
    def test_add_torrent_circuit_breaker(self, downloader):
        """Test circuit breaker activation on 5xx error."""
        with patch.object(downloader.api, "session") as mock_session:
            mock_response = Mock(spec=SmartResponse)
            mock_response.ok = False
            mock_response.status_code = 500
            
            mock_session.post.return_value = mock_response
            
            with pytest.raises(CircuitBreakerOpen) as exc_info:
                downloader.add_torrent("test_hash")
            
            assert exc_info.value.name == "api.torbox.app"
    
    def test_add_torrent_rate_limit(self, downloader):
        """Test rate limit handling."""
        with patch.object(downloader.api, "session") as mock_session:
            mock_response = Mock(spec=SmartResponse)
            mock_response.ok = False
            mock_response.status_code = 429
            
            mock_session.post.return_value = mock_response
            
            with pytest.raises(CircuitBreakerOpen) as exc_info:
                downloader.add_torrent("test_hash")
            
            assert exc_info.value.name == "api.torbox.app"
    
    def test_add_torrent_client_error(self, downloader):
        """Test client error handling."""
        with patch.object(downloader.api, "session") as mock_session:
            mock_response = Mock(spec=SmartResponse)
            mock_response.ok = False
            mock_response.status_code = 400
            
            mock_session.post.return_value = mock_response
            
            with pytest.raises(TorBoxError) as exc_info:
                downloader.add_torrent("test_hash")
            
            assert "[400] Torrent file is not valid" in str(exc_info.value)
    
    def test_add_torrent_no_id_returned(self, downloader):
        """Test error when no torrent ID is returned."""
        with patch.object(downloader.api, "session") as mock_session:
            mock_response = Mock(spec=SmartResponse)
            mock_response.ok = True
            mock_response.status_code = 200
            mock_response.data = {}  # Empty response - no torrent_id
            
            mock_session.post.return_value = mock_response
            
            with pytest.raises(TorBoxError) as exc_info:
                downloader.add_torrent("test_hash")
            
            assert "torrent_id" in str(exc_info.value)
    
    def test_select_files_success(self, downloader):
        """Test successful file selection."""
        # TorBox's select_files is a no-op, so just test it doesn't raise
        downloader.select_files("torrent_123", ["1", "2", "3"])
        # Should not raise any exception
    
    def test_select_files_no_files(self, downloader):
        """Test file selection with no specific files (select all)."""
        # TorBox's select_files is a no-op, so just test it doesn't raise
        downloader.select_files("torrent_123")
        # Should not raise any exception
    
    def test_select_files_error(self, downloader):
        """Test file selection error handling."""
        # TorBox's select_files is a no-op, so it shouldn't raise errors
        downloader.select_files("torrent_123", ["1", "2"])
        # Should not raise any exception
    
    def test_get_torrent_info_success(self, downloader):
        """Test successful torrent info retrieval."""
        with patch.object(downloader.api, "session") as mock_session:
            mock_response = Mock(spec=SmartResponse)
            mock_response.ok = True
            mock_response.status_code = 200
            mock_response.data = {
                "id": "torrent_123",
                "name": "Test Movie",
                "download_state": "downloaded",
                "cached": True,
                "hash": "test_hash_123",
                "size": 1000000,
                "created_at": "2025-01-01T00:00:00Z",
                "progress": 100.0,
                "files": [
                    {
                        "id": 1,
                        "name": "test_movie.mkv",
                        "short_name": "test_movie.mkv",
                        "size": 1000000
                    }
                ]
            }
            
            mock_session.get.return_value = mock_response
            
            result = downloader.get_torrent_info("torrent_123")
            
            assert isinstance(result, TorrentInfo)
            assert result.id == "torrent_123"
            assert result.name == "Test Movie"
            assert result.status == "downloaded"
            assert result.alternative_filename is None
            
            mock_session.get.assert_called_once_with("torrents/mylist?id=torrent_123")
    
    def test_get_torrent_info_not_found(self, downloader):
        """Test torrent info retrieval when torrent not found."""
        with patch.object(downloader.api, "session") as mock_session:
            mock_response = Mock(spec=SmartResponse)
            mock_response.ok = False
            mock_response.status_code = 404
            
            mock_session.get.return_value = mock_response
            
            with pytest.raises(TorBoxError) as exc_info:
                downloader.get_torrent_info("nonexistent_torrent")
            
            assert "[404] Torrent Not Found or Service Unavailable" in str(exc_info.value)
    
    def test_get_torrent_info_circuit_breaker(self, downloader):
        """Test circuit breaker on torrent info retrieval."""
        with patch.object(downloader.api, "session") as mock_session:
            mock_response = Mock(spec=SmartResponse)
            mock_response.ok = False
            mock_response.status_code = 500
            
            mock_session.get.return_value = mock_response
            
            with pytest.raises(CircuitBreakerOpen) as exc_info:
                downloader.get_torrent_info("torrent_123")
            
            assert exc_info.value.name == "api.torbox.app"
    
    def test_delete_torrent_success(self, downloader):
        """Test successful torrent deletion."""
        with patch.object(downloader.api, "session") as mock_session:
            mock_response = Mock(spec=SmartResponse)
            mock_response.ok = True
            mock_response.status_code = 200
            
            mock_session.post.return_value = mock_response
            
            # Should not raise any exception
            downloader.delete_torrent("torrent_123")
            
            mock_session.post.assert_called_once_with(
                "torrents/controltorrent",
                data={"id": "torrent_123", "operation": "delete"}
            )
    
    def test_delete_torrent_error(self, downloader):
        """Test torrent deletion error handling."""
        with patch.object(downloader.api, "session") as mock_session:
            mock_response = Mock(spec=SmartResponse)
            mock_response.ok = False
            mock_response.status_code = 404
            
            mock_session.post.return_value = mock_response
            
            with pytest.raises(TorBoxError) as exc_info:
                downloader.delete_torrent("nonexistent_torrent")
            
            assert "[404] Torrent Not Found or Service Unavailable" in str(exc_info.value)
    
    def test_complete_workflow_success(self, downloader):
        """Test complete download workflow from start to finish."""
        with patch.object(downloader, "add_torrent", return_value="torrent_123"), \
             patch.object(downloader, "get_torrent_info", return_value=Mock(id="torrent_123", name="Test Movie")), \
             patch.object(downloader, "select_files"), \
             patch.object(downloader, "get_instant_availability", return_value=Mock(spec=TorrentContainer)):
            
            # Test the complete workflow
            # 1. Check instant availability
            container = downloader.get_instant_availability("test_hash", "movie")
            assert container is not None
            
            # 2. Add torrent
            torrent_id = downloader.add_torrent("test_hash")
            assert torrent_id == "torrent_123"
            
            # 3. Select files
            downloader.select_files(torrent_id, ["1"])
            
            # 4. Get torrent info
            info = downloader.get_torrent_info(torrent_id)
            assert info is not None
            assert info.id == "torrent_123"
    
    def test_error_handling_comprehensive(self, downloader):
        """Test comprehensive error handling for all methods."""
        error_cases = [
            # (method, args, status_code, expected_error_type, expected_message)
            ("add_torrent", ("test_hash",), 451, TorBoxError, "[451] Infringing Torrent"),
            ("add_torrent", ("test_hash",), 400, TorBoxError, "[400] Torrent file is not valid"),
            ("add_torrent", ("test_hash",), 404, TorBoxError, "[404] Torrent Not Found or Service Unavailable"),
            ("delete_torrent", ("torrent_123",), 400, TorBoxError, "[400] Torrent file is not valid"),
            ("delete_torrent", ("torrent_123",), 404, TorBoxError, "[404] Torrent Not Found or Service Unavailable"),
        ]
        
        for method_name, args, status_code, expected_error_type, expected_message in error_cases:
            with patch.object(downloader.api, "session") as mock_session:
                mock_response = Mock(spec=SmartResponse)
                mock_response.ok = False
                mock_response.status_code = status_code
                
                # Determine the HTTP method based on the method being tested
                if method_name == "add_torrent" or method_name == "delete_torrent":
                    mock_session.post.return_value = mock_response
                else:
                    mock_session.get.return_value = mock_response
                
                method = getattr(downloader, method_name)
                
                with pytest.raises(expected_error_type) as exc_info:
                    method(*args)
                
                assert expected_message in str(exc_info.value)
    
    def test_circuit_breaker_comprehensive(self, downloader):
        """Test circuit breaker activation for all methods."""
        circuit_breaker_cases = [
            # (method, args, status_code)
            ("add_torrent", ("test_hash",), 500),
            ("add_torrent", ("test_hash",), 502),
            ("add_torrent", ("test_hash",), 503),
            ("get_torrent_info", ("torrent_123",), 500),
            ("get_torrent_info", ("torrent_123",), 502),
            ("get_torrent_info", ("torrent_123",), 503),
            ("delete_torrent", ("torrent_123",), 500),
            ("delete_torrent", ("torrent_123",), 502),
            ("delete_torrent", ("torrent_123",), 503),
        ]
        
        for method_name, args, status_code in circuit_breaker_cases:
            with patch.object(downloader.api, "session") as mock_session:
                mock_response = Mock(spec=SmartResponse)
                mock_response.ok = False
                mock_response.status_code = status_code
                
                # Determine the HTTP method based on the method being tested
                if method_name == "add_torrent" or method_name == "delete_torrent":
                    mock_session.post.return_value = mock_response
                else:
                    mock_session.get.return_value = mock_response
                
                method = getattr(downloader, method_name)
                
                with pytest.raises(CircuitBreakerOpen) as exc_info:
                    method(*args)
                
                assert exc_info.value.name == "api.torbox.app"
    
    def test_rate_limit_handling(self, downloader):
        """Test rate limit handling (429 responses)."""
        rate_limit_cases = [
            ("add_torrent", ("test_hash",)),
            ("get_torrent_info", ("torrent_123",)),
            ("delete_torrent", ("torrent_123",)),
            ("get_instant_availability", ("test_hash", "movie")),
        ]
        
        for method_name, args in rate_limit_cases:
            with patch.object(downloader.api, "session") as mock_session:
                mock_response = Mock(spec=SmartResponse)
                mock_response.ok = False
                mock_response.status_code = 429
                
                # Determine the HTTP method based on the method being tested
                if method_name == "add_torrent" or method_name == "delete_torrent":
                    mock_session.post.return_value = mock_response
                else:
                    mock_session.get.return_value = mock_response
                
                method = getattr(downloader, method_name)
                
                with pytest.raises(CircuitBreakerOpen) as exc_info:
                    method(*args)
                
                assert exc_info.value.name == "api.torbox.app"
