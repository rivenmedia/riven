"""
Job dependency management and item locking.

This module handles job dependencies and prevents concurrent processing
of related items to maintain data consistency.
"""

import threading
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Set

from loguru import logger

from program.queue.models import JobMessage


@dataclass
class DependencyInfo:
    """Track job dependencies and full job message for re-queuing"""
    job_id: str
    dependencies: Set[str]
    dependents: Set[str]
    item_id: Optional[str] = None
    job_message: Optional[JobMessage] = None


class DependencyManager:
    """Manages job dependencies and prevents concurrent processing of related items"""

    def __init__(self):
        self._lock = threading.RLock()
        self._dependencies: Dict[str, DependencyInfo] = {}
        self._item_locks: Dict[str, Set[str]] = {}  # item_id -> set of job_ids
        self._cleanup_interval = timedelta(hours=1)
        self._last_cleanup = datetime.now()

    def can_start_job(self, job: JobMessage) -> bool:
        """Check if a job can start based on dependencies and locks.
        Important: Do not hold the dependency lock while consulting QueueMonitor to avoid lock inversion.
        """
        # 1) Check explicit job-to-job dependencies (no dep lock held)
        from .monitor import queue_monitor
        for dep_job_id in job.dependencies:
            dep_monitor = queue_monitor.get_job_status(dep_job_id)
            if dep_monitor and dep_monitor.state.value != "completed":
                logger.debug(
                    f"Job {job.job_id} waiting for dependency {dep_job_id} (status: {dep_monitor.state.value})"
                )
                return False

        # 2) Check item-level locks under the dep lock
        with self._lock:
            if job.item_id and self._item_locks.get(job.item_id):
                running_jobs = self._item_locks[job.item_id].copy()
                logger.debug(
                    f"Job {job.job_id} waiting for item {job.item_id} (locked by: {running_jobs})"
                )
                return False
        return True

    def start_job(self, job: JobMessage) -> bool:
        """Attempt to mark a job as started and acquire the item lock.
        Returns True if the job can proceed, False if it must wait.
        Note: We purposely check QueueMonitor outside of our lock to prevent lock inversion.
        """
        # Check job-to-job dependencies first (outside dep lock)
        from .monitor import queue_monitor
        for dep_job_id in job.dependencies:
            dep_monitor = queue_monitor.get_job_status(dep_job_id)
            if dep_monitor and dep_monitor.state.value != "completed":
                return False

        # Now acquire dep lock to check/acquire the item lock and register dependency info
        with self._lock:
            # Check for item-level lock
            if job.item_id and self._item_locks.get(job.item_id):
                return False

            # Extract item identifier for logging
            item_identifier = job.item_id
            if not item_identifier and job.payload_kind == "content_item" and job.content_item_data:
                item_identifier = (
                    job.content_item_data.get("tmdb_id")
                    or job.content_item_data.get("tvdb_id")
                    or job.content_item_data.get("imdb_id")
                    or job.content_item_data.get("title")
                    or "New Item"
                )

            # Create or overwrite dependency info for this job
            dep_info = DependencyInfo(
                job_id=job.job_id,
                dependencies=set(job.dependencies),
                dependents=set(),
                item_id=job.item_id,
                job_message=job,
            )
            self._dependencies[job.job_id] = dep_info

            # Add reverse links for explicit dependencies we just recorded
            for dep_job_id in job.dependencies:
                if dep_job_id in self._dependencies:
                    self._dependencies[dep_job_id].dependents.add(job.job_id)

            # Acquire item lock
            if job.item_id:
                self._item_locks.setdefault(job.item_id, set()).add(job.job_id)

            logger.debug(f"Started job {job.job_id} for item {item_identifier}")
            return True


    def register_waiting_job(self, job: JobMessage) -> None:
        """Register a job that could not acquire its item lock so it can be
        automatically re-queued when its blockers complete.

        We capture current item lock holders as implicit dependencies and link
        reverse dependents so complete_job() can identify and re-queue us.
        """
        dep_set: Set[str] = set(job.dependencies or [])
        # Include current lockers of the same item (if any) as blockers
        with self._lock:
            if job.item_id:
                lockers = self._item_locks.get(job.item_id, set())
                dep_set.update(lockers)

            # Upsert DependencyInfo for this waiting job
            info = self._dependencies.get(job.job_id)
            if info is None:
                info = DependencyInfo(
                    job_id=job.job_id,
                    dependencies=set(),
                    dependents=set(),
                    item_id=job.item_id,
                    job_message=job,
                )
                self._dependencies[job.job_id] = info

            # Update its dependency set to what we see right now
            info.dependencies = dep_set
            info.item_id = job.item_id
            info.job_message = job

            # Link reverse dependents so blockers know about this job
            for dep_job_id in dep_set:
                if dep_job_id in self._dependencies:
                    self._dependencies[dep_job_id].dependents.add(job.job_id)

    def complete_job(self, job_id: str, success: bool = True) -> List[str]:
        """Mark a job as completed and release locks.
        Returns list of jobs that can now start. Avoids lock inversion by:
         - Releasing the item lock and collecting candidates under the dep lock
         - Evaluating dependency status via QueueMonitor outside the dep lock
         - Performing re-queues outside critical sections
        """
        # First critical section: release item lock and snapshot dependents
        with self._lock:
            if job_id not in self._dependencies:
                logger.warning(f"Job {job_id} not found for completion")
                return []

            dep_info = self._dependencies[job_id]

            # Release item lock using the item's id
            if dep_info.item_id:
                locked = self._item_locks.get(dep_info.item_id)
                if locked and job_id in locked:
                    locked.discard(job_id)
                    if not locked:
                        del self._item_locks[dep_info.item_id]

            candidate_ids = list(dep_info.dependents)

        # Evaluate candidate readiness outside dep lock
        from .monitor import queue_monitor
        ready_jobs: List[str] = []
        to_requeue: List[JobMessage] = []

        for candidate_id in candidate_ids:
            # Snapshot candidate dependency info (deps, item_id, message) under a brief dep lock
            with self._lock:
                cand_info = self._dependencies.get(candidate_id)
                if not cand_info:
                    continue
                cand_deps = set(cand_info.dependencies)
                cand_item_id = cand_info.item_id
                cand_msg = cand_info.job_message

            # Check dependency statuses via QueueMonitor outside dep lock
            deps_ok = True
            for dep_id in cand_deps:
                dep_mon = queue_monitor.get_job_status(dep_id)
                if dep_mon and dep_mon.state.value != "completed":
                    deps_ok = False
                    break
            if not deps_ok:
                continue

            # Check item lock availability under dep lock
            with self._lock:
                locked = self._item_locks.get(cand_item_id, set()) if cand_item_id else set()
                can_lock = not bool(locked)

            if can_lock and cand_msg:
                ready_jobs.append(candidate_id)
                to_requeue.append(cand_msg)
            elif can_lock and not cand_msg:
                logger.warning(f"Cannot re-queue job {candidate_id}: no job message stored")

        # Perform re-queues outside locks to reduce contention
        from program.queue.queue_manager import queue_manager
        for msg in to_requeue:
            try:
                # Clear any artificial delay for lock-based requeue. Preserve service-level delayed retries.
                if not (getattr(msg, "metadata", None) and msg.metadata and msg.metadata.get("delayed_retry")):
                    if msg.run_at:
                        logger.debug(f"Clearing run_at for {msg.job_id} on requeue (was {msg.run_at})")
                    msg.run_at = None
                logger.info(f"Re-queuing unblocked job {msg.job_id}")
                ok = queue_manager.submit_job(msg)
                if ok:
                    logger.debug(f"Successfully re-queued job {msg.job_id}")
                else:
                    logger.warning(f"Failed to re-queue job {msg.job_id}")
            except Exception as e:
                logger.warning(f"Exception while re-queuing {msg.job_id}: {e}")

        logger.debug(f"Completed job {job_id}, {len(ready_jobs)} jobs can now start")
        return ready_jobs

    def get_dependency_info(self, job_id: str) -> Optional[DependencyInfo]:
        """Get the dependency info of a job"""
        with self._lock:
            return self._dependencies.get(job_id)

    def get_item_locks(self, item_id: str) -> Set[str]:
        """Get jobs currently locking an item"""
        with self._lock:
            return self._item_locks.get(item_id, set()).copy()

    def clear_item_and_dependencies(self, item_id: str) -> Set[str]:
        """
        Atomically clear item locks and dependency records for a given item.
        Returns the set of affected job_ids.
        """
        with self._lock:
            affected: Set[str] = set()

            # Remove and collect jobs holding the item lock
            locked = self._item_locks.pop(item_id, set())
            affected.update(locked)

            # Remove dependency records associated with the item and update dependents
            to_remove: List[str] = []
            for job_id, dep in self._dependencies.items():
                if dep.item_id == item_id:
                    to_remove.append(job_id)

            for job_id in to_remove:
                dep = self._dependencies.pop(job_id, None)
                if dep is not None:
                    affected.add(job_id)
                    # Clean up reverse links in dependents of its dependencies
                    for dep_job_id in dep.dependencies:
                        if dep_job_id in self._dependencies:
                            self._dependencies[dep_job_id].dependents.discard(job_id)

            return affected

    def cleanup_old_jobs(self) -> int:
        """Clean up old dependency info for completed jobs"""
        with self._lock:
            now = datetime.now()
            if now - self._last_cleanup < self._cleanup_interval:
                return 0

            # Delegate to queue monitor to determine which jobs are old and completed
            from .monitor import queue_monitor

            to_remove = []
            cutoff = now - timedelta(hours=24)  # Keep dependency info for 24 hours

            for job_id in self._dependencies.keys():
                job_monitor = queue_monitor.get_job_status(job_id)
                if (job_monitor and
                    job_monitor.state.value in ["completed", "failed"] and
                    job_monitor.completed_at and
                    job_monitor.completed_at < cutoff):
                    to_remove.append(job_id)

            for job_id in to_remove:
                del self._dependencies[job_id]

            self._last_cleanup = now
            if len(to_remove) > 0:
                logger.debug(f"Cleaned up {len(to_remove)} old dependency records")

            return len(to_remove)

    def get_stats(self) -> Dict[str, Any]:
        """Get statistics about the dependency manager"""
        with self._lock:
            return {
                "tracked_dependencies": len(self._dependencies),
                "locked_items": len(self._item_locks),
                "total_locks": sum(len(jobs) for jobs in self._item_locks.values())
            }


# Global instance
dependency_manager = DependencyManager()
