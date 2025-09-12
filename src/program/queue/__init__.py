"""
Riven Queue System - Dramatiq/LavinMQ Integration

This module provides a complete queue management system using Dramatiq and LavinMQ
for background job processing in the Riven media management system.

Key Components:
- QueueManager: Main interface for job submission and queue management
- JobMessage: Standardized job message format
- JobType: Enumeration of supported job types
- Broker: Dramatiq broker configuration for LavinMQ
- Actors: Dramatiq worker actors for job processing
- Monitoring: Health checking and job lifecycle tracking
"""

from __future__ import annotations

from .broker import get_broker, setup_dramatiq_broker
from .dependencies import DependencyManager
from .engine import EnqueueRequest, build_messages, decide_next_jobs
from .health import HealthChecker
from .models import (
    DEFAULT_EMITTED_BY,
    QUEUE_NAMES,
    ContentItemData,
    JobMessage,
    JobType,
    PayloadKind,
    create_job_message,
)
from .monitor import QueueMonitor
from .monitoring import (
    HealthStatus,
    JobMonitor,
    JobState,
    dependency_manager,
    health_checker,
    queue_monitor,
)
from .queue_manager import QueueManager, queue_manager

__all__ = [
    # Core management
    "QueueManager",
    "queue_manager",

    # Job models
    "JobMessage",
    "JobType",
    "PayloadKind",
    "ContentItemData",
    "create_job_message",
    "QUEUE_NAMES",
    "DEFAULT_EMITTED_BY",

    # Broker
    "setup_dramatiq_broker",
    "get_broker",

    # Engine
    "decide_next_jobs",
    "build_messages",
    "EnqueueRequest",

    # Monitoring
    "health_checker",
    "dependency_manager",
    "queue_monitor",
    "HealthStatus",
    "JobMonitor",
    "JobState",

    # Individual monitoring classes
    "HealthChecker",
    "DependencyManager",
    "QueueMonitor",
]