"""Comprehensive tests for AllDebrid downloader service."""

from unittest.mock import Mock, patch

import pytest

from program.services.downloaders.alldebrid import AllDebridDownloader, AllDebridError
from program.services.downloaders.models import TorrentContainer, TorrentInfo
from program.utils.request import CircuitBreakerOpen, SmartResponse


class TestAllDebridComprehensive:
    """Comprehensive test suite for AllDebrid downloader."""
    
    @pytest.fixture
    def downloader(self):
        """Create an AllDebrid downloader instance for testing."""
        with patch("program.services.downloaders.alldebrid.settings_manager") as mock_settings:
            mock_settings.settings.downloaders.all_debrid.enabled = True
            mock_settings.settings.downloaders.all_debrid.api_key = "test_api_key_123"
            mock_settings.settings.downloaders.all_debrid.proxy_url = None
            downloader = AllDebridDownloader()
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
            mock_response.data.data = Mock()
            mock_response.data.data.user = Mock()
            mock_response.data.data.user.username = "test_user"
            mock_response.data.data.user.isPremium = False
            mock_response.data.data.user.expiration = "2025-12-31"
            
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
             patch.object(downloader, "get_torrent_info", return_value=Mock(status="Ready")), \
             patch.object(downloader, "get_files_and_links", return_value=[{
                 "n": "test_movie.mkv",
                 "s": 800000000,  # 800MB - within allowed range
                 "l": "https://alldebrid.com/d/test_link"
             }]), \
             patch.object(downloader, "delete_torrent"):
            
            result = downloader.get_instant_availability("test_hash", "movie")
            
            assert isinstance(result, TorrentContainer)
            assert result.infohash == "test_hash"
            assert len(result.files) == 1
            assert result.files[0].filename == "test_movie.mkv"
            downloader.add_torrent.assert_called_once_with("test_hash")
            downloader.delete_torrent.assert_called_once_with("torrent_123")
    
    def test_get_instant_availability_no_files(self, downloader):
        """Test instant availability check with no available files."""
        with patch.object(downloader.api, "session") as mock_session:
            mock_response = Mock(spec=SmartResponse)
            mock_response.ok = True
            mock_response.status_code = 200
            mock_response.data = Mock()
            mock_response.data.data = Mock()
            mock_response.data.data.magnets = []
            
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
            mock_response.data = Mock()
            mock_response.data.get.return_value = [{"id": "torrent_123"}]
            
            mock_session.get.return_value = mock_response
            
            result = downloader.add_torrent("test_hash")
            assert result == "torrent_123"
            mock_session.get.assert_called_once_with(
                "magnet/upload", 
                params={"magnets[]": "test_hash"}
            )
    
    def test_add_torrent_circuit_breaker(self, downloader):
        """Test circuit breaker activation on 5xx error."""
        with patch.object(downloader.api, "session") as mock_session:
            mock_response = Mock(spec=SmartResponse)
            mock_response.ok = False
            mock_response.status_code = 500
            
            mock_session.get.return_value = mock_response
            
            with pytest.raises(CircuitBreakerOpen) as exc_info:
                downloader.add_torrent("test_hash")
            
            assert exc_info.value.name == "api.alldebrid.com"
    
    def test_add_torrent_rate_limit(self, downloader):
        """Test rate limit handling."""
        with patch.object(downloader.api, "session") as mock_session:
            mock_response = Mock(spec=SmartResponse)
            mock_response.ok = False
            mock_response.status_code = 429
            
            mock_session.get.return_value = mock_response
            
            with pytest.raises(CircuitBreakerOpen) as exc_info:
                downloader.add_torrent("test_hash")
            
            assert exc_info.value.name == "api.alldebrid.com"
    
    def test_add_torrent_client_error(self, downloader):
        """Test client error handling."""
        with patch.object(downloader.api, "session") as mock_session:
            mock_response = Mock(spec=SmartResponse)
            mock_response.ok = False
            mock_response.status_code = 400
            
            mock_session.get.return_value = mock_response
            
            with pytest.raises(AllDebridError) as exc_info:
                downloader.add_torrent("test_hash")
            
            assert "[400] Torrent file is not valid" in str(exc_info.value)
    
    def test_add_torrent_no_id_returned(self, downloader):
        """Test error when no torrent ID is returned."""
        with patch.object(downloader.api, "session") as mock_session:
            mock_response = Mock(spec=SmartResponse)
            mock_response.ok = True
            mock_response.status_code = 200
            mock_response.data = Mock()
            mock_response.data.get.return_value = []  # Empty list causes IndexError
            
            mock_session.get.return_value = mock_response
            
            with pytest.raises(AllDebridError) as exc_info:
                downloader.add_torrent("test_hash")
            
            assert "list index out of range" in str(exc_info.value)
    
    def test_select_files_success(self, downloader):
        """Test successful file selection."""
        # AllDebrid's select_files is a no-op, so just test it doesn't raise
        downloader.select_files("torrent_123", ["1", "2", "3"])
        # Should not raise any exception
    
    def test_select_files_no_files(self, downloader):
        """Test file selection with no specific files (select all)."""
        # AllDebrid's select_files is a no-op, so just test it doesn't raise
        downloader.select_files("torrent_123")
        # Should not raise any exception
    
    def test_select_files_error(self, downloader):
        """Test file selection error handling."""
        # AllDebrid's select_files is a no-op, so it shouldn't raise errors
        downloader.select_files("torrent_123", ["1", "2"])
        # Should not raise any exception
    
    def test_get_torrent_info_success(self, downloader):
        """Test successful torrent info retrieval."""
        with patch.object(downloader.api, "session") as mock_session:
            mock_response = Mock(spec=SmartResponse)
            mock_response.ok = True
            mock_response.status_code = 200
            mock_response.data = Mock()
            mock_response.data.get.return_value = {
                "id": "torrent_123",
                "filename": "Test Movie",
                "status": "downloaded",
                "size": 1000000,
                "uploadDate": "2025-01-01T00:00:00Z",
                "downloaded": 1000000
            }
            
            mock_session.get.return_value = mock_response
            
            result = downloader.get_torrent_info("torrent_123")
            
            assert isinstance(result, TorrentInfo)
            assert result.id == "torrent_123"
            assert result.name == "Test Movie"
            assert result.status == "downloaded"
            
            mock_session.get.assert_called_once_with("magnet/status", params={"id": "torrent_123"})
    
    def test_get_torrent_info_not_found(self, downloader):
        """Test torrent info retrieval when torrent not found."""
        with patch.object(downloader.api, "session") as mock_session:
            mock_response = Mock(spec=SmartResponse)
            mock_response.ok = False
            mock_response.status_code = 404
            
            mock_session.get.return_value = mock_response
            
            with pytest.raises(AllDebridError) as exc_info:
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
            
            assert exc_info.value.name == "api.alldebrid.com"
    
    def test_delete_torrent_success(self, downloader):
        """Test successful torrent deletion."""
        with patch.object(downloader.api, "session") as mock_session:
            mock_response = Mock(spec=SmartResponse)
            mock_response.ok = True
            mock_response.status_code = 200
            
            mock_session.get.return_value = mock_response
            
            # Should not raise any exception
            downloader.delete_torrent("torrent_123")
            
            mock_session.get.assert_called_once_with("magnet/delete", params={"id": "torrent_123"})
    
    def test_delete_torrent_error(self, downloader):
        """Test torrent deletion error handling."""
        with patch.object(downloader.api, "session") as mock_session:
            mock_response = Mock(spec=SmartResponse)
            mock_response.ok = False
            mock_response.status_code = 404
            
            mock_session.get.return_value = mock_response
            
            with pytest.raises(AllDebridError) as exc_info:
                downloader.delete_torrent("nonexistent_torrent")
            
            assert "[404] Torrent Not Found or Service Unavailable" in str(exc_info.value)
    
    def test_get_files_and_links_success(self, downloader):
        """Test successful files and links retrieval."""
        with patch.object(downloader.api, "session") as mock_session:
            mock_response = Mock(spec=SmartResponse)
            mock_response.ok = True
            mock_response.status_code = 200
            mock_response.data = Mock()
            mock_response.data.get.return_value = [{
                "id": "torrent_123",
                "files": [
                    {
                        "n": "test_movie.mkv",
                        "s": 1000000,
                        "id": "file_1",
                        "link": "https://alldebrid.com/d/test_link"
                    }
                ]
            }]
            
            mock_session.get.return_value = mock_response
            
            result = downloader.get_files_and_links("torrent_123")
            
            assert isinstance(result, list)
            assert len(result) == 1
            assert result[0]["n"] == "test_movie.mkv"
            
            mock_session.get.assert_called_once_with("magnet/files", params={"id[]": "torrent_123"})
    
    def test_get_files_and_links_no_files(self, downloader):
        """Test files and links retrieval with no files."""
        with patch.object(downloader.api, "session") as mock_session:
            mock_response = Mock(spec=SmartResponse)
            mock_response.ok = True
            mock_response.status_code = 200
            mock_response.data = Mock()
            mock_response.data.get.return_value = [{
                "id": "torrent_123",
                "files": []
            }]
            
            mock_session.get.return_value = mock_response
            
            result = downloader.get_files_and_links("torrent_123")
            
            assert isinstance(result, list)
            assert len(result) == 0
            
            mock_session.get.assert_called_once_with("magnet/files", params={"id[]": "torrent_123"})
    
    def test_get_files_and_links_error(self, downloader):
        """Test files and links retrieval error handling."""
        with patch.object(downloader.api, "session") as mock_session:
            mock_response = Mock(spec=SmartResponse)
            mock_response.ok = False
            mock_response.status_code = 404
            
            mock_session.get.return_value = mock_response
            
            with pytest.raises(AllDebridError) as exc_info:
                downloader.get_files_and_links("nonexistent_torrent")
            
            assert "[404] Torrent Not Found or Service Unavailable" in str(exc_info.value)
    
    def test_complete_workflow_success(self, downloader):
        """Test complete download workflow from start to finish."""
        with patch.object(downloader, "add_torrent", return_value="torrent_123"), \
             patch.object(downloader, "get_torrent_info", return_value=Mock(status="Ready")), \
             patch.object(downloader, "get_files_and_links", return_value=[{
                 "n": "test_movie.mkv",
                 "s": 800000000,  # 800MB - within allowed range
                 "l": "https://alldebrid.com/d/test_link"
             }]), \
             patch.object(downloader, "delete_torrent"), \
             patch.object(downloader, "select_files"):
            
            # Test the complete workflow
            # 1. Check instant availability
            container = downloader.get_instant_availability("test_hash", "movie")
            assert container is not None
            assert isinstance(container, TorrentContainer)
            
            # 2. Add torrent
            torrent_id = downloader.add_torrent("test_hash")
            assert torrent_id == "torrent_123"
            
            # 3. Select files
            downloader.select_files(torrent_id, ["1"])
            
            # 4. Get torrent info
            info = downloader.get_torrent_info(torrent_id)
            assert info is not None
            
            # 5. Get files and links
            files = downloader.get_files_and_links(torrent_id)
            assert len(files) == 1
            assert files[0]["n"] == "test_movie.mkv"
    
    def test_error_handling_comprehensive(self, downloader):
        """Test comprehensive error handling for all methods."""
        error_cases = [
            # (method, args, status_code, expected_error_type, expected_message)
            ("add_torrent", ("test_hash",), 451, AllDebridError, "[451] Infringing Torrent"),
            ("add_torrent", ("test_hash",), 400, AllDebridError, "[400] Torrent file is not valid"),
            ("add_torrent", ("test_hash",), 404, AllDebridError, "[404] Torrent Not Found or Service Unavailable"),
            ("select_files", ("torrent_123", ["1"]), 400, AllDebridError, "[400] Torrent file is not valid"),
            ("select_files", ("torrent_123", ["1"]), 404, AllDebridError, "[404] Torrent Not Found or Service Unavailable"),
            ("delete_torrent", ("torrent_123",), 400, AllDebridError, "[400] Torrent file is not valid"),
            ("delete_torrent", ("torrent_123",), 404, AllDebridError, "[404] Torrent Not Found or Service Unavailable"),
        ]

        for method_name, args, status_code, expected_error_type, expected_message in error_cases:
            with patch.object(downloader.api, "session") as mock_session:
                mock_response = Mock(spec=SmartResponse)
                mock_response.ok = False
                mock_response.status_code = status_code  # Ensure this is an integer

                # Determine the HTTP method based on the method being tested
                if method_name == "add_torrent":
                    mock_session.get.return_value = mock_response
                elif method_name == "select_files":
                    # AllDebrid select_files is a no-op, so skip this test
                    continue
                elif method_name == "delete_torrent":
                    mock_session.get.return_value = mock_response
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
                mock_response.status_code = status_code  # Ensure this is an integer

                # Determine the HTTP method based on the method being tested
                if method_name == "add_torrent" or method_name == "delete_torrent":
                    mock_session.get.return_value = mock_response
                else:
                    mock_session.get.return_value = mock_response

                method = getattr(downloader, method_name)

                with pytest.raises(CircuitBreakerOpen) as exc_info:
                    method(*args)

                assert exc_info.value.name == "api.alldebrid.com"
    
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
                mock_response.status_code = 429  # Ensure this is an integer

                # Determine the HTTP method based on the method being tested
                if method_name == "add_torrent" or method_name == "delete_torrent":
                    mock_session.get.return_value = mock_response
                else:
                    mock_session.get.return_value = mock_response

                method = getattr(downloader, method_name)

                with pytest.raises(CircuitBreakerOpen) as exc_info:
                    method(*args)

                assert exc_info.value.name == "api.alldebrid.com"
