"""Integration tests for the NetworkProfiler module."""

import json
import time
from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient

from program.settings.manager import settings_manager
from program.utils.network_profiler import network_profiler
from program.utils.request import BaseRequestHandler, HttpMethod
from routers.secure.debug import router as debug_router


class TestNetworkProfilerIntegration:
    """Integration tests for NetworkProfiler with actual components."""
    
    def setup_method(self):
        """Set up test fixtures."""
        # Reset profiler state
        network_profiler.disable()
        network_profiler.clear_data()
        
        # Reset settings to defaults
        settings_manager.settings.network_profiling.enabled = False
        settings_manager.settings.network_profiling.slow_request_threshold = 2.0
        settings_manager.settings.network_profiling.enable_alerts = False
    
    def test_request_handler_integration(self):
        """Test integration with BaseRequestHandler."""
        # Enable profiling
        network_profiler.enable()
        
        # Create a mock session
        mock_session = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {"Content-Type": "application/json"}
        mock_response.content = b'{"test": "data"}'
        mock_response.raise_for_status.return_value = None
        mock_session.request.return_value = mock_response
        
        # Create request handler with service name
        handler = BaseRequestHandler(
            session=mock_session,
            service_name="test_service"
        )
        
        # Make a request
        start_time = time.time()
        response = handler._request(HttpMethod.GET, "https://api.example.com/test")
        end_time = time.time()
        
        # Verify request was recorded
        assert network_profiler._total_requests == 1
        assert len(network_profiler._requests) == 1
        
        recorded_request = network_profiler._requests[0]
        assert recorded_request.url == "https://api.example.com/test"
        assert recorded_request.method == "GET"
        assert recorded_request.status_code == 200
        assert recorded_request.success is True
        assert recorded_request.service_name == "test_service"
        assert start_time <= recorded_request.timestamp.timestamp() <= end_time
    
    def test_request_handler_error_integration(self):
        """Test integration with BaseRequestHandler for error cases."""
        # Enable profiling
        network_profiler.enable()
        
        # Create a mock session that raises an exception
        mock_session = MagicMock()
        mock_session.request.side_effect = Exception("Connection failed")
        
        handler = BaseRequestHandler(
            session=mock_session,
            service_name="test_service"
        )
        
        # Make a request that will fail
        with pytest.raises(Exception):
            handler._request(HttpMethod.GET, "https://api.example.com/error")
        
        # Verify error was recorded
        assert network_profiler._total_requests == 1
        assert network_profiler._error_count == 1
        
        recorded_request = network_profiler._requests[0]
        assert recorded_request.success is False
        assert "Connection failed" in recorded_request.error_message
    
    def test_settings_integration(self):
        """Test integration with settings system."""
        # Test that profiler respects settings
        settings_manager.settings.network_profiling.enabled = True
        settings_manager.settings.network_profiling.slow_request_threshold = 1.0
        
        network_profiler.enable()
        
        # Record a request that would be slow with new threshold
        network_profiler.record_request(
            url="https://api.example.com/test",
            method="GET",
            duration=1.5,
            status_code=200,
            success=True
        )
        
        # Should be counted as slow with threshold of 1.0
        slow_requests = network_profiler.get_slow_requests()
        assert len(slow_requests) == 1
        
        # Test statistics reflect settings
        stats = network_profiler.get_statistics()
        assert stats["slow_threshold"] == 1.0
        assert stats["enabled"] is True
    
    def test_cli_arguments_integration(self):
        """Test CLI argument handling."""
        from program.utils.cli import handle_args
        
        # Mock command line arguments
        with patch('sys.argv', ['program', '--profile-network', '--profile-threshold', '3.0']):
            args = handle_args()
            
            # Verify settings were updated
            assert settings_manager.settings.network_profiling.enabled is True
            assert settings_manager.settings.network_profiling.slow_request_threshold == 3.0
    
    def test_performance_impact(self):
        """Test performance impact of profiling."""
        # Create a mock session for testing
        mock_session = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {"Content-Type": "application/json"}
        mock_response.content = b'{"test": "data"}'
        mock_response.raise_for_status.return_value = None
        mock_session.request.return_value = mock_response
        
        handler = BaseRequestHandler(session=mock_session)
        
        # Measure performance without profiling
        network_profiler.disable()
        start_time = time.perf_counter()
        for _ in range(100):
            handler._request(HttpMethod.GET, "https://api.example.com/test")
        disabled_time = time.perf_counter() - start_time
        
        # Measure performance with profiling
        network_profiler.enable()
        start_time = time.perf_counter()
        for _ in range(100):
            handler._request(HttpMethod.GET, "https://api.example.com/test")
        enabled_time = time.perf_counter() - start_time
        
        # Performance impact should be minimal (less than 50% overhead)
        overhead_ratio = enabled_time / disabled_time
        assert overhead_ratio < 1.5, f"Performance overhead too high: {overhead_ratio:.2f}x"
        
        # Verify requests were recorded
        assert network_profiler._total_requests == 100


