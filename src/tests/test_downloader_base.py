"""Tests for the DownloaderBase class and its shared methods."""

from unittest.mock import Mock

import pytest

from program.services.downloaders.shared import DownloaderBase
from program.utils.request import CircuitBreakerOpen, SmartResponse


class TestDownloaderBase(DownloaderBase):
    """Test implementation of DownloaderBase for testing shared methods."""
    
    def validate(self) -> bool:
        return True
    
    def get_instant_availability(self, infohash: str, item_type: str):
        return None
    
    def add_torrent(self, infohash: str):
        return "test_id"
    
    def select_files(self, torrent_id, file_ids):
        pass
    
    def get_torrent_info(self, torrent_id):
        return None
    
    def delete_torrent(self, torrent_id):
        pass


class TestDownloaderBaseMethods:
    """Test the shared methods in DownloaderBase."""
    
    def setup_method(self):
        """Set up test instance."""
        self.downloader = TestDownloaderBase()
    
    def test_maybe_backoff_429_response(self):
        """Test that 429 responses raise CircuitBreakerOpen."""
        # Create mock response with 429 status
        mock_response = Mock(spec=SmartResponse)
        mock_response.status_code = 429
        
        # Should raise CircuitBreakerOpen
        with pytest.raises(CircuitBreakerOpen) as exc_info:
            self.downloader._maybe_backoff(mock_response, "api.test.com")
        
        assert exc_info.value.name == "api.test.com"
    
    def test_maybe_backoff_5xx_responses(self):
        """Test that 5xx responses raise CircuitBreakerOpen."""
        test_cases = [500, 502, 503, 504]
        
        for status_code in test_cases:
            mock_response = Mock(spec=SmartResponse)
            mock_response.status_code = status_code
            
            with pytest.raises(CircuitBreakerOpen) as exc_info:
                self.downloader._maybe_backoff(mock_response, "api.test.com")
            
            assert exc_info.value.name == "api.test.com"
    
    def test_maybe_backoff_successful_responses(self):
        """Test that successful responses don't raise exceptions."""
        test_cases = [200, 201, 400, 401, 403, 404]
        
        for status_code in test_cases:
            mock_response = Mock(spec=SmartResponse)
            mock_response.status_code = status_code
            
            # Should not raise any exception
            self.downloader._maybe_backoff(mock_response, "api.test.com")
    
    def test_handle_error_451(self):
        """Test error handling for 451 status code."""
        mock_response = Mock(spec=SmartResponse)
        mock_response.status_code = 451
        
        result = self.downloader._handle_error(mock_response)
        assert result == "[451] Infringing Torrent"
    
    def test_handle_error_503(self):
        """Test error handling for 503 status code."""
        mock_response = Mock(spec=SmartResponse)
        mock_response.status_code = 503
        
        result = self.downloader._handle_error(mock_response)
        assert result == "[503] Service Unavailable"
    
    def test_handle_error_429(self):
        """Test error handling for 429 status code."""
        mock_response = Mock(spec=SmartResponse)
        mock_response.status_code = 429
        
        result = self.downloader._handle_error(mock_response)
        assert result == "[429] Rate Limit Exceeded"
    
    def test_handle_error_404(self):
        """Test error handling for 404 status code."""
        mock_response = Mock(spec=SmartResponse)
        mock_response.status_code = 404
        
        result = self.downloader._handle_error(mock_response)
        assert result == "[404] Torrent Not Found or Service Unavailable"
    
    def test_handle_error_400(self):
        """Test error handling for 400 status code."""
        mock_response = Mock(spec=SmartResponse)
        mock_response.status_code = 400
        
        result = self.downloader._handle_error(mock_response)
        assert result == "[400] Torrent file is not valid"
    
    def test_handle_error_502(self):
        """Test error handling for 502 status code."""
        mock_response = Mock(spec=SmartResponse)
        mock_response.status_code = 502
        
        result = self.downloader._handle_error(mock_response)
        assert result == "[502] Bad Gateway"
    
    def test_handle_error_unknown_status(self):
        """Test error handling for unknown status codes."""
        mock_response = Mock(spec=SmartResponse)
        mock_response.status_code = 418
        mock_response.reason = "I'm a teapot"
        
        result = self.downloader._handle_error(mock_response)
        assert result == "I'm a teapot"
    
    def test_handle_error_no_reason(self):
        """Test error handling when response has no reason."""
        mock_response = Mock(spec=SmartResponse)
        mock_response.status_code = 999
        mock_response.reason = None
        
        result = self.downloader._handle_error(mock_response)
        assert result == "HTTP 999"
    
    def test_maybe_backoff_domain_parameter(self):
        """Test that the domain parameter is correctly passed to CircuitBreakerOpen."""
        mock_response = Mock(spec=SmartResponse)
        mock_response.status_code = 429
        
        test_domains = ["api.real-debrid.com", "api.alldebrid.com", "api.torbox.app"]
        
        for domain in test_domains:
            with pytest.raises(CircuitBreakerOpen) as exc_info:
                self.downloader._maybe_backoff(mock_response, domain)
            
            assert exc_info.value.name == domain
