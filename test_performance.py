#!/usr/bin/env python3
"""Test script to debug performance endpoint issues."""

import sys
import traceback

def test_performance_components():
    """Test each component of the performance endpoint individually."""
    
    print("Testing performance endpoint components...")
    
    # Test 1: Basic imports
    try:
        import time
        import os
        print("✓ Basic imports successful")
    except Exception as e:
        print(f"✗ Basic imports failed: {e}")
        return
    
    # Test 2: psutil import and basic usage
    try:
        import psutil
        process = psutil.Process(os.getpid())
        memory_mb = process.memory_info().rss / 1024 / 1024
        print(f"✓ psutil working - Memory: {memory_mb:.1f}MB")
    except Exception as e:
        print(f"✗ psutil failed: {e}")
        traceback.print_exc()
    
    # Test 3: Try to import performance monitor without starting server
    try:
        # Import the PerformanceMonitor class directly
        sys.path.insert(0, '/home/spoked/projects/riven/src')
        
        # Import just the class definition, not the global instance
        from main import PerformanceMonitor
        monitor = PerformanceMonitor()
        stats = monitor.get_stats()
        print(f"✓ PerformanceMonitor class working - Stats: {len(stats)} keys")
    except Exception as e:
        print(f"✗ PerformanceMonitor failed: {e}")
        traceback.print_exc()
    
    # Test 4: Database imports
    try:
        from program.db.db import db
        print("✓ Database import successful")
    except Exception as e:
        print(f"✗ Database import failed: {e}")
        traceback.print_exc()
    
    # Test 5: Program and dependency injection
    try:
        from program import Program
        from kink import di
        print("✓ Program and DI imports successful")
    except Exception as e:
        print(f"✗ Program/DI imports failed: {e}")
        traceback.print_exc()

if __name__ == "__main__":
    test_performance_components()
