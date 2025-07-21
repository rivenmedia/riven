#!/usr/bin/env python3
"""
Deployment validation script for Network Profiling.

This script validates that the network profiling feature is working correctly
after deployment and all components are functioning as expected.
"""

import argparse
import json
import sys
import time
from datetime import datetime
from typing import Dict, Any, List

import requests


class DeploymentValidator:
    """Validator for network profiling deployment."""
    
    def __init__(self, base_url: str, api_key: str):
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key
        self.headers = {"Authorization": f"Bearer {api_key}"}
        self.test_results = []
    
    def _make_request(self, method: str, endpoint: str, **kwargs) -> Dict[str, Any]:
        """Make API request with error handling."""
        url = f"{self.base_url}/api/v1/debug/{endpoint}"
        
        try:
            response = requests.request(method, url, headers=self.headers, timeout=10, **kwargs)
            return {
                "success": True,
                "status_code": response.status_code,
                "data": response.json() if response.content else {},
                "response_time": response.elapsed.total_seconds()
            }
        except requests.exceptions.RequestException as e:
            return {
                "success": False,
                "error": str(e),
                "status_code": 0,
                "data": {},
                "response_time": 0
            }
    
    def test_basic_connectivity(self) -> bool:
        """Test basic API connectivity."""
        print("Testing basic connectivity...")
        
        result = self._make_request("GET", "network-profiling/status")
        
        if result["success"] and result["status_code"] == 200:
            print("✅ Basic connectivity: PASS")
            return True
        else:
            print(f"❌ Basic connectivity: FAIL - {result.get('error', 'Unknown error')}")
            return False
    
    def test_profiling_control(self) -> bool:
        """Test profiling enable/disable functionality."""
        print("Testing profiling control...")
        
        # Test disable
        result = self._make_request("POST", "network-profiling/disable")
        if not result["success"] or result["status_code"] != 200:
            print(f"❌ Disable profiling: FAIL - {result.get('error', 'Unknown error')}")
            return False
        
        # Verify disabled
        result = self._make_request("GET", "network-profiling/status")
        if not result["success"] or not result["data"].get("enabled") == False:
            print("❌ Verify disabled: FAIL")
            return False
        
        # Test enable
        result = self._make_request("POST", "network-profiling/enable")
        if not result["success"] or result["status_code"] != 200:
            print(f"❌ Enable profiling: FAIL - {result.get('error', 'Unknown error')}")
            return False
        
        # Verify enabled
        result = self._make_request("GET", "network-profiling/status")
        if not result["success"] or not result["data"].get("enabled") == True:
            print("❌ Verify enabled: FAIL")
            return False
        
        print("✅ Profiling control: PASS")
        return True
    
    def test_data_collection(self) -> bool:
        """Test that profiling data is being collected."""
        print("Testing data collection...")
        
        # Enable profiling
        self._make_request("POST", "network-profiling/enable")
        time.sleep(1)
        
        # Make some requests to generate data
        for _ in range(5):
            self._make_request("GET", "network-stats")
            time.sleep(0.2)
        
        # Check if data was collected
        result = self._make_request("GET", "network-stats")
        if not result["success"]:
            print(f"❌ Get stats: FAIL - {result.get('error', 'Unknown error')}")
            return False
        
        stats = result["data"]
        if stats.get("total_requests", 0) == 0:
            print("❌ Data collection: FAIL - No requests recorded")
            return False
        
        print(f"✅ Data collection: PASS - {stats['total_requests']} requests recorded")
        return True
    
    def test_api_endpoints(self) -> bool:
        """Test all API endpoints."""
        print("Testing API endpoints...")
        
        endpoints = [
            ("GET", "network-stats"),
            ("GET", "network-profiling/status"),
            ("GET", "network-profiling/summary"),
            ("GET", "network-profiling/slow-requests"),
            ("GET", "network-profiling/advanced-stats"),
            ("GET", "network-profiling/domains"),
            ("GET", "network-profiling/services"),
            ("GET", "network-profiling/patterns"),
            ("GET", "network-profiling/health"),
            ("GET", "network-profiling/memory-usage"),
            ("GET", "network-profiling/production-metrics"),
            ("GET", "network-profiling/alerts/status"),
        ]
        
        failed_endpoints = []
        
        for method, endpoint in endpoints:
            result = self._make_request(method, endpoint)
            if not result["success"] or result["status_code"] not in [200, 404]:
                failed_endpoints.append(f"{method} {endpoint}: {result.get('error', 'Unknown error')}")
        
        if failed_endpoints:
            print("❌ API endpoints: FAIL")
            for failure in failed_endpoints:
                print(f"   {failure}")
            return False
        
        print(f"✅ API endpoints: PASS - {len(endpoints)} endpoints tested")
        return True
    
    def test_export_functionality(self) -> bool:
        """Test export functionality."""
        print("Testing export functionality...")
        
        # Test JSON export
        result = self._make_request("GET", "network-profiling/export/json")
        if not result["success"] or result["status_code"] != 200:
            print(f"❌ JSON export: FAIL - {result.get('error', 'Unknown error')}")
            return False
        
        # Test CSV export
        result = self._make_request("GET", "network-profiling/export/csv")
        if not result["success"] or result["status_code"] != 200:
            print(f"❌ CSV export: FAIL - {result.get('error', 'Unknown error')}")
            return False
        
        print("✅ Export functionality: PASS")
        return True
    
    def test_memory_management(self) -> bool:
        """Test memory management functionality."""
        print("Testing memory management...")
        
        # Check memory usage
        result = self._make_request("GET", "network-profiling/memory-usage")
        if not result["success"]:
            print(f"❌ Memory usage check: FAIL - {result.get('error', 'Unknown error')}")
            return False
        
        memory_data = result["data"]
        memory_mb = float(memory_data.get("estimated_mb", "0"))
        
        if memory_mb > 100:  # Alert if memory usage is very high
            print(f"⚠️  High memory usage: {memory_mb}MB")
        
        # Test retention policy
        result = self._make_request("POST", "network-profiling/retention-policy", params={"max_age_hours": 1})
        if not result["success"]:
            print(f"❌ Retention policy: FAIL - {result.get('error', 'Unknown error')}")
            return False
        
        print("✅ Memory management: PASS")
        return True
    
    def test_production_features(self) -> bool:
        """Test production-specific features."""
        print("Testing production features...")
        
        # Test production metrics
        result = self._make_request("GET", "network-profiling/production-metrics")
        if not result["success"]:
            print(f"❌ Production metrics: FAIL - {result.get('error', 'Unknown error')}")
            return False
        
        prod_metrics = result["data"]
        
        # Check for concerning metrics
        consecutive_errors = prod_metrics.get("consecutive_errors", 0)
        if consecutive_errors > 5:
            print(f"⚠️  High consecutive errors: {consecutive_errors}")
        
        perf_metrics = prod_metrics.get("performance_metrics", {})
        avg_overhead = perf_metrics.get("average_overhead_ms", 0)
        if avg_overhead > 5:
            print(f"⚠️  High profiling overhead: {avg_overhead:.2f}ms")
        
        # Test error reset
        result = self._make_request("POST", "network-profiling/reset-errors")
        if not result["success"]:
            print(f"❌ Error reset: FAIL - {result.get('error', 'Unknown error')}")
            return False
        
        print("✅ Production features: PASS")
        return True
    
    def test_alerting(self) -> bool:
        """Test alerting functionality."""
        print("Testing alerting...")
        
        # Check alert status
        result = self._make_request("GET", "network-profiling/alerts/status")
        if not result["success"]:
            print(f"❌ Alert status: FAIL - {result.get('error', 'Unknown error')}")
            return False
        
        # Test alert (this will send a real alert if notifications are configured)
        result = self._make_request("POST", "network-profiling/alerts/test")
        if not result["success"]:
            print(f"❌ Test alert: FAIL - {result.get('error', 'Unknown error')}")
            return False
        
        print("✅ Alerting: PASS")
        return True
    
    def run_validation(self) -> Dict[str, Any]:
        """Run complete validation suite."""
        print("=== Network Profiling Deployment Validation ===")
        print(f"Target: {self.base_url}")
        print(f"Time: {datetime.now().isoformat()}")
        print()
        
        tests = [
            ("Basic Connectivity", self.test_basic_connectivity),
            ("Profiling Control", self.test_profiling_control),
            ("Data Collection", self.test_data_collection),
            ("API Endpoints", self.test_api_endpoints),
            ("Export Functionality", self.test_export_functionality),
            ("Memory Management", self.test_memory_management),
            ("Production Features", self.test_production_features),
            ("Alerting", self.test_alerting),
        ]
        
        results = {}
        passed = 0
        total = len(tests)
        
        for test_name, test_func in tests:
            try:
                result = test_func()
                results[test_name] = result
                if result:
                    passed += 1
            except Exception as e:
                print(f"❌ {test_name}: ERROR - {e}")
                results[test_name] = False
            print()
        
        # Summary
        print("=== Validation Summary ===")
        print(f"Passed: {passed}/{total} tests")
        print(f"Success Rate: {(passed/total)*100:.1f}%")
        
        if passed == total:
            print("🎉 All tests passed! Deployment is ready.")
            overall_status = "PASS"
        elif passed >= total * 0.8:
            print("⚠️  Most tests passed, but some issues detected.")
            overall_status = "PARTIAL"
        else:
            print("❌ Multiple test failures. Deployment needs attention.")
            overall_status = "FAIL"
        
        return {
            "timestamp": datetime.now().isoformat(),
            "overall_status": overall_status,
            "passed_tests": passed,
            "total_tests": total,
            "success_rate": (passed/total)*100,
            "test_results": results
        }


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Validate network profiling deployment")
    parser.add_argument("--url", default="http://localhost:8080", help="Riven base URL")
    parser.add_argument("--api-key", required=True, help="API key for authentication")
    parser.add_argument("--output", help="Output file for results (JSON)")
    
    args = parser.parse_args()
    
    validator = DeploymentValidator(args.url, args.api_key)
    results = validator.run_validation()
    
    # Save results if requested
    if args.output:
        with open(args.output, 'w') as f:
            json.dump(results, f, indent=2)
        print(f"\nResults saved to {args.output}")
    
    # Exit with appropriate code
    if results["overall_status"] == "PASS":
        sys.exit(0)
    elif results["overall_status"] == "PARTIAL":
        sys.exit(1)
    else:
        sys.exit(2)


if __name__ == "__main__":
    main()
