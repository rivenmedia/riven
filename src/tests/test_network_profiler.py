"""Unit tests for the NetworkProfiler module."""

import threading
import time
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from program.utils.network_profiler import NetworkProfiler, RequestMetrics


class TestRequestMetrics:
    """Test the RequestMetrics dataclass."""
    
    def test_request_metrics_creation(self):
        """Test basic RequestMetrics creation."""
        metrics = RequestMetrics(
            url="https://api.example.com/test",
            method="GET",
            status_code=200,
            duration=1.5,
            timestamp=datetime.now(),
            success=True,
            service_name="test_service"
        )
        
        assert metrics.url == "https://api.example.com/test"
        assert metrics.method == "GET"
        assert metrics.status_code == 200
        assert metrics.duration == 1.5
        assert metrics.success is True
        assert metrics.service_name == "test_service"
    
    def test_domain_extraction(self):
        """Test domain extraction from URLs."""
        metrics = RequestMetrics(
            url="https://api.example.com/v1/test",
            method="GET",
            status_code=200,
            duration=1.0,
            timestamp=datetime.now(),
            success=True
        )
        
        assert metrics.domain == "api.example.com"
    
    def test_domain_extraction_invalid_url(self):
        """Test domain extraction with invalid URL."""
        metrics = RequestMetrics(
            url="invalid-url",
            method="GET",
            status_code=200,
            duration=1.0,
            timestamp=datetime.now(),
            success=True
        )
        
        assert metrics.domain == "unknown"
    
    def test_url_pattern_extraction(self):
        """Test URL pattern extraction."""
        test_cases = [
            ("https://api.example.com/users/123", "api.example.com/users/{id}"),
            ("https://api.example.com/items/abc123def", "api.example.com/items/{hash}"),
            ("https://api.example.com/movies/tt1234567", "api.example.com/movies/{imdb_id}"),
            ("https://api.example.com/auth/ABC123XYZ", "api.example.com/auth/{token}"),
        ]
        
        for url, expected_pattern in test_cases:
            metrics = RequestMetrics(
                url=url,
                method="GET",
                status_code=200,
                duration=1.0,
                timestamp=datetime.now(),
                success=True
            )
            assert metrics.url_pattern == expected_pattern
    
    def test_is_slow(self):
        """Test slow request detection."""
        fast_metrics = RequestMetrics(
            url="https://api.example.com/test",
            method="GET",
            status_code=200,
            duration=1.0,
            timestamp=datetime.now(),
            success=True
        )
        
        slow_metrics = RequestMetrics(
            url="https://api.example.com/test",
            method="GET",
            status_code=200,
            duration=3.0,
            timestamp=datetime.now(),
            success=True
        )
        
        assert not fast_metrics.is_slow(2.0)
        assert slow_metrics.is_slow(2.0)


