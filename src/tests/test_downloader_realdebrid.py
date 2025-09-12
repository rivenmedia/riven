"""Comprehensive tests for RealDebrid downloader service."""

from unittest.mock import Mock, patch

import pytest

from program.services.downloaders.models import TorrentContainer, TorrentInfo
from program.services.downloaders.realdebrid import (
    RealDebridDownloader,
    RealDebridError,
)
from program.utils.request import CircuitBreakerOpen, SmartResponse


class TestRealDebridComprehensive:
    """Comprehensive test suite for RealDebrid downloader."""
    
    @pytest.fixture
    def downloader(self):
        """Create a RealDebrid downloader instance for testing."""
        with patch("program.services.downloaders.realdebrid.settings_manager") as mock_settings:
            mock_settings.settings.downloaders.real_debrid.enabled = True
            mock_settings.settings.downloaders.real_debrid.api_key = "test_api_key_123"
            mock_settings.settings.downloaders.real_debrid.proxy_url = None
            downloader = RealDebridDownloader()
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
        with patch.object(downloader.api, "session") as mock_session:
            mock_response = Mock(spec=SmartResponse)
            mock_response.ok = True
            mock_response.status_code = 200
            mock_response.data = Mock()
            mock_response.data.username = "test_user"
            mock_response.data.premium = 0
            mock_response.data.expiration = "2025-12-31"
            
            mock_session.get.return_value = mock_response
            
            result = downloader.validate()
            assert result is False
    
    def test_validate_api_error(self, downloader):
        """Test validation failure on API error."""
        with patch.object(downloader.api, "session") as mock_session:
            mock_response = Mock(spec=SmartResponse)
            mock_response.ok = False
            mock_response.status_code = 401
            
            mock_session.get.return_value = mock_response
            
            result = downloader.validate()
            assert result is False
    
    def test_get_instant_availability_success(self, downloader):
        """Test successful instant availability check."""
        with patch.object(downloader, "add_torrent", return_value="torrent_123"), \
             patch.object(downloader, "_process_torrent", return_value=(Mock(spec=TorrentContainer), None)), \
             patch.object(downloader, "delete_torrent"):
            
            result = downloader.get_instant_availability("test_hash", "movie")
            
            assert isinstance(result, TorrentContainer)
            downloader.add_torrent.assert_called_once_with("test_hash")
            downloader.delete_torrent.assert_called_once_with("torrent_123")
    
    def test_get_instant_availability_no_files(self, downloader):
        """Test instant availability check with no available files."""
        with patch.object(downloader.api, "session") as mock_session:
            mock_response = Mock(spec=SmartResponse)
            mock_response.ok = True
            mock_response.status_code = 200
            mock_response.data = []
            
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
            mock_response.status_code = 201
            mock_response.data = Mock()
            mock_response.data.id = "torrent_123"
            
            mock_session.post.return_value = mock_response
            
            result = downloader.add_torrent("test_hash")
            assert result == "torrent_123"
            mock_session.post.assert_called_once_with(
                "torrents/addMagnet", 
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
            
            assert exc_info.value.name == "api.real-debrid.com"
    
    def test_add_torrent_rate_limit(self, downloader):
        """Test rate limit handling."""
        with patch.object(downloader.api, "session") as mock_session:
            mock_response = Mock(spec=SmartResponse)
            mock_response.ok = False
            mock_response.status_code = 429
            
            mock_session.post.return_value = mock_response
            
            with pytest.raises(CircuitBreakerOpen) as exc_info:
                downloader.add_torrent("test_hash")
            
            assert exc_info.value.name == "api.real-debrid.com"
    
    def test_add_torrent_client_error(self, downloader):
        """Test client error handling."""
        with patch.object(downloader.api, "session") as mock_session:
            mock_response = Mock(spec=SmartResponse)
            mock_response.ok = False
            mock_response.status_code = 400
            
            mock_session.post.return_value = mock_response
            
            with pytest.raises(RealDebridError) as exc_info:
                downloader.add_torrent("test_hash")
            
            assert "[400] Torrent file is not valid" in str(exc_info.value)
    
    def test_add_torrent_no_id_returned(self, downloader):
        """Test error when no torrent ID is returned."""
        with patch.object(downloader.api, "session") as mock_session:
            mock_response = Mock(spec=SmartResponse)
            mock_response.ok = True
            mock_response.status_code = 201
            mock_response.data = Mock()
            mock_response.data.id = None
            
            mock_session.post.return_value = mock_response
            
            with pytest.raises(RealDebridError) as exc_info:
                downloader.add_torrent("test_hash")
            
            assert "No torrent ID returned" in str(exc_info.value)
    
    def test_select_files_success(self, downloader):
        """Test successful file selection."""
        with patch.object(downloader.api, "session") as mock_session:
            mock_response = Mock(spec=SmartResponse)
            mock_response.ok = True
            mock_response.status_code = 200
            
            mock_session.post.return_value = mock_response
            
            # Should not raise any exception
            downloader.select_files("torrent_123", [1, 2, 3])
            
            mock_session.post.assert_called_once_with(
                "torrents/selectFiles/torrent_123",
                data={"files": "1,2,3"}
            )
    
    def test_select_files_no_files(self, downloader):
        """Test file selection with no specific files (select all)."""
        with patch.object(downloader.api, "session") as mock_session:
            mock_response = Mock(spec=SmartResponse)
            mock_response.ok = True
            mock_response.status_code = 200
            
            mock_session.post.return_value = mock_response
            
            downloader.select_files("torrent_123")
            
            mock_session.post.assert_called_once_with(
                "torrents/selectFiles/torrent_123",
                data={"files": "all"}
            )
    
    def test_select_files_error(self, downloader):
        """Test file selection error handling."""
        with patch.object(downloader.api, "session") as mock_session:
            mock_response = Mock(spec=SmartResponse)
            mock_response.ok = False
            mock_response.status_code = 404
            
            mock_session.post.return_value = mock_response
            
            with pytest.raises(RealDebridError) as exc_info:
                downloader.select_files("torrent_123", [1, 2])
            
            assert "[404] Torrent Not Found or Service Unavailable" in str(exc_info.value)
    
    def test_get_torrent_info_success(self, downloader):
        """Test successful torrent info retrieval."""
        with patch.object(downloader.api, "session") as mock_session:
            mock_response = Mock(spec=SmartResponse)
            mock_response.ok = True
            mock_response.status_code = 200
            mock_response.data = Mock()
            mock_response.data.id = "torrent_123"
            mock_response.data.filename = "Test Movie"
            mock_response.data.status = "downloaded"
            mock_response.data.files = []
            mock_response.data.hash = "test_hash_123"
            mock_response.data.bytes = 1000000
            mock_response.data.added = "2025-01-01T00:00:00Z"
            mock_response.data.progress = 100.0
            mock_response.data.original_filename = "Original Movie Name"
            # Ensure no error attribute
            del mock_response.data.error
            
            mock_session.get.return_value = mock_response
            
            result = downloader.get_torrent_info("torrent_123")
            
            assert isinstance(result, TorrentInfo)
            assert result.id == "torrent_123"
            assert result.name == "Test Movie"
            assert result.alternative_filename == "Original Movie Name"
            
            mock_session.get.assert_called_once_with("torrents/info/torrent_123")
    
    def test_get_torrent_info_not_found(self, downloader):
        """Test torrent info retrieval when torrent not found."""
        with patch.object(downloader.api, "session") as mock_session:
            mock_response = Mock(spec=SmartResponse)
            mock_response.ok = False
            mock_response.status_code = 404
            
            mock_session.get.return_value = mock_response
            
            result = downloader.get_torrent_info("nonexistent_torrent")
            assert result is None
    
    def test_get_torrent_info_circuit_breaker(self, downloader):
        """Test circuit breaker on torrent info retrieval."""
        with patch.object(downloader.api, "session") as mock_session:
            mock_response = Mock(spec=SmartResponse)
            mock_response.ok = False
            mock_response.status_code = 500
            
            mock_session.get.return_value = mock_response
            
            with pytest.raises(CircuitBreakerOpen) as exc_info:
                downloader.get_torrent_info("torrent_123")
            
            assert exc_info.value.name == "api.real-debrid.com"
    
    def test_delete_torrent_success(self, downloader):
        """Test successful torrent deletion."""
        with patch.object(downloader.api, "session") as mock_session:
            mock_response = Mock(spec=SmartResponse)
            mock_response.ok = True
            mock_response.status_code = 204
            
            mock_session.delete.return_value = mock_response
            
            # Should not raise any exception
            downloader.delete_torrent("torrent_123")
            
            mock_session.delete.assert_called_once_with("torrents/delete/torrent_123")
    
    def test_delete_torrent_error(self, downloader):
        """Test torrent deletion error handling."""
        with patch.object(downloader.api, "session") as mock_session:
            mock_response = Mock(spec=SmartResponse)
            mock_response.ok = False
            mock_response.status_code = 404
            
            mock_session.delete.return_value = mock_response
            
            with pytest.raises(RealDebridError) as exc_info:
                downloader.delete_torrent("nonexistent_torrent")
            
            assert "[404] Torrent Not Found or Service Unavailable" in str(exc_info.value)

    def test_complete_workflow_success(self, downloader):
        """Test complete download workflow from start to finish."""
        with patch.object(downloader, "add_torrent", return_value="torrent_123"), \
             patch.object(downloader, "_process_torrent", return_value=(Mock(spec=TorrentContainer), None)), \
             patch.object(downloader, "delete_torrent"), \
             patch.object(downloader, "get_torrent_info", return_value=Mock(spec=TorrentInfo)), \
             patch.object(downloader, "select_files"):

            # Test the complete workflow
            # 1. Check instant availability
            container = downloader.get_instant_availability("test_hash", "movie")
            assert container is not None
            
            # 2. Add torrent
            torrent_id = downloader.add_torrent("test_hash")
            assert torrent_id == "torrent_123"
            
            # 3. Select files
            downloader.select_files(torrent_id, [1])
            
            # 4. Get torrent info
            info = downloader.get_torrent_info(torrent_id)
            assert info is not None
    
    def test_error_handling_comprehensive(self, downloader):
        """Test comprehensive error handling for all methods."""
        error_cases = [
            # (method, args, status_code, expected_error_type, expected_message)
            ("add_torrent", ("test_hash",), 451, RealDebridError, "[451] Infringing Torrent"),
            ("add_torrent", ("test_hash",), 400, RealDebridError, "[400] Torrent file is not valid"),
            ("add_torrent", ("test_hash",), 404, RealDebridError, "[404] Torrent Not Found or Service Unavailable"),
            ("select_files", ("torrent_123", [1]), 400, RealDebridError, "[400] Torrent file is not valid"),
            ("select_files", ("torrent_123", [1]), 404, RealDebridError, "[404] Torrent Not Found or Service Unavailable"),
            ("delete_torrent", ("torrent_123",), 400, RealDebridError, "[400] Torrent file is not valid"),
            ("delete_torrent", ("torrent_123",), 404, RealDebridError, "[404] Torrent Not Found or Service Unavailable"),
        ]
        
        for method_name, args, status_code, expected_error_type, expected_message in error_cases:
            with patch.object(downloader.api, "session") as mock_session:
                mock_response = Mock(spec=SmartResponse)
                mock_response.ok = False
                mock_response.status_code = status_code
                
                # Determine the HTTP method based on the method being tested
                if method_name == "add_torrent" or method_name == "select_files":
                    mock_session.post.return_value = mock_response
                elif method_name == "delete_torrent":
                    mock_session.delete.return_value = mock_response
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
                if method_name == "add_torrent":
                    mock_session.post.return_value = mock_response
                elif method_name == "delete_torrent":
                    mock_session.delete.return_value = mock_response
                else:
                    mock_session.get.return_value = mock_response
                
                method = getattr(downloader, method_name)
                
                with pytest.raises(CircuitBreakerOpen) as exc_info:
                    method(*args)
                
                assert exc_info.value.name == "api.real-debrid.com"
    
    def test_rate_limit_handling(self, downloader):
        """Test rate limit handling (429 responses)."""
        rate_limit_cases = [
            ("add_torrent", ("test_hash",)),
            ("get_torrent_info", ("torrent_123",)),
            ("delete_torrent", ("torrent_123",)),
        ]
        
        for method_name, args in rate_limit_cases:
            with patch.object(downloader.api, "session") as mock_session:
                mock_response = Mock(spec=SmartResponse)
                mock_response.ok = False
                mock_response.status_code = 429
                
                # Determine the HTTP method based on the method being tested
                if method_name == "add_torrent":
                    mock_session.post.return_value = mock_response
                elif method_name == "delete_torrent":
                    mock_session.delete.return_value = mock_response
                else:
                    mock_session.get.return_value = mock_response
                
                method = getattr(downloader, method_name)
                
                with pytest.raises(CircuitBreakerOpen) as exc_info:
                    method(*args)
                
                assert exc_info.value.name == "api.real-debrid.com"
        
        # Test get_instant_availability separately since it catches and re-raises CircuitBreakerOpen
        with patch.object(downloader.api, "session") as mock_session:
            mock_response = Mock(spec=SmartResponse)
            mock_response.ok = False
            mock_response.status_code = 429
            
            mock_session.post.return_value = mock_response
            
            with pytest.raises(CircuitBreakerOpen) as exc_info:
                downloader.get_instant_availability("test_hash", "movie")
            
            assert exc_info.value.name == "api.real-debrid.com"
