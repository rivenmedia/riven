"""Debug router for network profiling and system diagnostics."""

from typing import Dict, List, Optional, Union, Any
from datetime import datetime

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import PlainTextResponse
from loguru import logger
from pydantic import BaseModel, Field

from ..models.shared import MessageResponse

router = APIRouter(
    prefix="/debug",
    tags=["debug"],
    responses={404: {"description": "Not found"}},
)


class RequestMetricsResponse(BaseModel):
    """Response model for individual request metrics."""
    url: str
    method: str
    status_code: Optional[int]
    duration: float = Field(description="Request duration in seconds")
    timestamp: datetime
    success: bool
    error_message: Optional[str] = None
    service_name: Optional[str] = None
    domain: str


class NetworkStatsResponse(BaseModel):
    """Response model for network profiling statistics."""
    enabled: bool
    total_requests: int
    average_duration: float = Field(description="Average request duration in seconds")
    slow_requests_count: int
    error_count: int
    slow_requests_percentage: float
    error_percentage: float
    stored_requests: int
    max_stored_requests: int
    slow_threshold: float = Field(description="Threshold in seconds for slow requests")


class ProfilingStatusResponse(BaseModel):
    """Response model for profiling status operations."""
    enabled: bool
    message: str


class SlowRequestsResponse(BaseModel):
    """Response model for slow requests."""
    slow_requests: List[RequestMetricsResponse]
    total_count: int
    threshold: float = Field(description="Current slow request threshold in seconds")


class DomainStatsResponse(BaseModel):
    """Response model for domain-grouped statistics."""
    domain_stats: Dict[str, Dict[str, Any]]
    total_domains: int


class AdvancedStatsResponse(BaseModel):
    """Response model for advanced analytics."""
    enabled: bool
    total_requests: int
    average_duration: float
    percentiles: Dict[str, float] = Field(description="Duration percentiles (p50, p95, p99)")
    recent_percentiles: Dict[str, float] = Field(description="Recent duration percentiles (last 5 minutes)")
    request_rate_per_second: float = Field(description="Requests per second over last hour")
    recent_requests_count: int = Field(description="Number of requests in last 5 minutes")
    slow_requests_count: int
    error_count: int
    slow_requests_percentage: float
    error_percentage: float


class PatternStatsResponse(BaseModel):
    """Response model for URL pattern statistics."""
    pattern_stats: Dict[str, Dict[str, Any]]
    total_patterns: int


class ServiceStatsResponse(BaseModel):
    """Response model for service-grouped statistics."""
    service_stats: Dict[str, Dict[str, Any]]
    total_services: int


class MemoryUsageResponse(BaseModel):
    """Response model for memory usage information."""
    requests_count: int
    estimated_bytes: int
    estimated_mb: str


class RetentionPolicyResponse(BaseModel):
    """Response model for retention policy operations."""
    removed_count: int
    remaining_count: int
    message: str


class HealthCheckResponse(BaseModel):
    """Response model for network health check."""
    health_check_enabled: bool
    status: Optional[str] = None
    recent_requests: Optional[int] = None
    recent_error_rate: Optional[float] = None
    recent_slow_rate: Optional[float] = None
    average_duration: Optional[float] = None


class AlertStatusResponse(BaseModel):
    """Response model for alert status."""
    alerts_enabled: bool
    last_alerts: Dict[str, Optional[str]] = Field(description="Last alert times by type")
    alert_settings: Dict[str, Any]


class ProductionMetricsResponse(BaseModel):
    """Response model for production monitoring metrics."""
    feature_flag_enabled: bool
    consecutive_errors: int
    last_error_time: Optional[str]
    performance_metrics: Dict[str, Any]
    memory_usage: Dict[str, Any]
    settings_status: Dict[str, Any]


class CleanupStatsResponse(BaseModel):
    """Response model for memory cleanup operations."""
    original_count: int
    removed_count: int
    remaining_count: int


@router.get("/network-stats", operation_id="get_network_stats")
async def get_network_stats() -> NetworkStatsResponse:
    """Get comprehensive network profiling statistics."""
    try:
        from program.utils.network_profiler import network_profiler
        stats = network_profiler.get_statistics()
        return NetworkStatsResponse(**stats)
    except ImportError:
        raise HTTPException(status_code=503, detail="Network profiling not available")
    except Exception as e:
        logger.error(f"Error getting network stats: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve network statistics")


