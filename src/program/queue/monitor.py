"""
Queue monitoring and job lifecycle tracking.

This module provides monitoring functionality for job queues,
including job state tracking, orphan detection, and queue health monitoring.
"""

import threading
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Set

from loguru import logger

from program.queue.models import JobMessage, JobType


class JobState(Enum):
    """Job states for monitoring"""
    PENDING = "pending"
    WAITING = "waiting"  # queued but blocked by locks/dependencies
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    ORPHANED = "orphaned"
    TIMEOUT = "timeout"


@dataclass
class JobMonitor:
    """Monitor a job's lifecycle"""
    job_id: str
    job_type: JobType
    item_id: Optional[str]
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    state: JobState = JobState.PENDING
    retry_count: int = 0
    max_retries: int = 3
    priority: int = 5
    last_heartbeat: Optional[datetime] = None
    timeout_seconds: int = 300  # 5 minutes default
    # External IDs for duplicate detection
    tmdb_id: Optional[str] = None
    tvdb_id: Optional[str] = None
    imdb_id: Optional[str] = None
    # Mark when registered under overflow/backpressure conditions
    overflow: bool = False


class QueueMonitor:
    """Monitors queue health, handles orphaned jobs, and manages priority"""

    def __init__(self):
        self._lock = threading.RLock()
        self._jobs: Dict[str, JobMonitor] = {}
        self._orphaned_jobs: Set[str] = set()
        self._cleanup_interval = timedelta(minutes=5)
        self._last_cleanup = datetime.now()
        self._job_timeouts = {
            JobType.INDEX: 300,       # 5 minutes
            JobType.SCRAPE: 300,      # 5 minutes
            JobType.DOWNLOAD: 1800,   # 30 minutes
            JobType.SYMLINK: 60,      # 1 minute
            JobType.UPDATE: 30,       # 30 seconds
            JobType.POST_PROCESS: 600 # 10 minutes
        }
        self._max_queue_size = 100000
        self._priority_thresholds = {
            1: 50,   # High priority: max 50 jobs
            2: 100,  # Medium-high: max 100 jobs
            3: 200,  # Medium: max 200 jobs
            4: 300,  # Medium-low: max 300 jobs
            5: 500   # Low priority: max 500 jobs
        }

    def register_job(self, job: JobMessage) -> bool:
        """Register a new job for monitoring (never rejects; applies backpressure via flags).
        Idempotent: if job exists, returns True.
        """
        with self._lock:
            if job.job_id in self._jobs:
                return True

            # Check limits to set overflow flag and log, but DO NOT reject.
            queue_size = len(self._jobs)
            overflow = False
            if queue_size >= self._max_queue_size:
                logger.warning(f"Queue size limit reached ({self._max_queue_size}), registering job {job.job_id} with overflow flag")
                overflow = True

            # Check priority limits (count only same-priority jobs)
            priority_count = len([j for j in self._jobs.values() if j.priority == job.priority])
            max_for_priority = self._priority_thresholds.get(job.priority, 1000)
            if priority_count >= max_for_priority:
                logger.warning(f"Priority {job.priority} limit reached ({max_for_priority}); registering job {job.job_id} under overflow")
                overflow = True

            # Extract external IDs from content_item_data
            tmdb_id = None
            tvdb_id = None
            imdb_id = None

            if job.content_item_data:
                tmdb_id = job.content_item_data.get("tmdb_id")
                tvdb_id = job.content_item_data.get("tvdb_id")
                imdb_id = job.content_item_data.get("imdb_id")

            monitor = JobMonitor(
                job_id=job.job_id,
                job_type=job.job_type,
                item_id=job.item_id,
                created_at=datetime.now(),
                priority=job.priority,
                max_retries=job.max_retries,
                timeout_seconds=self._job_timeouts.get(job.job_type, 300),
                tmdb_id=tmdb_id,
                tvdb_id=tvdb_id,
                imdb_id=imdb_id,
                overflow=overflow,
            )

            self._jobs[job.job_id] = monitor
            logger.debug(f"Registered job {job.job_id} for monitoring (overflow={overflow})")
            return True

    def start_job(self, job_id: str) -> bool:
        """Mark a job as started"""
        with self._lock:
            if job_id not in self._jobs:
                logger.warning(f"Job {job_id} not found for start")
                return False

            monitor = self._jobs[job_id]
            monitor.state = JobState.RUNNING
            monitor.started_at = datetime.now()
            monitor.last_heartbeat = datetime.now()

            logger.debug(f"Started monitoring job {job_id}")
            return True

    def mark_waiting(self, job_id: str) -> bool:
        """Mark a job as waiting due to locks/dependencies"""
        with self._lock:
            jm = self._jobs.get(job_id)
            if not jm:
                logger.warning(f"Job {job_id} not found to mark waiting")
                return False
            if jm.state == JobState.PENDING:
                jm.state = JobState.WAITING
                jm.last_heartbeat = datetime.now()
                logger.debug(f"Marked job {job_id} as WAITING")
            return True

    def complete_job(self, job_id: str, success: bool = True) -> bool:
        """Mark a job as completed"""
        with self._lock:
            if job_id not in self._jobs:
                logger.warning(f"Job {job_id} not found for completion")
                return False

            monitor = self._jobs[job_id]
            monitor.state = JobState.COMPLETED if success else JobState.FAILED
            monitor.completed_at = datetime.now()

            # Remove from orphaned set if it was there
            self._orphaned_jobs.discard(job_id)

            logger.debug(f"Completed monitoring job {job_id} (success: {success})")
            return True

    def heartbeat_job(self, job_id: str) -> bool:
        """Update job heartbeat to indicate it's still alive"""
        with self._lock:
            if job_id not in self._jobs:
                return False

            self._jobs[job_id].last_heartbeat = datetime.now()
            return True

    def detect_orphaned_jobs(self) -> List[str]:
        """Detect jobs that appear to be orphaned"""
        with self._lock:
            now = datetime.now()
            orphaned = []

            for job_id, monitor in self._jobs.items():
                if monitor.state == JobState.RUNNING:
                    # Check if job has timed out
                    if monitor.started_at:
                        elapsed = now - monitor.started_at
                        if elapsed.total_seconds() > monitor.timeout_seconds:
                            monitor.state = JobState.TIMEOUT
                            orphaned.append(job_id)
                            self._orphaned_jobs.add(job_id)
                            logger.warning(f"Job {job_id} timed out after {elapsed.total_seconds()}s")

                    # Check if heartbeat is stale
                    elif monitor.last_heartbeat:
                        elapsed = now - monitor.last_heartbeat
                        if elapsed.total_seconds() > monitor.timeout_seconds:
                            monitor.state = JobState.ORPHANED
                            orphaned.append(job_id)
                            self._orphaned_jobs.add(job_id)
                            logger.warning(f"Job {job_id} appears orphaned (no heartbeat for {elapsed.total_seconds()}s)")

            return orphaned

    def cleanup_orphaned_jobs(self) -> int:
        """Clean up orphaned jobs"""
        with self._lock:
            orphaned = self.detect_orphaned_jobs()
            cleaned_count = 0

            for job_id in orphaned:
                # Remove from monitoring
                del self._jobs[job_id]
                self._orphaned_jobs.discard(job_id)
                cleaned_count += 1

            if cleaned_count > 0:
                logger.debug(f"Cleaned up {cleaned_count} orphaned jobs")

            return cleaned_count

    def cleanup_old_jobs(self) -> int:
        """Clean up old completed jobs quickly to keep memory usage bounded."""
        with self._lock:
            now = datetime.now()
            if now - self._last_cleanup < self._cleanup_interval:
                return 0

            cutoff = now - timedelta(minutes=10)  # Keep completed/failed jobs for 10 minutes
            to_remove = []

            for job_id, monitor in list(self._jobs.items()):
                if (monitor.state in [JobState.COMPLETED, JobState.FAILED] and
                    monitor.completed_at and
                    monitor.completed_at < cutoff):
                    to_remove.append(job_id)

            for job_id in to_remove:
                del self._jobs[job_id]

            self._last_cleanup = now
            logger.debug(f"Cleaned up {len(to_remove)} old jobs")
            return len(to_remove)

    def get_stats(self) -> Dict[str, Any]:
        """Get queue statistics"""
        with self._lock:
            stats = {
                "total_jobs": len(self._jobs),
                "pending_jobs": len([j for j in self._jobs.values() if j.state == JobState.PENDING]),
                "waiting_jobs": len([j for j in self._jobs.values() if j.state == JobState.WAITING]),
                "running_jobs": len([j for j in self._jobs.values() if j.state == JobState.RUNNING]),
                "completed_jobs": len([j for j in self._jobs.values() if j.state == JobState.COMPLETED]),
                "failed_jobs": len([j for j in self._jobs.values() if j.state == JobState.FAILED]),
                "orphaned_jobs": len(self._orphaned_jobs),
                "timeout_jobs": len([j for j in self._jobs.values() if j.state == JobState.TIMEOUT]),
                "queue_size_limit": self._max_queue_size,
                "queue_utilization": len(self._jobs) / self._max_queue_size * 100
            }

            # Add priority breakdown
            for priority in range(1, 6):
                count = len([j for j in self._jobs.values() if j.priority == priority])
                stats[f"priority_{priority}_jobs"] = count

            return stats

    def get_job_status(self, job_id: str) -> Optional[JobMonitor]:
        """Get the status of a specific job"""
        with self._lock:
            return self._jobs.get(job_id)

    def is_over_priority_limit(self, priority: int) -> tuple[bool, int, int]:
        """Return (over_limit, current_count, limit) for a given priority under a lock.
        Counts only active jobs (PENDING/RUNNING) to avoid artificial backpressure from completed jobs.
        """
        with self._lock:
            active = [
                j for j in self._jobs.values()
                if j.priority == priority and j.state in (JobState.PENDING, JobState.RUNNING)
            ]
            count = len(active)
            limit = self._priority_thresholds.get(priority, 1000)
            return (count >= limit, count, limit)

    def batch_mark_failed(self, job_ids: Set[str] | List[str]) -> int:
        """
        Batch mark multiple jobs as FAILED under a single lock acquisition.
        Returns the number of jobs updated.
        """
        with self._lock:
            updated = 0
            now = datetime.now()
            for job_id in job_ids:
                jm = self._jobs.get(job_id)
                if jm is None:
                    continue
                jm.state = JobState.FAILED
                jm.completed_at = now
                self._orphaned_jobs.discard(job_id)
                updated += 1
            return updated

    def get_active_job_id_for_item(self, item_id: str) -> Optional[str]:
        """Return an active (pending/running) job id for the given item_id if any."""
        with self._lock:
            for job in self._jobs.values():
                if job.item_id == item_id and job.state in [JobState.PENDING, JobState.RUNNING]:
                    return job.job_id
        return None

    def has_duplicate_job(self, tmdb_id: str = None, tvdb_id: str = None, imdb_id: str = None) -> bool:
        """Check if there's already a job for an item with the same external IDs"""
        with self._lock:
            for job in self._jobs.values():
                # Skip completed/failed jobs
                if job.state in [JobState.COMPLETED, JobState.FAILED]:
                    continue

                # Check for matching external IDs
                if tmdb_id and job.tmdb_id and tmdb_id == job.tmdb_id:
                    return True
                if tvdb_id and job.tvdb_id and tvdb_id == job.tvdb_id:
                    return True
                if imdb_id and job.imdb_id and imdb_id == job.imdb_id:
                    return True

            return False

    def get_duplicate_job_info(self, tmdb_id: str = None, tvdb_id: str = None, imdb_id: str = None) -> Optional[JobMonitor]:
        """Get information about a duplicate job if one exists"""
        with self._lock:
            for job in self._jobs.values():
                # Skip completed/failed jobs
                if job.state in [JobState.COMPLETED, JobState.FAILED]:
                    continue

                # Check for matching external IDs
                if tmdb_id and job.tmdb_id and tmdb_id == job.tmdb_id:
                    return job
                if tvdb_id and job.tvdb_id and tvdb_id == job.tvdb_id:
                    return job
                if imdb_id and job.imdb_id and imdb_id == job.imdb_id:
                    return job

            return None

    def is_queue_healthy(self) -> bool:
        """Check if the queue is healthy"""
        with self._lock:
            # Check if queue is too full
            if len(self._jobs) > self._max_queue_size * 0.9:  # 90% full
                return False

            # Check if too many orphaned jobs
            orphaned_ratio = len(self._orphaned_jobs) / max(len(self._jobs), 1)
            if orphaned_ratio > 0.1:  # More than 10% orphaned
                return False

            return True


# Global instance
queue_monitor = QueueMonitor()
