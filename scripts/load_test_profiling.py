#!/usr/bin/env python3
"""
Load testing script for Network Profiling performance validation.

This script simulates realistic HTTP request patterns to test the performance
impact of network profiling under load.
"""

import argparse
import asyncio
import aiohttp
import time
import statistics
from datetime import datetime
from typing import List, Dict, Any
import json


class LoadTester:
    """Load tester for network profiling performance validation."""
    
    def __init__(self, base_url: str, api_key: str):
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key
        self.headers = {"Authorization": f"Bearer {api_key}"}
        self.results = []
    
    async def make_request(self, session: aiohttp.ClientSession, endpoint: str) -> Dict[str, Any]:
        """Make a single HTTP request and measure timing."""
        url = f"{self.base_url}/api/v1/{endpoint}"
        start_time = time.perf_counter()
        
        try:
            async with session.get(url, headers=self.headers) as response:
                await response.text()  # Read response body
                end_time = time.perf_counter()
                
                return {
                    "endpoint": endpoint,
                    "status_code": response.status,
                    "duration": end_time - start_time,
                    "success": response.status < 400,
                    "timestamp": datetime.now().isoformat()
                }
        except Exception as e:
            end_time = time.perf_counter()
            return {
                "endpoint": endpoint,
                "status_code": 0,
                "duration": end_time - start_time,
                "success": False,
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }
    
    async def run_load_test(self, duration: int, concurrent: int, endpoints: List[str]) -> List[Dict[str, Any]]:
        """Run load test for specified duration with concurrent requests."""
        print(f"Starting load test: {duration}s duration, {concurrent} concurrent requests")
        print(f"Target endpoints: {endpoints}")
        print()
        
        results = []
        start_time = time.time()
        end_time = start_time + duration
        
        async with aiohttp.ClientSession() as session:
            while time.time() < end_time:
                # Create batch of concurrent requests
                tasks = []
                for i in range(concurrent):
                    endpoint = endpoints[i % len(endpoints)]
                    task = self.make_request(session, endpoint)
                    tasks.append(task)
                
                # Execute batch
                batch_results = await asyncio.gather(*tasks, return_exceptions=True)
                
                # Process results
                for result in batch_results:
                    if isinstance(result, dict):
                        results.append(result)
                
                # Small delay to prevent overwhelming the server
                await asyncio.sleep(0.1)
        
        return results
    
    def analyze_results(self, results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Analyze load test results."""
        if not results:
            return {"error": "No results to analyze"}
        
        # Basic statistics
        total_requests = len(results)
        successful_requests = sum(1 for r in results if r["success"])
        failed_requests = total_requests - successful_requests
        
        # Duration statistics
        durations = [r["duration"] for r in results if r["success"]]
        if durations:
            avg_duration = statistics.mean(durations)
            median_duration = statistics.median(durations)
            p95_duration = statistics.quantiles(durations, n=20)[18] if len(durations) > 19 else max(durations)
            p99_duration = statistics.quantiles(durations, n=100)[98] if len(durations) > 99 else max(durations)
            min_duration = min(durations)
            max_duration = max(durations)
        else:
            avg_duration = median_duration = p95_duration = p99_duration = min_duration = max_duration = 0
        
        # Error analysis
        error_rate = (failed_requests / total_requests) * 100 if total_requests > 0 else 0
        
        # Requests per second
        if results:
            test_duration = (datetime.fromisoformat(results[-1]["timestamp"]) - 
                           datetime.fromisoformat(results[0]["timestamp"])).total_seconds()
            rps = total_requests / test_duration if test_duration > 0 else 0
        else:
            rps = 0
        
        return {
            "summary": {
                "total_requests": total_requests,
                "successful_requests": successful_requests,
                "failed_requests": failed_requests,
                "error_rate_percent": error_rate,
                "requests_per_second": rps
            },
            "performance": {
                "average_duration_ms": avg_duration * 1000,
                "median_duration_ms": median_duration * 1000,
                "p95_duration_ms": p95_duration * 1000,
                "p99_duration_ms": p99_duration * 1000,
                "min_duration_ms": min_duration * 1000,
                "max_duration_ms": max_duration * 1000
            }
        }
    
    async def test_profiling_impact(self, duration: int, concurrent: int, endpoints: List[str]) -> Dict[str, Any]:
        """Test performance impact of profiling by comparing enabled vs disabled."""
        print("=== Testing Network Profiling Performance Impact ===")
        print()
        
        # Test with profiling disabled
        print("Phase 1: Testing with profiling DISABLED")
        await self.disable_profiling()
        await asyncio.sleep(2)  # Allow time for change to take effect
        
        results_disabled = await self.run_load_test(duration, concurrent, endpoints)
        analysis_disabled = self.analyze_results(results_disabled)
        
        print(f"Disabled - Avg: {analysis_disabled['performance']['average_duration_ms']:.2f}ms, "
              f"P95: {analysis_disabled['performance']['p95_duration_ms']:.2f}ms")
        print()
        
        # Test with profiling enabled
        print("Phase 2: Testing with profiling ENABLED")
        await self.enable_profiling()
        await asyncio.sleep(2)  # Allow time for change to take effect
        
        results_enabled = await self.run_load_test(duration, concurrent, endpoints)
        analysis_enabled = self.analyze_results(results_enabled)
        
        print(f"Enabled - Avg: {analysis_enabled['performance']['average_duration_ms']:.2f}ms, "
              f"P95: {analysis_enabled['performance']['p95_duration_ms']:.2f}ms")
        print()
        
        # Calculate impact
        avg_overhead = (analysis_enabled['performance']['average_duration_ms'] - 
                       analysis_disabled['performance']['average_duration_ms'])
        p95_overhead = (analysis_enabled['performance']['p95_duration_ms'] - 
                       analysis_disabled['performance']['p95_duration_ms'])
        
        overhead_percentage = (avg_overhead / analysis_disabled['performance']['average_duration_ms'] * 100 
                              if analysis_disabled['performance']['average_duration_ms'] > 0 else 0)
        
        return {
            "profiling_disabled": analysis_disabled,
            "profiling_enabled": analysis_enabled,
            "impact": {
                "average_overhead_ms": avg_overhead,
                "p95_overhead_ms": p95_overhead,
                "overhead_percentage": overhead_percentage
            }
        }
    
    async def enable_profiling(self):
        """Enable network profiling."""
        url = f"{self.base_url}/api/v1/debug/network-profiling/enable"
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=self.headers) as response:
                if response.status != 200:
                    print(f"Warning: Failed to enable profiling: {response.status}")
    
    async def disable_profiling(self):
        """Disable network profiling."""
        url = f"{self.base_url}/api/v1/debug/network-profiling/disable"
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=self.headers) as response:
                if response.status != 200:
                    print(f"Warning: Failed to disable profiling: {response.status}")
    
    def print_results(self, analysis: Dict[str, Any]):
        """Print formatted test results."""
        print("=== Load Test Results ===")
        
        summary = analysis["summary"]
        performance = analysis["performance"]
        
        print(f"Total Requests: {summary['total_requests']:,}")
        print(f"Successful: {summary['successful_requests']:,}")
        print(f"Failed: {summary['failed_requests']:,}")
        print(f"Error Rate: {summary['error_rate_percent']:.2f}%")
        print(f"Requests/Second: {summary['requests_per_second']:.2f}")
        print()
        
        print("Performance Metrics:")
        print(f"  Average: {performance['average_duration_ms']:.2f}ms")
        print(f"  Median: {performance['median_duration_ms']:.2f}ms")
        print(f"  P95: {performance['p95_duration_ms']:.2f}ms")
        print(f"  P99: {performance['p99_duration_ms']:.2f}ms")
        print(f"  Min: {performance['min_duration_ms']:.2f}ms")
        print(f"  Max: {performance['max_duration_ms']:.2f}ms")


async def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Load test network profiling performance")
    parser.add_argument("--url", default="http://localhost:8080", help="Riven base URL")
    parser.add_argument("--api-key", required=True, help="API key for authentication")
    parser.add_argument("--duration", type=int, default=60, help="Test duration in seconds")
    parser.add_argument("--concurrent", type=int, default=10, help="Concurrent requests")
    parser.add_argument("--compare", action="store_true", help="Compare enabled vs disabled profiling")
    parser.add_argument("--endpoints", nargs="+", default=["debug/network-stats"], help="Endpoints to test")
    parser.add_argument("--output", help="Output file for results (JSON)")
    
    args = parser.parse_args()
    
    tester = LoadTester(args.url, args.api_key)
    
    if args.compare:
        # Compare profiling enabled vs disabled
        results = await tester.test_profiling_impact(args.duration, args.concurrent, args.endpoints)
        
        print("=== Performance Impact Analysis ===")
        impact = results["impact"]
        print(f"Average Overhead: {impact['average_overhead_ms']:.2f}ms ({impact['overhead_percentage']:.1f}%)")
        print(f"P95 Overhead: {impact['p95_overhead_ms']:.2f}ms")
        
        if impact['overhead_percentage'] < 5:
            print("✅ Performance impact is acceptable (< 5%)")
        elif impact['overhead_percentage'] < 10:
            print("⚠️  Performance impact is moderate (5-10%)")
        else:
            print("❌ Performance impact is high (> 10%)")
        
    else:
        # Single load test
        results = await tester.run_load_test(args.duration, args.concurrent, args.endpoints)
        analysis = tester.analyze_results(results)
        tester.print_results(analysis)
        results = analysis
    
    # Save results if requested
    if args.output:
        with open(args.output, 'w') as f:
            json.dump(results, f, indent=2)
        print(f"\nResults saved to {args.output}")


if __name__ == "__main__":
    asyncio.run(main())