@router.get("/network-profiling/status", operation_id="get_profiling_status")
async def get_profiling_status() -> ProfilingStatusResponse:
    """Get current network profiling status."""
    try:
        from program.utils.network_profiler import network_profiler
        enabled = network_profiler.enabled
        return ProfilingStatusResponse(
            enabled=enabled,
            message=f"Network profiling is {'enabled' if enabled else 'disabled'}"
        )
    except ImportError:
        raise HTTPException(status_code=503, detail="Network profiling not available")


@router.post("/network-profiling/enable", operation_id="enable_profiling")
async def enable_profiling() -> ProfilingStatusResponse:
    """Enable network profiling."""
    try:
        from program.utils.network_profiler import network_profiler
        network_profiler.enable()
        return ProfilingStatusResponse(
            enabled=True,
            message="Network profiling enabled successfully"
        )
    except ImportError:
        raise HTTPException(status_code=503, detail="Network profiling not available")
    except Exception as e:
        logger.error(f"Error enabling profiling: {e}")
        raise HTTPException(status_code=500, detail="Failed to enable network profiling")


@router.post("/network-profiling/disable", operation_id="disable_profiling")
async def disable_profiling() -> ProfilingStatusResponse:
    """Disable network profiling."""
    try:
        from program.utils.network_profiler import network_profiler
        network_profiler.disable()
        return ProfilingStatusResponse(
            enabled=False,
            message="Network profiling disabled successfully"
        )
    except ImportError:
        raise HTTPException(status_code=503, detail="Network profiling not available")
    except Exception as e:
        logger.error(f"Error disabling profiling: {e}")
        raise HTTPException(status_code=500, detail="Failed to disable network profiling")


@router.get("/network-profiling/summary", operation_id="get_profiling_summary")
async def get_profiling_summary() -> MessageResponse:
    """Get a text summary of network profiling statistics."""
    try:
        from program.utils.network_profiler import network_profiler
        stats = network_profiler.get_statistics()
        
        if not stats["enabled"]:
            return {"message": "Network profiling is disabled"}
        
        if stats["total_requests"] == 0:
            return {"message": "No requests recorded yet"}
        
        summary = (
            f"Network Profiling Summary:\n"
            f"• Total requests: {stats['total_requests']}\n"
            f"• Average duration: {stats['average_duration']:.2f}s\n"
            f"• Slow requests: {stats['slow_requests_count']} ({stats['slow_requests_percentage']:.1f}%)\n"
            f"• Errors: {stats['error_count']} ({stats['error_percentage']:.1f}%)\n"
            f"• Stored requests: {stats['stored_requests']}/{stats['max_stored_requests']}\n"
            f"• Slow threshold: {stats['slow_threshold']}s"
        )
        
        return {"message": summary}
    except ImportError:
        raise HTTPException(status_code=503, detail="Network profiling not available")
    except Exception as e:
        logger.error(f"Error getting profiling summary: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve profiling summary")


@router.get("/network-profiling/slow-requests", operation_id="get_slow_requests")
async def get_slow_requests(limit: int = 50) -> SlowRequestsResponse:
    """Get recent slow requests."""
    try:
        from program.utils.network_profiler import network_profiler
        
        if limit < 1 or limit > 1000:
            raise HTTPException(status_code=400, detail="Limit must be between 1 and 1000")
        
        slow_requests = network_profiler.get_slow_requests(limit)
        stats = network_profiler.get_statistics()
        
        # Convert to response format
        slow_requests_response = []
        for req in slow_requests:
            slow_requests_response.append(RequestMetricsResponse(
                url=req.url,
                method=req.method,
                status_code=req.status_code,
                duration=req.duration,
                timestamp=req.timestamp,
                success=req.success,
                error_message=req.error_message,
                service_name=req.service_name,
                domain=req.domain
            ))
        
        return SlowRequestsResponse(
            slow_requests=slow_requests_response,
            total_count=len(slow_requests_response),
            threshold=stats["slow_threshold"]
        )
    except ImportError:
        raise HTTPException(status_code=503, detail="Network profiling not available")
    except Exception as e:
        logger.error(f"Error getting slow requests: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve slow requests")