class TestNetworkProfiler:
    """Test the NetworkProfiler class."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.profiler = NetworkProfiler(max_stored_requests=100, slow_threshold=2.0)
    
    def test_initialization(self):
        """Test NetworkProfiler initialization."""
        assert not self.profiler.enabled
        assert self.profiler._max_stored_requests == 100
        assert self.profiler._slow_threshold == 2.0
        assert len(self.profiler._requests) == 0
    
    def test_enable_disable(self):
        """Test enabling and disabling profiling."""
        assert not self.profiler.enabled
        
        self.profiler.enable()
        assert self.profiler.enabled
        
        self.profiler.disable()
        assert not self.profiler.enabled
    
    def test_record_request_disabled(self):
        """Test that requests are not recorded when profiling is disabled."""
        self.profiler.record_request(
            url="https://api.example.com/test",
            method="GET",
            duration=1.5,
            status_code=200,
            success=True
        )
        
        assert len(self.profiler._requests) == 0
        assert self.profiler._total_requests == 0
    
    def test_record_request_enabled(self):
        """Test recording requests when profiling is enabled."""
        self.profiler.enable()
        
        self.profiler.record_request(
            url="https://api.example.com/test",
            method="GET",
            duration=1.5,
            status_code=200,
            success=True,
            service_name="test_service"
        )
        
        assert len(self.profiler._requests) == 1
        assert self.profiler._total_requests == 1
        assert self.profiler._total_duration == 1.5
        
        request = self.profiler._requests[0]
        assert request.url == "https://api.example.com/test"
        assert request.method == "GET"
        assert request.duration == 1.5
        assert request.success is True
        assert request.service_name == "test_service"
    
    def test_record_slow_request(self):
        """Test recording slow requests."""
        self.profiler.enable()
        
        # Record a slow request
        self.profiler.record_request(
            url="https://api.example.com/slow",
            method="GET",
            duration=3.0,
            status_code=200,
            success=True
        )
        
        assert self.profiler._slow_requests_count == 1
    
    def test_record_error_request(self):
        """Test recording error requests."""
        self.profiler.enable()
        
        # Record an error request
        self.profiler.record_request(
            url="https://api.example.com/error",
            method="GET",
            duration=1.0,
            status_code=500,
            success=False,
            error_message="Internal Server Error"
        )
        
        assert self.profiler._error_count == 1
    
    def test_memory_limit(self):
        """Test that memory limit is respected."""
        profiler = NetworkProfiler(max_stored_requests=5)
        profiler.enable()
        
        # Add more requests than the limit
        for i in range(10):
            profiler.record_request(
                url=f"https://api.example.com/test{i}",
                method="GET",
                duration=1.0,
                status_code=200,
                success=True
            )
        
        # Should only keep the last 5 requests
        assert len(profiler._requests) == 5
        assert profiler._total_requests == 10  # Total count should still be accurate
    
    def test_thread_safety(self):
        """Test thread safety of the profiler."""
        self.profiler.enable()
        
        def record_requests(thread_id):
            for i in range(50):
                self.profiler.record_request(
                    url=f"https://api.example.com/thread{thread_id}/request{i}",
                    method="GET",
                    duration=1.0,
                    status_code=200,
                    success=True
                )
        
        # Create multiple threads
        threads = []
        for i in range(5):
            thread = threading.Thread(target=record_requests, args=(i,))
            threads.append(thread)
            thread.start()
        
        # Wait for all threads to complete
        for thread in threads:
            thread.join()
        
        # Should have recorded all requests
        assert self.profiler._total_requests == 250
        # But only keep the last 100 due to memory limit
        assert len(self.profiler._requests) == 100
    
    def test_get_statistics(self):
        """Test statistics calculation."""
        self.profiler.enable()
        
        # Add some test data
        self.profiler.record_request("https://api.example.com/fast", "GET", 1.0, 200, True)
        self.profiler.record_request("https://api.example.com/slow", "GET", 3.0, 200, True)
        self.profiler.record_request("https://api.example.com/error", "GET", 1.5, 500, False)
        
        stats = self.profiler.get_statistics()
        
        assert stats["enabled"] is True
        assert stats["total_requests"] == 3
        assert stats["average_duration"] == 1.833333333333333  # (1.0 + 3.0 + 1.5) / 3
        assert stats["slow_requests_count"] == 1
        assert stats["error_count"] == 1
        assert stats["slow_requests_percentage"] == 33.333333333333336  # 1/3 * 100
        assert stats["error_percentage"] == 33.333333333333336  # 1/3 * 100
    
    def test_get_slow_requests(self):
        """Test retrieving slow requests."""
        self.profiler.enable()
        
        # Add test data
        self.profiler.record_request("https://api.example.com/fast", "GET", 1.0, 200, True)
        self.profiler.record_request("https://api.example.com/slow1", "GET", 3.0, 200, True)
        self.profiler.record_request("https://api.example.com/slow2", "GET", 4.0, 200, True)
        
        slow_requests = self.profiler.get_slow_requests()
        
        assert len(slow_requests) == 2
        # Should be in reverse order (most recent first)
        assert slow_requests[0].url == "https://api.example.com/slow2"
        assert slow_requests[1].url == "https://api.example.com/slow1"
    
    def test_clear_data(self):
        """Test clearing profiling data."""
        self.profiler.enable()
        
        # Add some data
        self.profiler.record_request("https://api.example.com/test", "GET", 1.0, 200, True)
        
        assert len(self.profiler._requests) == 1
        assert self.profiler._total_requests == 1
        
        # Clear data
        self.profiler.clear_data()
        
        assert len(self.profiler._requests) == 0
        assert self.profiler._total_requests == 0
        assert self.profiler._total_duration == 0.0
        assert self.profiler._slow_requests_count == 0
        assert self.profiler._error_count == 0

    def test_get_requests_by_domain(self):
        """Test grouping requests by domain."""
        self.profiler.enable()

        # Add requests from different domains
        self.profiler.record_request("https://api1.example.com/test", "GET", 1.0, 200, True)
        self.profiler.record_request("https://api1.example.com/test2", "GET", 1.5, 200, True)
        self.profiler.record_request("https://api2.example.com/test", "GET", 2.0, 200, True)

        domain_groups = self.profiler.get_requests_by_domain()

        assert len(domain_groups) == 2
        assert "api1.example.com" in domain_groups
        assert "api2.example.com" in domain_groups
        assert len(domain_groups["api1.example.com"]) == 2
        assert len(domain_groups["api2.example.com"]) == 1

    def test_get_requests_by_pattern(self):
        """Test grouping requests by URL pattern."""
        self.profiler.enable()

        # Add requests with similar patterns
        self.profiler.record_request("https://api.example.com/users/123", "GET", 1.0, 200, True)
        self.profiler.record_request("https://api.example.com/users/456", "GET", 1.5, 200, True)
        self.profiler.record_request("https://api.example.com/posts/789", "GET", 2.0, 200, True)

        pattern_groups = self.profiler.get_requests_by_pattern()

        assert len(pattern_groups) == 2
        assert "api.example.com/users/{id}" in pattern_groups
        assert "api.example.com/posts/{id}" in pattern_groups
        assert len(pattern_groups["api.example.com/users/{id}"]) == 2
        assert len(pattern_groups["api.example.com/posts/{id}"]) == 1

    def test_get_requests_by_service(self):
        """Test grouping requests by service."""
        self.profiler.enable()

        # Add requests from different services
        self.profiler.record_request("https://api.example.com/test1", "GET", 1.0, 200, True, service_name="service1")
        self.profiler.record_request("https://api.example.com/test2", "GET", 1.5, 200, True, service_name="service1")
        self.profiler.record_request("https://api.example.com/test3", "GET", 2.0, 200, True, service_name="service2")
        self.profiler.record_request("https://api.example.com/test4", "GET", 2.5, 200, True)  # No service name

        service_groups = self.profiler.get_requests_by_service()

        assert len(service_groups) == 3
        assert "service1" in service_groups
        assert "service2" in service_groups
        assert "unknown" in service_groups
        assert len(service_groups["service1"]) == 2
        assert len(service_groups["service2"]) == 1
        assert len(service_groups["unknown"]) == 1

    def test_get_requests_in_timeframe(self):
        """Test filtering requests by timeframe."""
        self.profiler.enable()

        # Add requests with different timestamps
        now = datetime.now()
        old_time = now - timedelta(hours=2)

        # Manually create requests with specific timestamps
        old_request = RequestMetrics(
            url="https://api.example.com/old",
            method="GET",
            status_code=200,
            duration=1.0,
            timestamp=old_time,
            success=True
        )

        recent_request = RequestMetrics(
            url="https://api.example.com/recent",
            method="GET",
            status_code=200,
            duration=1.0,
            timestamp=now,
            success=True
        )

        # Add to profiler manually
        self.profiler._requests.extend([old_request, recent_request])

        # Get requests from last 60 minutes
        recent_requests = self.profiler.get_requests_in_timeframe(60)

        assert len(recent_requests) == 1
        assert recent_requests[0].url == "https://api.example.com/recent"

    def test_calculate_percentiles(self):
        """Test percentile calculations."""
        self.profiler.enable()

        # Add requests with known durations
        durations = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]
        for i, duration in enumerate(durations):
            self.profiler.record_request(f"https://api.example.com/test{i}", "GET", duration, 200, True)

        percentiles = self.profiler.calculate_percentiles()

        assert "p50" in percentiles
        assert "p95" in percentiles
        assert "p99" in percentiles

        # With our test data, p50 should be around 5.5
        assert 5.0 <= percentiles["p50"] <= 6.0
        # p95 should be around 9.5
        assert 9.0 <= percentiles["p95"] <= 10.0

    def test_calculate_request_rate(self):
        """Test request rate calculation."""
        self.profiler.enable()

        # Add some recent requests
        for i in range(10):
            self.profiler.record_request(f"https://api.example.com/test{i}", "GET", 1.0, 200, True)

        # Calculate rate for last 60 minutes
        rate = self.profiler.calculate_request_rate(60)

        # Should be 10 requests / 3600 seconds = ~0.0028 requests/second
        assert 0.002 <= rate <= 0.004

    def test_export_to_json(self):
        """Test JSON export functionality."""
        self.profiler.enable()

        # Add some test data
        self.profiler.record_request("https://api.example.com/test", "GET", 1.5, 200, True, service_name="test")

        # Test export with requests
        json_data = self.profiler.export_to_json(include_requests=True)
        assert "export_timestamp" in json_data
        assert "statistics" in json_data
        assert "requests" in json_data

        # Test export without requests
        json_data_no_requests = self.profiler.export_to_json(include_requests=False)
        assert "export_timestamp" in json_data_no_requests
        assert "statistics" in json_data_no_requests
        assert "requests" not in json_data_no_requests

    def test_export_to_csv(self):
        """Test CSV export functionality."""
        self.profiler.enable()

        # Add some test data
        self.profiler.record_request("https://api.example.com/test", "GET", 1.5, 200, True, service_name="test")

        csv_data = self.profiler.export_to_csv()

        # Check CSV structure
        lines = csv_data.strip().split('\n')
        assert len(lines) == 2  # Header + 1 data row

        header = lines[0]
        assert "timestamp" in header
        assert "url" in header
        assert "method" in header
        assert "duration" in header

    def test_apply_retention_policy(self):
        """Test retention policy application."""
        self.profiler.enable()

        # Add old and new requests
        now = datetime.now()
        old_time = now - timedelta(hours=25)  # Older than 24 hours

        # Add old request manually
        old_request = RequestMetrics(
            url="https://api.example.com/old",
            method="GET",
            status_code=200,
            duration=1.0,
            timestamp=old_time,
            success=True
        )
        self.profiler._requests.append(old_request)

        # Add recent request
        self.profiler.record_request("https://api.example.com/recent", "GET", 1.0, 200, True)

        assert len(self.profiler._requests) == 2

        # Apply retention policy (24 hours)
        removed_count = self.profiler.apply_retention_policy(24)

        assert removed_count == 1
        assert len(self.profiler._requests) == 1
        assert self.profiler._requests[0].url == "https://api.example.com/recent"

    def test_get_memory_usage_estimate(self):
        """Test memory usage estimation."""
        self.profiler.enable()

        # Add some requests
        for i in range(10):
            self.profiler.record_request(f"https://api.example.com/test{i}", "GET", 1.0, 200, True)

        usage = self.profiler.get_memory_usage_estimate()

        assert usage["requests_count"] == 10
        assert usage["estimated_bytes"] > 0
        assert "estimated_mb" in usage

    @patch('program.utils.network_profiler.notify')
    def test_alerting_slow_request(self, mock_notify):
        """Test alerting for slow requests."""
        # Mock settings to enable alerts
        with patch.object(self.profiler, '_get_settings') as mock_settings:
            mock_settings.return_value.enable_alerts = True
            mock_settings.return_value.alert_slow_request_threshold = 5.0
            mock_settings.return_value.alert_cooldown_minutes = 1

            self.profiler.enable()

            # Record a very slow request
            self.profiler.record_request(
                "https://api.example.com/very-slow",
                "GET",
                6.0,  # Exceeds threshold
                200,
                True
            )

            # Should have sent an alert
            mock_notify.assert_called_once()
            args = mock_notify.call_args[0]
            assert "Extremely Slow Network Request" in args[0]

    @patch('program.utils.network_profiler.notify')
    def test_alerting_high_error_rate(self, mock_notify):
        """Test alerting for high error rates."""
        with patch.object(self.profiler, '_get_settings') as mock_settings:
            mock_settings.return_value.enable_alerts = True
            mock_settings.return_value.alert_error_rate_threshold = 50.0
            mock_settings.return_value.alert_cooldown_minutes = 1

            self.profiler.enable()

            # Add requests to build up error rate
            for i in range(10):
                success = i < 4  # 6 failures out of 10 = 60% error rate
                self.profiler.record_request(
                    f"https://api.example.com/test{i}",
                    "GET",
                    1.0,
                    500 if not success else 200,
                    success,
                    error_message="Server Error" if not success else None
                )

            # Should have sent an alert for high error rate
            mock_notify.assert_called()
            args = mock_notify.call_args[0]
            assert "High Network Error Rate" in args[0]
