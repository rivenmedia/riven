"""
Consolidated monitoring module.

This module provides a unified interface to the queue monitoring system
by importing and re-exporting components from focused modules.

Components:
- Health checking for LavinMQ and services (from health.py)
- Job dependency management and item locking (from dependencies.py)
- Queue monitoring and job lifecycle tracking (from monitor.py)
"""

from __future__ import annotations

from .dependencies import DependencyInfo, DependencyManager, dependency_manager

# Import all components from focused modules
from .health import HealthChecker, HealthStatus, health_checker
from .monitor import JobMonitor, JobState, QueueMonitor, queue_monitor

# Re-export everything for backward compatibility
__all__ = [
    # Health checking
    "HealthChecker",
    "HealthStatus",
    "health_checker",

    # Dependencies
    "DependencyManager",
    "DependencyInfo",
    "dependency_manager",

    # Queue monitoring
    "QueueMonitor",
    "JobMonitor",
    "JobState",
    "queue_monitor",
]