@router.get("/network-profiling/domains", operation_id="get_domain_stats")
async def get_domain_stats() -> DomainStatsResponse:
    """Get request statistics grouped by domain."""
    try:
        from program.utils.network_profiler import network_profiler
        
        domain_groups = network_profiler.get_requests_by_domain()
        domain_stats = {}
        
        for domain, requests in domain_groups.items():
            total_requests = len(requests)
            total_duration = sum(req.duration for req in requests)
            slow_requests = sum(1 for req in requests if req.is_slow(network_profiler._get_settings().slow_request_threshold))
            error_requests = sum(1 for req in requests if not req.success)
            
            domain_stats[domain] = {
                "total_requests": total_requests,
                "average_duration": total_duration / total_requests if total_requests > 0 else 0,
                "slow_requests": slow_requests,
                "error_requests": error_requests,
                "slow_percentage": (slow_requests / total_requests * 100) if total_requests > 0 else 0,
                "error_percentage": (error_requests / total_requests * 100) if total_requests > 0 else 0
            }
        
        return DomainStatsResponse(
            domain_stats=domain_stats,
            total_domains=len(domain_stats)
        )
    except ImportError:
        raise HTTPException(status_code=503, detail="Network profiling not available")
    except Exception as e:
        logger.error(f"Error getting domain stats: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve domain statistics")


@router.post("/network-profiling/clear", operation_id="clear_profiling_data")
async def clear_profiling_data() -> MessageResponse:
    """Clear all stored network profiling data."""
    try:
        from program.utils.network_profiler import network_profiler
        network_profiler.clear_data()
        return {"message": "Network profiling data cleared successfully"}
    except ImportError:
        raise HTTPException(status_code=503, detail="Network profiling not available")
    except Exception as e:
        logger.error(f"Error clearing profiling data: {e}")
        raise HTTPException(status_code=500, detail="Failed to clear profiling data")


@router.get("/network-profiling/advanced-stats", operation_id="get_advanced_stats")
async def get_advanced_stats() -> AdvancedStatsResponse:
    """Get advanced network profiling statistics with percentiles and rates."""
    try:
        from program.utils.network_profiler import network_profiler
        stats = network_profiler.get_advanced_statistics()
        return AdvancedStatsResponse(**stats)
    except ImportError:
        raise HTTPException(status_code=503, detail="Network profiling not available")
    except Exception as e:
        logger.error(f"Error getting advanced stats: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve advanced statistics")


@router.get("/network-profiling/patterns", operation_id="get_pattern_stats")
async def get_pattern_stats() -> PatternStatsResponse:
    """Get request statistics grouped by URL pattern."""
    try:
        from program.utils.network_profiler import network_profiler

        pattern_groups = network_profiler.get_requests_by_pattern()
        pattern_stats = {}
        settings = network_profiler._get_settings()

        for pattern, requests in pattern_groups.items():
            total_requests = len(requests)
            total_duration = sum(req.duration for req in requests)
            slow_requests = sum(1 for req in requests if req.is_slow(settings.slow_request_threshold))
            error_requests = sum(1 for req in requests if not req.success)

            # Calculate percentiles for this pattern
            percentiles = network_profiler.calculate_percentiles(requests)

            pattern_stats[pattern] = {
                "total_requests": total_requests,
                "average_duration": total_duration / total_requests if total_requests > 0 else 0,
                "slow_requests": slow_requests,
                "error_requests": error_requests,
                "slow_percentage": (slow_requests / total_requests * 100) if total_requests > 0 else 0,
                "error_percentage": (error_requests / total_requests * 100) if total_requests > 0 else 0,
                "percentiles": percentiles
            }

        return PatternStatsResponse(
            pattern_stats=pattern_stats,
            total_patterns=len(pattern_stats)
        )
    except ImportError:
        raise HTTPException(status_code=503, detail="Network profiling not available")
    except Exception as e:
        logger.error(f"Error getting pattern stats: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve pattern statistics")


