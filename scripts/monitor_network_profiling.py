#!/usr/bin/env python3
"""
Production monitoring script for Riven Network Profiling.

This script monitors the health and performance of the network profiling system
and can be used for automated monitoring and alerting.
"""

import argparse
import json
import sys
import time
from datetime import datetime
from typing import Dict, Any

import requests


class NetworkProfilingMonitor:
    """Monitor for network profiling system."""
    
    def __init__(self, base_url: str, api_key: str):
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key
        self.headers = {"Authorization": f"Bearer {api_key}"}
    
    def _make_request(self, endpoint: str) -> Dict[str, Any]:
        """Make API request with error handling."""
        url = f"{self.base_url}/api/v1/debug/{endpoint}"
        
        try:
            response = requests.get(url, headers=self.headers, timeout=10)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"ERROR: Failed to fetch {endpoint}: {e}")
            return {}
    
    def check_health(self) -> Dict[str, Any]:
        """Check overall health of network profiling."""
        health_data = {}
        
        # Get basic stats
        stats = self._make_request("network-stats")
        if stats:
            health_data["basic_stats"] = stats
        
        # Get production metrics
        prod_metrics = self._make_request("network-profiling/production-metrics")
        if prod_metrics:
            health_data["production_metrics"] = prod_metrics
        
        # Get health status
        health = self._make_request("network-profiling/health")
        if health:
            health_data["health_status"] = health
        
        return health_data
    
    def analyze_health(self, health_data: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze health data and return status."""
        analysis = {
            "overall_status": "healthy",
            "warnings": [],
            "errors": [],
            "recommendations": []
        }
        
        # Check if profiling is enabled
        basic_stats = health_data.get("basic_stats", {})
        if not basic_stats.get("enabled", False):
            analysis["warnings"].append("Network profiling is disabled")
        
        # Check error rate
        error_percentage = basic_stats.get("error_percentage", 0)
        if error_percentage > 10:
            analysis["errors"].append(f"High error rate: {error_percentage:.1f}%")
            analysis["overall_status"] = "unhealthy"
        elif error_percentage > 5:
            analysis["warnings"].append(f"Elevated error rate: {error_percentage:.1f}%")
            if analysis["overall_status"] == "healthy":
                analysis["overall_status"] = "warning"
        
        # Check consecutive errors
        prod_metrics = health_data.get("production_metrics", {})
        consecutive_errors = prod_metrics.get("consecutive_errors", 0)
        if consecutive_errors > 3:
            analysis["errors"].append(f"Consecutive errors: {consecutive_errors}")
            analysis["overall_status"] = "unhealthy"
        elif consecutive_errors > 0:
            analysis["warnings"].append(f"Recent errors: {consecutive_errors}")
        
        # Check memory usage
        memory_usage = prod_metrics.get("memory_usage", {})
        memory_mb = float(memory_usage.get("estimated_mb", "0"))
        if memory_mb > 100:
            analysis["errors"].append(f"High memory usage: {memory_mb:.1f}MB")
            analysis["overall_status"] = "unhealthy"
        elif memory_mb > 50:
            analysis["warnings"].append(f"Elevated memory usage: {memory_mb:.1f}MB")
            if analysis["overall_status"] == "healthy":
                analysis["overall_status"] = "warning"
        
        # Check performance overhead
        perf_metrics = prod_metrics.get("performance_metrics", {})
        avg_overhead = perf_metrics.get("average_overhead_ms", 0)
        if avg_overhead > 5:
            analysis["warnings"].append(f"High profiling overhead: {avg_overhead:.2f}ms")
            if analysis["overall_status"] == "healthy":
                analysis["overall_status"] = "warning"
        
        # Check auto-disables
        auto_disables = perf_metrics.get("auto_disables", 0)
        if auto_disables > 0:
            analysis["errors"].append(f"Auto-disables occurred: {auto_disables}")
            analysis["overall_status"] = "unhealthy"
        
        # Generate recommendations
        if error_percentage > 5:
            analysis["recommendations"].append("Investigate high error rate causes")
        
        if memory_mb > 50:
            analysis["recommendations"].append("Consider reducing max_stored_requests or applying retention policy")
        
        if consecutive_errors > 0:
            analysis["recommendations"].append("Check logs for error details and consider resetting error state")
        
        return analysis
    
    def print_status(self, health_data: Dict[str, Any], analysis: Dict[str, Any]) -> None:
        """Print formatted status report."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        status = analysis["overall_status"].upper()
        
        print(f"=== Network Profiling Status Report - {timestamp} ===")
        print(f"Overall Status: {status}")
        print()
        
        # Basic statistics
        basic_stats = health_data.get("basic_stats", {})
        if basic_stats:
            print("Basic Statistics:")
            print(f"  Enabled: {basic_stats.get('enabled', False)}")
            print(f"  Total Requests: {basic_stats.get('total_requests', 0):,}")
            print(f"  Average Duration: {basic_stats.get('average_duration', 0):.2f}s")
            print(f"  Error Rate: {basic_stats.get('error_percentage', 0):.1f}%")
            print(f"  Slow Requests: {basic_stats.get('slow_requests_percentage', 0):.1f}%")
            print()
        
        # Production metrics
        prod_metrics = health_data.get("production_metrics", {})
        if prod_metrics:
            print("Production Metrics:")
            print(f"  Feature Flag: {prod_metrics.get('feature_flag_enabled', False)}")
            print(f"  Consecutive Errors: {prod_metrics.get('consecutive_errors', 0)}")
            
            perf_metrics = prod_metrics.get("performance_metrics", {})
            print(f"  Average Overhead: {perf_metrics.get('average_overhead_ms', 0):.2f}ms")
            print(f"  Memory Cleanups: {perf_metrics.get('memory_cleanups', 0)}")
            print(f"  Auto Disables: {perf_metrics.get('auto_disables', 0)}")
            
            memory_usage = prod_metrics.get("memory_usage", {})
            print(f"  Memory Usage: {memory_usage.get('estimated_mb', '0')}MB")
            print()
        
        # Warnings and errors
        if analysis["errors"]:
            print("ERRORS:")
            for error in analysis["errors"]:
                print(f"  ❌ {error}")
            print()
        
        if analysis["warnings"]:
            print("WARNINGS:")
            for warning in analysis["warnings"]:
                print(f"  ⚠️  {warning}")
            print()
        
        if analysis["recommendations"]:
            print("RECOMMENDATIONS:")
            for rec in analysis["recommendations"]:
                print(f"  💡 {rec}")
            print()
    
    def monitor_continuous(self, interval: int = 60) -> None:
        """Run continuous monitoring."""
        print(f"Starting continuous monitoring (interval: {interval}s)")
        print("Press Ctrl+C to stop")
        print()
        
        try:
            while True:
                health_data = self.check_health()
                analysis = self.analyze_health(health_data)
                self.print_status(health_data, analysis)
                
                # Exit with error code if unhealthy
                if analysis["overall_status"] == "unhealthy":
                    print("❌ System is unhealthy!")
                
                print("-" * 60)
                time.sleep(interval)
                
        except KeyboardInterrupt:
            print("\nMonitoring stopped.")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Monitor Riven Network Profiling")
    parser.add_argument("--url", default="http://localhost:8080", help="Riven base URL")
    parser.add_argument("--api-key", required=True, help="API key for authentication")
    parser.add_argument("--continuous", action="store_true", help="Run continuous monitoring")
    parser.add_argument("--interval", type=int, default=60, help="Monitoring interval in seconds")
    parser.add_argument("--json", action="store_true", help="Output in JSON format")
    
    args = parser.parse_args()
    
    monitor = NetworkProfilingMonitor(args.url, args.api_key)
    
    if args.continuous:
        monitor.monitor_continuous(args.interval)
    else:
        # Single check
        health_data = monitor.check_health()
        analysis = monitor.analyze_health(health_data)
        
        if args.json:
            output = {
                "timestamp": datetime.now().isoformat(),
                "health_data": health_data,
                "analysis": analysis
            }
            print(json.dumps(output, indent=2))
        else:
            monitor.print_status(health_data, analysis)
        
        # Exit with appropriate code
        if analysis["overall_status"] == "unhealthy":
            sys.exit(1)
        elif analysis["overall_status"] == "warning":
            sys.exit(2)
        else:
            sys.exit(0)


if __name__ == "__main__":
    main()