class TestDebugAPIIntegration:
    """Integration tests for debug API endpoints."""
    
    def setup_method(self):
        """Set up test fixtures."""
        # Reset profiler state
        network_profiler.disable()
        network_profiler.clear_data()
        
        # Create test client
        from fastapi import FastAPI
        app = FastAPI()
        app.include_router(debug_router)
        self.client = TestClient(app)
    
    def test_network_stats_endpoint(self):
        """Test /debug/network-stats endpoint."""
        # Enable profiling and add some data
        network_profiler.enable()
        network_profiler.record_request(
            url="https://api.example.com/test",
            method="GET",
            duration=1.5,
            status_code=200,
            success=True
        )
        
        response = self.client.get("/debug/network-stats")
        assert response.status_code == 200
        
        data = response.json()
        assert data["enabled"] is True
        assert data["total_requests"] == 1
        assert data["average_duration"] == 1.5
    
    def test_profiling_enable_disable_endpoints(self):
        """Test profiling enable/disable endpoints."""
        # Test enable
        response = self.client.post("/debug/network-profiling/enable")
        assert response.status_code == 200
        assert network_profiler.enabled is True
        
        data = response.json()
        assert data["enabled"] is True
        assert "enabled successfully" in data["message"]
        
        # Test disable
        response = self.client.post("/debug/network-profiling/disable")
        assert response.status_code == 200
        assert network_profiler.enabled is False
        
        data = response.json()
        assert data["enabled"] is False
        assert "disabled successfully" in data["message"]
    
    def test_slow_requests_endpoint(self):
        """Test /debug/network-profiling/slow-requests endpoint."""
        network_profiler.enable()
        
        # Add some requests
        network_profiler.record_request("https://api.example.com/fast", "GET", 1.0, 200, True)
        network_profiler.record_request("https://api.example.com/slow", "GET", 3.0, 200, True)
        
        response = self.client.get("/debug/network-profiling/slow-requests?limit=10")
        assert response.status_code == 200
        
        data = response.json()
        assert data["total_count"] == 1
        assert len(data["slow_requests"]) == 1
        assert data["slow_requests"][0]["url"] == "https://api.example.com/slow"
        assert data["slow_requests"][0]["duration"] == 3.0
    
    def test_export_endpoints(self):
        """Test export endpoints."""
        network_profiler.enable()
        
        # Add some test data
        network_profiler.record_request(
            url="https://api.example.com/test",
            method="GET",
            duration=1.5,
            status_code=200,
            success=True,
            service_name="test_service"
        )
        
        # Test JSON export
        response = self.client.get("/debug/network-profiling/export/json")
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/json"
        
        # Verify it's valid JSON
        json_data = json.loads(response.content)
        assert "export_timestamp" in json_data
        assert "statistics" in json_data
        assert "requests" in json_data
        
        # Test CSV export
        response = self.client.get("/debug/network-profiling/export/csv")
        assert response.status_code == 200
        assert response.headers["content-type"] == "text/csv; charset=utf-8"
        
        # Verify CSV structure
        csv_content = response.content.decode()
        lines = csv_content.strip().split('\n')
        assert len(lines) >= 2  # Header + at least one data row
        assert "timestamp" in lines[0]
        assert "url" in lines[0]
    
    def test_advanced_stats_endpoint(self):
        """Test advanced statistics endpoint."""
        network_profiler.enable()
        
        # Add test data with various durations
        durations = [1.0, 2.0, 3.0, 4.0, 5.0]
        for i, duration in enumerate(durations):
            network_profiler.record_request(
                f"https://api.example.com/test{i}",
                "GET",
                duration,
                200,
                True
            )
        
        response = self.client.get("/debug/network-profiling/advanced-stats")
        assert response.status_code == 200
        
        data = response.json()
        assert "percentiles" in data
        assert "p50" in data["percentiles"]
        assert "p95" in data["percentiles"]
        assert "p99" in data["percentiles"]
        assert "request_rate_per_second" in data
    
    def test_health_endpoint(self):
        """Test network health endpoint."""
        network_profiler.enable()
        
        # Add some test data
        network_profiler.record_request("https://api.example.com/test", "GET", 1.0, 200, True)
        
        response = self.client.get("/debug/network-profiling/health")
        assert response.status_code == 200
        
        data = response.json()
        assert "health_check_enabled" in data
        assert "status" in data
    
    def test_clear_data_endpoint(self):
        """Test clear data endpoint."""
        network_profiler.enable()
        
        # Add some data
        network_profiler.record_request("https://api.example.com/test", "GET", 1.0, 200, True)
        assert len(network_profiler._requests) == 1
        
        # Clear data
        response = self.client.post("/debug/network-profiling/clear")
        assert response.status_code == 200
        
        data = response.json()
        assert "cleared successfully" in data["message"]
        assert len(network_profiler._requests) == 0
    
    def test_memory_usage_endpoint(self):
        """Test memory usage endpoint."""
        network_profiler.enable()
        
        # Add some data
        for i in range(10):
            network_profiler.record_request(f"https://api.example.com/test{i}", "GET", 1.0, 200, True)
        
        response = self.client.get("/debug/network-profiling/memory-usage")
        assert response.status_code == 200
        
        data = response.json()
        assert data["requests_count"] == 10
        assert data["estimated_bytes"] > 0
        assert "estimated_mb" in data
    
    def test_retention_policy_endpoint(self):
        """Test retention policy endpoint."""
        network_profiler.enable()
        
        # Add some data
        network_profiler.record_request("https://api.example.com/test", "GET", 1.0, 200, True)
        
        response = self.client.post("/debug/network-profiling/retention-policy?max_age_hours=1")
        assert response.status_code == 200
        
        data = response.json()
        assert "removed_count" in data
        assert "remaining_count" in data
        assert "message" in data