@router.get("/network-profiling/services", operation_id="get_service_stats")
async def get_service_stats() -> ServiceStatsResponse:
    """Get request statistics grouped by service."""
    try:
        from program.utils.network_profiler import network_profiler

        service_groups = network_profiler.get_requests_by_service()
        service_stats = {}
        settings = network_profiler._get_settings()

        for service, requests in service_groups.items():
            total_requests = len(requests)
            total_duration = sum(req.duration for req in requests)
            slow_requests = sum(1 for req in requests if req.is_slow(settings.slow_request_threshold))
            error_requests = sum(1 for req in requests if not req.success)

            # Calculate percentiles for this service
            percentiles = network_profiler.calculate_percentiles(requests)

            service_stats[service] = {
                "total_requests": total_requests,
                "average_duration": total_duration / total_requests if total_requests > 0 else 0,
                "slow_requests": slow_requests,
                "error_requests": error_requests,
                "slow_percentage": (slow_requests / total_requests * 100) if total_requests > 0 else 0,
                "error_percentage": (error_requests / total_requests * 100) if total_requests > 0 else 0,
                "percentiles": percentiles
            }

        return ServiceStatsResponse(
            service_stats=service_stats,
            total_services=len(service_stats)
        )
    except ImportError:
        raise HTTPException(status_code=503, detail="Network profiling not available")
    except Exception as e:
        logger.error(f"Error getting service stats: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve service statistics")


@router.get("/network-profiling/export/json", operation_id="export_json")
async def export_json(include_requests: bool = True) -> Response:
    """Export profiling data as JSON."""
    try:
        from program.utils.network_profiler import network_profiler

        json_data = network_profiler.export_to_json(include_requests=include_requests)

        return Response(
            content=json_data,
            media_type="application/json",
            headers={"Content-Disposition": f"attachment; filename=network_profiling_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"}
        )
    except ImportError:
        raise HTTPException(status_code=503, detail="Network profiling not available")
    except Exception as e:
        logger.error(f"Error exporting JSON: {e}")
        raise HTTPException(status_code=500, detail="Failed to export JSON data")


@router.get("/network-profiling/export/csv", operation_id="export_csv")
async def export_csv() -> PlainTextResponse:
    """Export profiling data as CSV."""
    try:
        from program.utils.network_profiler import network_profiler

        csv_data = network_profiler.export_to_csv()

        return PlainTextResponse(
            content=csv_data,
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename=network_profiling_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"}
        )
    except ImportError:
        raise HTTPException(status_code=503, detail="Network profiling not available")
    except Exception as e:
        logger.error(f"Error exporting CSV: {e}")
        raise HTTPException(status_code=500, detail="Failed to export CSV data")


@router.get("/network-profiling/memory-usage", operation_id="get_memory_usage")
async def get_memory_usage() -> MemoryUsageResponse:
    """Get memory usage information for profiling data."""
    try:
        from program.utils.network_profiler import network_profiler

        usage = network_profiler.get_memory_usage_estimate()
        return MemoryUsageResponse(**usage)
    except ImportError:
        raise HTTPException(status_code=503, detail="Network profiling not available")
    except Exception as e:
        logger.error(f"Error getting memory usage: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve memory usage")


@router.post("/network-profiling/retention-policy", operation_id="apply_retention_policy")
async def apply_retention_policy(max_age_hours: int = 24) -> RetentionPolicyResponse:
    """Apply retention policy to remove old profiling data."""
    try:
        from program.utils.network_profiler import network_profiler

        if max_age_hours < 1 or max_age_hours > 8760:  # 1 hour to 1 year
            raise HTTPException(status_code=400, detail="max_age_hours must be between 1 and 8760")

        removed_count = network_profiler.apply_retention_policy(max_age_hours)
        remaining_count = len(network_profiler._requests)

        return RetentionPolicyResponse(
            removed_count=removed_count,
            remaining_count=remaining_count,
            message=f"Removed {removed_count} requests older than {max_age_hours} hours"
        )
    except ImportError:
        raise HTTPException(status_code=503, detail="Network profiling not available")
    except Exception as e:
        logger.error(f"Error applying retention policy: {e}")
        raise HTTPException(status_code=500, detail="Failed to apply retention policy")


@router.get("/network-profiling/health", operation_id="get_network_health")
async def get_network_health() -> HealthCheckResponse:
    """Get network health status and metrics."""
    try:
        from program.utils.network_profiler import network_profiler

        health_data = network_profiler.check_system_health()
        return HealthCheckResponse(**health_data)
    except ImportError:
        raise HTTPException(status_code=503, detail="Network profiling not available")
    except Exception as e:
        logger.error(f"Error getting network health: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve network health")


