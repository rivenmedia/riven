"""Network profiling module for monitoring HTTP request performance."""

import time
import threading
import re
import json
import csv
import io
from collections import deque, defaultdict
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Deque, Union
from urllib.parse import urlparse
import statistics

from loguru import logger


@dataclass
class RequestMetrics:
    url: str
    method: str
    status_code: Optional[int]
    duration: float
    timestamp: datetime
    success: bool
    error_message: Optional[str] = None
    service_name: Optional[str] = None

    @property
    def domain(self) -> str:
        try:
            return urlparse(self.url).netloc
        except Exception:
            return "unknown"

    @property
    def url_pattern(self) -> str:
        try:
            parsed = urlparse(self.url)
            path = parsed.path
            path = re.sub(r'/\d+', '/{id}', path)
            path = re.sub(r'/[a-f0-9]{8,}', '/{hash}', path)
            path = re.sub(r'/tt\d+', '/{imdb_id}', path)
            path = re.sub(r'/[A-Z0-9]{8,}', '/{token}', path)  # Tokens/API keys

            return f"{parsed.netloc}{path}"
        except Exception:
            return self.url

    def is_slow(self, threshold: float = 2.0) -> bool:
        """Check if request is considered slow based on threshold."""
        return self.duration > threshold


class NetworkProfiler:
    """Thread-safe network profiler for monitoring HTTP request performance."""

    def __init__(self, max_stored_requests: int = 1000, slow_threshold: float = 2.0):
        self._enabled = False
        self._max_stored_requests = max_stored_requests
        self._slow_threshold = slow_threshold
        self._lock = threading.RLock()
        self._requests: Deque[RequestMetrics] = deque(maxlen=max_stored_requests)
        self._total_requests = 0
        self._total_duration = 0.0
        self._slow_requests_count = 0
        self._error_count = 0

        # Error tracking
        self._error_count_consecutive = 0
        self._last_error_time = None

        # Alerting tracking
        self._last_alert_times = {}

        # Performance metrics
        self._performance_metrics = {
            "profiling_overhead_total": 0.0,
            "profiling_calls_total": 0,
            "memory_cleanups": 0,
            "auto_disables": 0
        }

    def _get_settings(self):
        try:
            from program.settings.manager import settings_manager
            return settings_manager.settings.network_profiling
        except (ImportError, AttributeError):
            class DefaultSettings:
                enabled = False
                slow_request_threshold = 2.0
                max_stored_requests = 1000
                log_slow_requests = True
                graceful_degradation = True
                enable_alerts = False
                alert_slow_request_threshold = 10.0
                alert_error_rate_threshold = 10.0
                alert_cooldown_minutes = 60
            return DefaultSettings()

    def _is_feature_enabled(self) -> bool:
        settings = self._get_settings()
        return self._enabled and settings.enabled

    def _handle_error(self, error: Exception, operation: str) -> None:
        """Handle errors with simple logging."""
        self._error_count_consecutive += 1
        self._last_error_time = datetime.now()
        logger.error(f"Network profiling error in {operation}: {error}")

    def _check_memory_usage(self) -> None:
        """Simple memory management."""
        if len(self._requests) >= self._max_stored_requests * 0.9:
            # Remove oldest 25% of requests when approaching limit
            remove_count = len(self._requests) // 4
            for _ in range(remove_count):
                if self._requests:
                    self._requests.popleft()
            self._performance_metrics["memory_cleanups"] += 1

    def _measure_performance_impact(self, operation_time: float) -> None:
        """Track performance impact of profiling."""
        self._performance_metrics["profiling_overhead_total"] += operation_time
        self._performance_metrics["profiling_calls_total"] += 1
    
    def enable(self) -> None:
        """Enable network profiling."""
        with self._lock:
            self._enabled = True
            logger.info("Network profiling enabled")
    
    def disable(self) -> None:
        """Disable network profiling."""
        with self._lock:
            self._enabled = False
            logger.info("Network profiling disabled")
    
    @property
    def enabled(self) -> bool:
        """Check if profiling is enabled."""
        return self._enabled
    
    def record_request(
        self,
        url: str,
        method: str,
        duration: float,
        status_code: Optional[int] = None,
        success: bool = True,
        error_message: Optional[str] = None,
        service_name: Optional[str] = None
    ) -> None:
        """
        Record a request's metrics with production-ready error handling.

        Args:
            url: The request URL
            method: HTTP method (GET, POST, etc.)
            duration: Request duration in seconds
            status_code: HTTP status code (if available)
            success: Whether the request was successful
            error_message: Error message if request failed
            service_name: Name of the service making the request
        """
        # Quick feature flag check
        if not self._is_feature_enabled():
            return

        start_time = time.perf_counter()

        try:
            settings = self._get_settings()

            metrics = RequestMetrics(
                url=url,
                method=method,
                status_code=status_code,
                duration=duration,
                timestamp=datetime.now(),
                success=success,
                error_message=error_message,
                service_name=service_name
            )

            with self._lock:
                self._requests.append(metrics)
                self._total_requests += 1
                self._total_duration += duration

                if not success:
                    self._error_count += 1

                if metrics.is_slow(settings.slow_request_threshold):
                    self._slow_requests_count += 1
                    # Log slow requests immediately if enabled
                    if settings.log_slow_requests:
                        logger.warning(
                            f"Slow request detected: {method} {url} took {duration:.2f}s "
                            f"(status: {status_code}, service: {service_name or 'unknown'})"
                        )

                # Check for alerts
                self._check_and_send_alerts(metrics)

                # Periodic memory check (every 100 requests)
                if self._total_requests % 100 == 0:
                    self._check_memory_usage()

            # Reset consecutive error count on success
            self._error_count_consecutive = 0

        except Exception as e:
            settings = self._get_settings()
            if settings.graceful_degradation:
                self._handle_error(e, "record_request")
            else:
                raise

        finally:
            # Measure performance impact
            operation_time = time.perf_counter() - start_time
            self._measure_performance_impact(operation_time)
    
    def get_slow_requests(self, limit: int = 50) -> List[RequestMetrics]:
        """
        Get the most recent slow requests.

        Args:
            limit: Maximum number of slow requests to return

        Returns:
            List of slow RequestMetrics, most recent first
        """
        settings = self._get_settings()
        with self._lock:
            slow_requests = [req for req in self._requests if req.is_slow(settings.slow_request_threshold)]
            # Return most recent first
            return list(reversed(slow_requests))[:limit]
    
    def get_statistics(self) -> Dict:
        """
        Get comprehensive statistics about recorded requests.

        Returns:
            Dictionary containing various statistics
        """
        settings = self._get_settings()
        with self._lock:
            if self._total_requests == 0:
                return {
                    "enabled": self._enabled and settings.enabled,
                    "total_requests": 0,
                    "average_duration": 0.0,
                    "slow_requests_count": 0,
                    "error_count": 0,
                    "slow_requests_percentage": 0.0,
                    "error_percentage": 0.0,
                    "stored_requests": 0,
                    "max_stored_requests": settings.max_stored_requests,
                    "slow_threshold": settings.slow_request_threshold
                }

            return {
                "enabled": self._enabled and settings.enabled,
                "total_requests": self._total_requests,
                "average_duration": self._total_duration / self._total_requests,
                "slow_requests_count": self._slow_requests_count,
                "error_count": self._error_count,
                "slow_requests_percentage": (self._slow_requests_count / self._total_requests) * 100,
                "error_percentage": (self._error_count / self._total_requests) * 100,
                "stored_requests": len(self._requests),
                "max_stored_requests": settings.max_stored_requests,
                "slow_threshold": settings.slow_request_threshold
            }
    
    def get_requests_by_domain(self) -> Dict[str, List[RequestMetrics]]:
        """
        Group stored requests by domain.
        
        Returns:
            Dictionary mapping domain names to lists of RequestMetrics
        """
        with self._lock:
            domain_groups = {}
            for request in self._requests:
                domain = request.domain
                if domain not in domain_groups:
                    domain_groups[domain] = []
                domain_groups[domain].append(request)
            return domain_groups
    
    def log_summary(self) -> None:
        """Log a summary of current profiling statistics."""
        stats = self.get_statistics()
        
        if not stats["enabled"]:
            logger.debug("Network profiling is disabled")
            return
        
        if stats["total_requests"] == 0:
            logger.info("Network profiling summary: No requests recorded yet")
            return
        
        logger.info(
            f"Network profiling summary: "
            f"{stats['total_requests']} total requests, "
            f"avg duration: {stats['average_duration']:.2f}s, "
            f"slow requests: {stats['slow_requests_count']} ({stats['slow_requests_percentage']:.1f}%), "
            f"errors: {stats['error_count']} ({stats['error_percentage']:.1f}%)"
        )
    
    def clear_data(self) -> None:
        """Clear all stored request data and reset statistics."""
        with self._lock:
            self._requests.clear()
            self._total_requests = 0
            self._total_duration = 0.0
            self._slow_requests_count = 0
            self._error_count = 0
            logger.info("Network profiling data cleared")

    def get_requests_by_pattern(self) -> Dict[str, List[RequestMetrics]]:
        """Group stored requests by URL pattern."""
        with self._lock:
            pattern_groups = defaultdict(list)
            for request in self._requests:
                pattern = request.url_pattern
                pattern_groups[pattern].append(request)
            return dict(pattern_groups)

    def get_requests_by_service(self) -> Dict[str, List[RequestMetrics]]:
        """Group stored requests by service name."""
        with self._lock:
            service_groups = defaultdict(list)
            for request in self._requests:
                service = request.service_name or "unknown"
                service_groups[service].append(request)
            return dict(service_groups)

    def get_requests_in_timeframe(self, minutes: int = 60) -> List[RequestMetrics]:
        """Get requests from the last N minutes."""
        cutoff_time = datetime.now() - timedelta(minutes=minutes)
        with self._lock:
            return [req for req in self._requests if req.timestamp >= cutoff_time]

    def calculate_percentiles(self, requests: Optional[List[RequestMetrics]] = None) -> Dict[str, float]:
        """Calculate duration percentiles for requests."""
        if requests is None:
            with self._lock:
                requests = list(self._requests)

        if not requests:
            return {"p50": 0.0, "p95": 0.0, "p99": 0.0}

        durations = [req.duration for req in requests]

        try:
            return {
                "p50": statistics.quantiles(durations, n=2)[0] if len(durations) > 1 else durations[0],
                "p95": statistics.quantiles(durations, n=20)[18] if len(durations) > 19 else max(durations),
                "p99": statistics.quantiles(durations, n=100)[98] if len(durations) > 99 else max(durations)
            }
        except statistics.StatisticsError:
            # Fallback for edge cases
            sorted_durations = sorted(durations)
            n = len(sorted_durations)
            return {
                "p50": sorted_durations[n // 2],
                "p95": sorted_durations[int(n * 0.95)] if n > 1 else sorted_durations[0],
                "p99": sorted_durations[int(n * 0.99)] if n > 1 else sorted_durations[0]
            }

    def calculate_request_rate(self, minutes: int = 60) -> float:
        """Calculate requests per second over the last N minutes."""
        recent_requests = self.get_requests_in_timeframe(minutes)
        if not recent_requests:
            return 0.0

        time_span_seconds = minutes * 60
        return len(recent_requests) / time_span_seconds

    def get_advanced_statistics(self) -> Dict:
        """Get comprehensive statistics with advanced analytics."""
        basic_stats = self.get_statistics()

        with self._lock:
            if not self._requests:
                return {**basic_stats, "percentiles": {"p50": 0.0, "p95": 0.0, "p99": 0.0}, "request_rate_per_second": 0.0}

            # Calculate percentiles
            percentiles = self.calculate_percentiles()

            # Calculate request rate (last hour)
            request_rate = self.calculate_request_rate(60)

            # Get recent requests (last 5 minutes)
            recent_requests = self.get_requests_in_timeframe(5)
            recent_percentiles = self.calculate_percentiles(recent_requests) if recent_requests else {"p50": 0.0, "p95": 0.0, "p99": 0.0}

            return {
                **basic_stats,
                "percentiles": percentiles,
                "recent_percentiles": recent_percentiles,
                "request_rate_per_second": request_rate,
                "recent_requests_count": len(recent_requests)
            }

    def export_to_json(self, include_requests: bool = True) -> str:
        """Export profiling data to JSON format."""
        with self._lock:
            export_data = {
                "export_timestamp": datetime.now().isoformat(),
                "statistics": self.get_advanced_statistics(),
                "settings": {
                    "max_stored_requests": self._max_stored_requests,
                    "slow_threshold": self._slow_threshold
                }
            }

            if include_requests:
                # Convert RequestMetrics to dict for JSON serialization
                requests_data = []
                for req in self._requests:
                    req_dict = asdict(req)
                    req_dict["timestamp"] = req.timestamp.isoformat()
                    requests_data.append(req_dict)
                export_data["requests"] = requests_data

            return json.dumps(export_data, indent=2)

    def export_to_csv(self) -> str:
        """Export request data to CSV format."""
        with self._lock:
            output = io.StringIO()
            writer = csv.writer(output)

            # Write header
            writer.writerow([
                "timestamp", "url", "method", "status_code", "duration",
                "success", "error_message", "service_name", "domain", "url_pattern"
            ])

            # Write data
            for req in self._requests:
                writer.writerow([
                    req.timestamp.isoformat(),
                    req.url,
                    req.method,
                    req.status_code,
                    req.duration,
                    req.success,
                    req.error_message or "",
                    req.service_name or "",
                    req.domain,
                    req.url_pattern
                ])

            return output.getvalue()

    def apply_retention_policy(self, max_age_hours: int = 24) -> int:
        """Remove requests older than specified hours. Returns number of removed requests."""
        cutoff_time = datetime.now() - timedelta(hours=max_age_hours)

        with self._lock:
            original_count = len(self._requests)

            # Filter out old requests
            filtered_requests = deque(
                (req for req in self._requests if req.timestamp >= cutoff_time),
                maxlen=self._max_stored_requests
            )

            removed_count = original_count - len(filtered_requests)
            self._requests = filtered_requests

            if removed_count > 0:
                logger.debug(f"Removed {removed_count} old requests from profiling data")

            return removed_count

    def get_memory_usage_estimate(self) -> Dict[str, Union[int, str]]:
        """Estimate memory usage of stored profiling data."""
        with self._lock:
            if not self._requests:
                return {"requests_count": 0, "estimated_bytes": 0, "estimated_mb": "0.00"}

            # Rough estimate: each request takes about 200-500 bytes
            # This includes the RequestMetrics object and string data
            avg_bytes_per_request = 350
            estimated_bytes = len(self._requests) * avg_bytes_per_request
            estimated_mb = estimated_bytes / (1024 * 1024)

            return {
                "requests_count": len(self._requests),
                "estimated_bytes": estimated_bytes,
                "estimated_mb": f"{estimated_mb:.2f}"
            }

    def _should_send_alert(self, alert_type: str) -> bool:
        """Check if enough time has passed since the last alert of this type."""
        settings = self._get_settings()
        if not settings.enable_alerts:
            return False

        cooldown_seconds = settings.alert_cooldown_minutes * 60
        last_alert_time = self._last_alert_times.get(alert_type)

        if last_alert_time is None:
            return True

        return (datetime.now() - last_alert_time).total_seconds() >= cooldown_seconds

    def _send_alert(self, alert_type: str, title: str, message: str) -> None:
        """Send an alert notification."""
        try:
            from program.utils.notifications import notify
            notify(title, message)
            self._last_alert_times[alert_type] = datetime.now()
            logger.info(f"Sent network profiling alert: {title}")
        except ImportError:
            logger.warning("Notifications not available for network profiling alerts")
        except Exception as e:
            logger.error(f"Failed to send network profiling alert: {e}")

    def _check_and_send_alerts(self, request: RequestMetrics) -> None:
        """Check if any alerts should be sent based on the current request."""
        settings = self._get_settings()
        if not settings.enable_alerts:
            return

        # Check for extremely slow requests
        if request.duration >= settings.alert_slow_request_threshold:
            if self._should_send_alert("slow_request"):
                title = "🐌 Extremely Slow Network Request Detected"
                message = (
                    f"**Request Details:**\n"
                    f"• URL: {request.url}\n"
                    f"• Method: {request.method}\n"
                    f"• Duration: {request.duration:.2f}s\n"
                    f"• Service: {request.service_name or 'Unknown'}\n"
                    f"• Status: {request.status_code}\n\n"
                    f"This request exceeded the alert threshold of {settings.alert_slow_request_threshold}s."
                )
                self._send_alert("slow_request", title, message)

        # Check error rate (only if we have enough requests)
        if self._total_requests >= 10:
            error_rate = (self._error_count / self._total_requests) * 100
            if error_rate >= settings.alert_error_rate_threshold:
                if self._should_send_alert("high_error_rate"):
                    title = "⚠️ High Network Error Rate Detected"
                    message = (
                        f"**Error Rate Alert:**\n"
                        f"• Current error rate: {error_rate:.1f}%\n"
                        f"• Total requests: {self._total_requests}\n"
                        f"• Failed requests: {self._error_count}\n"
                        f"• Alert threshold: {settings.alert_error_rate_threshold}%\n\n"
                        f"Recent error: {request.error_message or 'Unknown error'}"
                    )
                    self._send_alert("high_error_rate", title, message)

    def check_system_health(self) -> Dict[str, any]:
        """Check overall system health and send alerts if needed."""
        settings = self._get_settings()
        if not (self._enabled and settings.enabled and settings.enable_alerts):
            return {"health_check_enabled": False}

        with self._lock:
            if self._total_requests < 10:
                return {"health_check_enabled": True, "status": "insufficient_data"}

            # Calculate recent metrics (last hour)
            recent_requests = self.get_requests_in_timeframe(60)
            if not recent_requests:
                return {"health_check_enabled": True, "status": "no_recent_requests"}

            recent_errors = sum(1 for req in recent_requests if not req.success)
            recent_error_rate = (recent_errors / len(recent_requests)) * 100

            recent_slow = sum(1 for req in recent_requests if req.is_slow(settings.slow_request_threshold))
            recent_slow_rate = (recent_slow / len(recent_requests)) * 100

            avg_duration = sum(req.duration for req in recent_requests) / len(recent_requests)

            health_status = {
                "health_check_enabled": True,
                "status": "healthy",
                "recent_requests": len(recent_requests),
                "recent_error_rate": recent_error_rate,
                "recent_slow_rate": recent_slow_rate,
                "average_duration": avg_duration
            }

            # Check for sustained high error rate
            if recent_error_rate >= settings.alert_error_rate_threshold:
                if self._should_send_alert("sustained_high_error_rate"):
                    title = "🚨 Sustained High Network Error Rate"
                    message = (
                        f"**System Health Alert:**\n"
                        f"• Recent error rate (1h): {recent_error_rate:.1f}%\n"
                        f"• Recent requests: {len(recent_requests)}\n"
                        f"• Failed requests: {recent_errors}\n"
                        f"• Average duration: {avg_duration:.2f}s\n\n"
                        f"The system has been experiencing sustained network issues."
                    )
                    self._send_alert("sustained_high_error_rate", title, message)
                    health_status["status"] = "unhealthy"

            return health_status

    def get_production_metrics(self) -> Dict[str, any]:
        """Get production monitoring metrics."""
        with self._lock:
            avg_overhead = 0.0
            if self._performance_metrics["profiling_calls_total"] > 0:
                avg_overhead = (self._performance_metrics["profiling_overhead_total"] /
                               self._performance_metrics["profiling_calls_total"])

            return {
                "feature_flag_enabled": self._is_feature_enabled(),
                "consecutive_errors": self._error_count_consecutive,
                "last_error_time": self._last_error_time.isoformat() if self._last_error_time else None,
                "performance_metrics": {
                    "average_overhead_ms": avg_overhead * 1000,
                    "total_profiling_calls": self._performance_metrics["profiling_calls_total"],
                    "memory_cleanups": self._performance_metrics["memory_cleanups"],
                    "auto_disables": self._performance_metrics["auto_disables"]
                },
                "memory_usage": self.get_memory_usage_estimate(),
                "settings_status": {
                    "graceful_degradation": self._get_settings().graceful_degradation,
                    "auto_disable_on_error": self._get_settings().auto_disable_on_error,
                    "performance_monitoring": self._get_settings().performance_monitoring,
                    "max_memory_mb": self._get_settings().max_memory_mb
                }
            }

    def reset_error_state(self) -> None:
        """Reset error state for manual recovery."""
        with self._lock:
            self._error_count_consecutive = 0
            self._last_error_time = None
            logger.info("Network profiling error state reset")

    def force_memory_cleanup(self) -> Dict[str, int]:
        """Force memory cleanup and return cleanup statistics."""
        with self._lock:
            original_count = len(self._requests)

            # Remove oldest 50% of requests
            remove_count = original_count // 2
            for _ in range(remove_count):
                if self._requests:
                    self._requests.popleft()

            self._performance_metrics["memory_cleanups"] += 1

            cleanup_stats = {
                "original_count": original_count,
                "removed_count": remove_count,
                "remaining_count": len(self._requests)
            }

            logger.info(f"Forced memory cleanup: removed {remove_count} requests")
            return cleanup_stats


# Global network profiler instance
network_profiler = NetworkProfiler()