@router.get("/network-profiling/alerts/status", operation_id="get_alert_status")
async def get_alert_status() -> AlertStatusResponse:
    """Get current alert status and configuration."""
    try:
        from program.utils.network_profiler import network_profiler
        settings = network_profiler._get_settings()

        # Format last alert times
        last_alerts = {}
        for alert_type, timestamp in network_profiler._last_alert_times.items():
            last_alerts[alert_type] = timestamp.isoformat() if timestamp else None

        alert_settings = {
            "enable_alerts": settings.enable_alerts,
            "alert_slow_request_threshold": settings.alert_slow_request_threshold,
            "alert_error_rate_threshold": settings.alert_error_rate_threshold,
            "alert_cooldown_minutes": settings.alert_cooldown_minutes
        }

        return AlertStatusResponse(
            alerts_enabled=settings.enable_alerts,
            last_alerts=last_alerts,
            alert_settings=alert_settings
        )
    except ImportError:
        raise HTTPException(status_code=503, detail="Network profiling not available")
    except Exception as e:
        logger.error(f"Error getting alert status: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve alert status")


@router.post("/network-profiling/alerts/test", operation_id="test_alert")
async def test_alert() -> MessageResponse:
    """Send a test alert to verify notification configuration."""
    try:
        from program.utils.network_profiler import network_profiler

        title = "🧪 Network Profiling Test Alert"
        message = (
            f"**Test Alert from Riven Network Profiling**\n\n"
            f"This is a test alert to verify that network profiling notifications are working correctly.\n\n"
            f"• Timestamp: {datetime.now().isoformat()}\n"
            f"• Source: Network Profiling Debug Endpoint\n"
            f"• Status: Test Successful ✅"
        )

        network_profiler._send_alert("test", title, message)
        return {"message": "Test alert sent successfully"}
    except ImportError:
        raise HTTPException(status_code=503, detail="Network profiling not available")
    except Exception as e:
        logger.error(f"Error sending test alert: {e}")
        raise HTTPException(status_code=500, detail="Failed to send test alert")


@router.get("/network-profiling/production-metrics", operation_id="get_production_metrics")
async def get_production_metrics() -> ProductionMetricsResponse:
    """Get production monitoring metrics including performance and error tracking."""
    try:
        from program.utils.network_profiler import network_profiler

        metrics = network_profiler.get_production_metrics()
        return ProductionMetricsResponse(**metrics)
    except ImportError:
        raise HTTPException(status_code=503, detail="Network profiling not available")
    except Exception as e:
        logger.error(f"Error getting production metrics: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve production metrics")


@router.post("/network-profiling/reset-errors", operation_id="reset_error_state")
async def reset_error_state() -> MessageResponse:
    """Reset error state for manual recovery."""
    try:
        from program.utils.network_profiler import network_profiler

        network_profiler.reset_error_state()
        return {"message": "Error state reset successfully"}
    except ImportError:
        raise HTTPException(status_code=503, detail="Network profiling not available")
    except Exception as e:
        logger.error(f"Error resetting error state: {e}")
        raise HTTPException(status_code=500, detail="Failed to reset error state")


@router.post("/network-profiling/force-cleanup", operation_id="force_memory_cleanup")
async def force_memory_cleanup() -> CleanupStatsResponse:
    """Force memory cleanup and return cleanup statistics."""
    try:
        from program.utils.network_profiler import network_profiler

        cleanup_stats = network_profiler.force_memory_cleanup()
        return CleanupStatsResponse(**cleanup_stats)
    except ImportError:
        raise HTTPException(status_code=503, detail="Network profiling not available")
    except Exception as e:
        logger.error(f"Error forcing memory cleanup: {e}")
        raise HTTPException(status_code=500, detail="Failed to force memory cleanup")


@router.get("/network-profiling/feature-flag", operation_id="get_feature_flag_status")
async def get_feature_flag_status() -> MessageResponse:
    """Get current feature flag status."""
    try:
        from program.utils.network_profiler import network_profiler

        enabled = network_profiler._is_feature_enabled()
        settings = network_profiler._get_settings()

        status = {
            "feature_flag_enabled": settings.feature_flag_enabled,
            "profiler_enabled": network_profiler.enabled,
            "settings_enabled": settings.enabled,
            "overall_enabled": enabled
        }

        return {"message": f"Feature flag status: {status}"}
    except ImportError:
        raise HTTPException(status_code=503, detail="Network profiling not available")
    except Exception as e:
        logger.error(f"Error getting feature flag status: {e}")
        raise HTTPException(status_code=500, detail="Failed to get feature flag status")
