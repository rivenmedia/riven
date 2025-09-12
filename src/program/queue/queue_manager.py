"""
Unified queue management for Dramatiq/LavinMQ.

Key changes:
- Explicit payload kinds for jobs ("existing_item" vs "content_item").
- Unified service runner: run_service_for_job(job: JobMessage) -> bool
- Pure state engine usage for next steps (decide_next_jobs + build_messages)
- Producer submits via broker.enqueue using actor/queue names (no in-process registry)
"""

from __future__ import annotations

from datetime import datetime, timedelta
import random
import os

from typing import Any, Dict, List, Optional

from loguru import logger

from program.metrics.collector import metrics_registry, parse_partition_from_queue

from program.db import db_functions
from program.db.db import db
from program.media.item import MediaItem
from program.media.state import States
from program.queue.broker import get_broker
from program.queue.engine import build_messages, decide_next_jobs
from program.queue.models import JobMessage, JobType, create_job_message
from program.queue.monitor import JobState
from program.services.post_processing import notify as notify_on_complete

SERVICE_FOR_JOB: Dict[JobType, str] = {
    JobType.INDEX: "CompositeIndexer",
    JobType.SCRAPE: "Scraping",
    JobType.DOWNLOAD: "Downloader",
    JobType.SYMLINK: "Symlinker",
    JobType.UPDATE: "Updater",
    JobType.POST_PROCESS: "PostProcessing",
}

# Names of content services that emit brand-new items
CONTENT_SERVICE_NAMES = {"Overseerr", "PlexWatchlist", "Listrr", "Mdblist", "TraktContent"}


def run_service_for_job(job: JobMessage, queue_manager_instance: Optional['QueueManager'] = None) -> bool:
    """
    Execute the service indicated by job.job_type using either:
    - content_item_data (indexer path), or
    - existing item loaded by item_id (all other services).

    Handles delayed retries, state persistence, and scheduling next jobs.
    """
    from program.service_manager import service_manager  # local import to avoid cycles

    service_name = SERVICE_FOR_JOB[job.job_type]
    service_instance = service_manager.get_service_by_name(service_name)
    if not service_instance:
        logger.error(f"Service {service_name} not available.")
        return False

    try:
        with db.Session() as session:
            # Resolve an item to operate on, but do NOT prematurely merge a content payload.
            if job.payload_kind == "content_item":
                if service_name != "CompositeIndexer":
                    logger.error(f"Content payload can only be handled by CompositeIndexer, got {service_name}")
                    return False
                # Build a transient MediaItem (not merged yet; indexer decides).
                item = MediaItem(job.content_item_data or {})
                attach_before_run = False
                logger.info(f"Indexing new item: {item.log_string}")
            else:
                if not job.item_id:
                    logger.error("existing_item payload requires item_id.")
                    return False
                item = session.get(MediaItem, job.item_id)
                if not item:
                    logger.warning(f"Item {job.item_id} not found for {service_name}")
                    return False
                attach_before_run = True
                logger.info(f"Processing existing item: {item.log_string}")

            # Merge only existing items to track changes; let indexer produce DB entity for new ones.
            merged_item = session.merge(item) if attach_before_run else item

            try:
                # Run the service generator
                result = next(service_instance.run(merged_item), None)

                # Services may yield (MediaItem, run_at) to request a delayed retry.
                if isinstance(result, tuple) and len(result) == 2:
                    candidate_item, run_at = result  # type: ignore[misc]
                    if isinstance(candidate_item, MediaItem) and isinstance(run_at, datetime):
                        tracked = session.merge(candidate_item)
                        session.commit()
                        if not getattr(tracked, "id", None):
                            logger.error("Cannot schedule retry; item has no id after merge.")
                            return False
                        # Create a new QueueManager instance to avoid circular reference
                        qm = QueueManager()
                        return qm.schedule_delayed_retry(job.job_type, tracked.id, run_at, emitted_by=service_name)
                    logger.error(f"Invalid delayed retry payload from {service_name}: {type(result)}")
                    return False

                if result is None:
                    logger.debug(f"{service_name} returned no result for {merged_item.log_string}")
                    return False

                if not isinstance(result, MediaItem):
                    logger.error(f"{service_name} emitted non-MediaItem: {type(result).__name__}")
                    return False

                # Persist new state
                tracked_item = session.merge(result)
                # Bubble state to parents appropriately
                if tracked_item.type == "episode":
                    tracked_item.parent.parent.store_state()
                elif tracked_item.type == "season":
                    tracked_item.parent.store_state()
                else:
                    tracked_item.store_state()

                session.commit()
                logger.success(f"{service_name} processed {tracked_item.log_string}")

                # Post-completion side-effect: notifications for Completed (outside engine for clarity)
                if (tracked_item.last_state or tracked_item.state) == States.Completed:
                    if job.emitted_by not in {"RetryItem", "PostProcessing"}:
                        try:
                            notify_on_complete(tracked_item)
                        except Exception as e:
                            logger.debug(f"Completion notification skipped: {e}")

                # Decide and enqueue next steps
                msgs: List[JobMessage] = build_messages(decide_next_jobs(tracked_item, emitted_by=job.emitted_by or service_name))
                submitted_any = False
                # Use provided queue manager instance or create new one to avoid circular reference
                qm = queue_manager_instance or QueueManager()
                for m in msgs:
                    submitted_any = qm.submit_job(m) or submitted_any

                return True if (msgs and submitted_any) or not msgs else False

            except Exception as e:
                logger.error(f"Service {service_name} failed for {merged_item.log_string}: {e}")
                session.rollback()
                raise

    except Exception as e:
        logger.error(f"Failed to run {service_name} for job {job.job_id}: {e}")
        return False


def submit_job_to_actor(job: JobMessage) -> bool:
    """
    Submit a job to Dramatiq by actor name and queue name via the broker.
    This decouples the producer from worker actor imports.
    """
    try:
        import dramatiq  # local import to avoid global dependency at module import time

        from program.queue.broker import setup_dramatiq_broker

        # Resolve partition based on stable key (prefer item_id; else external ids; else job_id)
        from program.queue.partitioning import select_partition, resolve_partitioned_names

        key_parts: List[str] = []
        if job.item_id:
            key_parts.append(str(job.item_id))
        if job.content_item_data:
            for k in ("tmdb_id", "tvdb_id", "imdb_id", "title"):
                v = job.content_item_data.get(k)
                if v:
                    key_parts.append(str(v))
        if not key_parts:
            key_parts.append(job.job_id)
        key = ":".join(key_parts)

        partition_index = select_partition(job.job_type, key)
        queue_name, actor_name = resolve_partitioned_names(job.job_type, partition_index)

        # Attach partition metadata for metrics & observability
        if os.getenv("RIVEN_QUEUE_DEBUG", "0") == "1":
            logger.debug(f"enqueue: job={job.job_id} -> {queue_name}/{actor_name}")

        try:
            if job.metadata is None:
                job.metadata = {}
            job.metadata["partition"] = f"p{partition_index}"
            job.metadata["queue_name"] = queue_name
        except Exception:
            pass

        payload = job.to_dict()
        delay_ms: Optional[int] = None
        if job.run_at:
            try:
                dt = datetime.fromisoformat(job.run_at)
                delta = int((dt - datetime.now()).total_seconds() * 1000)
                delay_ms = max(delta, 0)
            except Exception:
                delay_ms = None

        broker = get_broker() or setup_dramatiq_broker()
        if not broker:
            logger.error("Dramatiq broker is not configured; cannot enqueue message")
            return False

        options = {"delay": delay_ms} if delay_ms and delay_ms > 0 else {}
        message = dramatiq.Message(
            queue_name=queue_name,
            actor_name=actor_name,
            args=(payload,),
            kwargs={},
            options=options,
        )
        broker.enqueue(message)

        # Metrics: mark enqueued
        try:
            partition_label = parse_partition_from_queue(queue_name)
            metrics_registry.mark_enqueued(job.job_id, job.job_type.value, partition_label)
        except Exception:
            pass
        if delay_ms and delay_ms > 0:
            logger.debug(f"Job {job.job_id} enqueued to {actor_name} on '{queue_name}' with {delay_ms}ms delay")
        else:
            logger.debug(f"Job {job.job_id} enqueued to {actor_name} on '{queue_name}'")
        return True

    except Exception as e:
        logger.error(f"Failed to submit job {job.job_id}: {e}")
        return False


class QueueManager:
    """Manages Dramatiq queues and job submission."""

    def __init__(self) -> None:
        self.broker = get_broker()
        self._processing_paused = False

    def pause_processing(self) -> None:
        """Pause queue processing due to LavinMQ issues."""
        self._processing_paused = True
        logger.warning("Queue processing paused due to LavinMQ connectivity issues")

    def resume_processing(self) -> None:
        """Resume queue processing after LavinMQ is restored."""
        self._processing_paused = False
        logger.info("Queue processing resumed - LavinMQ connectivity restored")

    def is_processing_paused(self) -> bool:
        """Check if queue processing is currently paused."""
        return self._processing_paused

    def submit_job(self, job: JobMessage) -> bool:
        """
        Submit a job to the appropriate Dramatiq actor.
        Applies intelligent backpressure when priority limits are exceeded by delaying submission instead of rejecting.
        """
        if self._processing_paused:
            logger.warning(f"Queue processing paused - skipping {job.job_type.value} ({job.log_message})")
            return False

        # Backpressure: if no explicit run_at and priority is over limit, delay job
        if not job.run_at:
            try:
                from program.queue.monitor import queue_monitor
                over, count, limit = queue_monitor.is_over_priority_limit(job.priority)
                if over:
                    # Simple linear backoff capped between 5s and 120s
                    delay_sec = min(max((count - limit + 1) * 2, 5), 120)
                    job.run_at = (datetime.now() + timedelta(seconds=delay_sec)).isoformat()
                    logger.warning(
                        f"Priority {job.priority} over limit ({count}/{limit}); delaying job {job.job_id} by {delay_sec}s instead of immediate enqueue"
                    )
            except Exception as e:
                logger.debug(f"Backpressure check failed for job {job.job_id}: {e}")

        return submit_job_to_actor(job)

    def schedule_delayed_retry(self, job_type: JobType, item_id: str, run_at: datetime, emitted_by: str = "System") -> bool:
        """
        Schedule a delayed retry for an existing item job.
        """
        try:
            retry_job = create_job_message(
                job_type,
                payload_kind="existing_item",
                item_id=item_id,
                emitted_by=emitted_by,
                # Add small jitter to avoid thundering herds on delayed retries
                run_at=(run_at + timedelta(seconds=random.uniform(0, 2))).isoformat(),
                metadata={"delayed_retry": True, "original_run_at": run_at.isoformat()},
            )
            # Metrics: record retry with predicted partition label
            try:
                from program.queue.partitioning import select_partition
                part = select_partition(job_type, str(item_id))
                metrics_registry.mark_retry(job_type.value, f"p{part}")
            except Exception:
                pass
            return self.submit_job(retry_job)
        except Exception as e:
            logger.error(f"Failed to schedule delayed retry for {job_type.value}: {e}")
            return False

    def submit_content_item(self, item: MediaItem, *, priority: int = 5, emitted_by: str = "Manual") -> bool:
        """
        Submit a new/transient content item for indexing.

        Pass an explicit content_item_data dict to minimize serialization and
        keep consistent with ID-only strategy for existing items.
        """
        if self._processing_paused:
            logger.warning(f"Queue paused - skipping new item {item.log_string}")
            return False

        # Build a minimal content payload from the transient item (no DB id expected)
        content_item_data = {
            "title": getattr(item, "title", None),
            "type": getattr(item, "type", None),
            "tmdb_id": getattr(item, "tmdb_id", None),
            "tvdb_id": getattr(item, "tvdb_id", None),
            "imdb_id": getattr(item, "imdb_id", None),
            "year": getattr(item, "year", None),
        }

        job = create_job_message(
            JobType.INDEX,
            payload_kind="content_item",
            content_item_data=content_item_data,  # explicit payload for indexer
            priority=priority,
            emitted_by=emitted_by,
        )
        return self.submit_job(job)

    def submit_existing_item(self, item: MediaItem, *, emitted_by: str = "Manual") -> bool:
        """
        Route an already-persisted item based on state via the pure engine.
        """
        if self._processing_paused:
            logger.warning(f"Queue paused - skipping {item.log_string}")
            return False

        # Decide next steps and enqueue
        msgs = build_messages(decide_next_jobs(item, emitted_by))
        submitted_any = False
        for m in msgs:
            submitted_any = self.submit_job(m) or submitted_any
        return submitted_any

    def submit_item(self, item: MediaItem, emitted_by: str = "Manual") -> bool:
        """
        Back-compat entrypoint:
        - If item has no id or looks like a fresh content submission, enqueue INDEX with content payload.
        - Otherwise, resolve duplicates and route via engine.
        """
        if self._processing_paused:
            logger.warning(f"Queue paused - skipping {item.log_string}")
            return False

        try:
            # Resolve existing by external ids to avoid re-indexing completed titles.
            if not getattr(item, "id", None) and any([item.tmdb_id, item.tvdb_id, item.imdb_id]):
                existing = db_functions.get_item_by_external_id(
                    imdb_id=item.imdb_id,
                    tvdb_id=item.tvdb_id,
                    tmdb_id=item.tmdb_id,
                )
                if existing:
                    item = existing

            # Dup/lock checks
            if self._is_item_already_queued(item):
                logger.debug(f"{item.log_string} already queued/locked")
                return False

            # New items (content services or state Requested or missing title) => content payload INDEX
            is_new = (
                not getattr(item, "id", None)
                or item.state == States.Requested
                or emitted_by in CONTENT_SERVICE_NAMES
                or not item.title
            )
            if is_new and not getattr(item, "id", None):
                priority = 3 if emitted_by in CONTENT_SERVICE_NAMES else 5
                return self.submit_content_item(item, priority=priority, emitted_by=emitted_by)

            priority = 5
            if emitted_by in ("Downloader", "Symlinker", "Updater"):
                priority = 2

            # Persisted item => route via engine
            return self.submit_existing_item(item, emitted_by=emitted_by)

        except Exception as e:
            logger.error(f"Failed to submit {item.log_string}: {e}")
            return False

    def _is_item_already_queued(self, item: MediaItem) -> bool:
        """
        Check if an item is already in-flight (lock) or has a duplicate job (external ids).
        """
        from program.queue.monitoring import dependency_manager, queue_monitor

        if item.id:
            locks = dependency_manager.get_item_locks(item.id)
            if locks:
                logger.debug(f"{item.log_string} locked by jobs: {locks}")
                return True

        # Ancestor lock checks to enforce Show → Seasons → Episodes sequencing
        try:
            itype = getattr(item, "type", None)
            # Season should not start if its Show is locked
            if itype == "season":
                parent = getattr(item, "parent", None)
                parent_id = getattr(parent, "id", None)
                if parent_id:
                    parent_locks = dependency_manager.get_item_locks(parent_id)
                    if parent_locks:
                        logger.debug(f"{item.log_string} blocked by parent locks: {parent_locks}")
                        return True
            # Episode should not start if its Season or Show is locked
            if itype == "episode":
                season = getattr(item, "parent", None)
                season_id = getattr(season, "id", None)
                if season_id:
                    season_locks = dependency_manager.get_item_locks(season_id)
                    if season_locks:
                        logger.debug(f"{item.log_string} blocked by season locks: {season_locks}")
                        return True
                show = getattr(season, "parent", None) if season else None
                show_id = getattr(show, "id", None)
                if show_id:
                    show_locks = dependency_manager.get_item_locks(show_id)
                    if show_locks:
                        logger.debug(f"{item.log_string} blocked by show locks: {show_locks}")
                        return True
        except Exception:
            # Be conservative: if any errors resolving ancestors, do not block
            pass

        duplicate_job = queue_monitor.get_duplicate_job_info(
            tmdb_id=item.tmdb_id,
            tvdb_id=item.tvdb_id,
            imdb_id=item.imdb_id,
        )
        if duplicate_job:
            logger.debug(f"{item.log_string} already has job {duplicate_job.job_id} ({duplicate_job.state.value})")
            return True

        return False

    def get_queue_status(self) -> Dict[str, Any]:
        """Shallow status; broker-connected hint only."""
        status: Dict[str, Any] = {}
        try:
            broker = get_broker()
            for name in ("indexing", "scraping", "downloader", "symlinker", "updater", "postprocessing"):
                status[name] = {"length": "unknown", "status": "active", "workers": "unknown"}
            status["_worker_info"] = {
                "broker_connected": broker is not None,
                "broker_type": type(broker).__name__ if broker else "None",
                "message": "Workers should be running if broker is connected",
            }
        except Exception as e:
            logger.error(f"Failed to get queue status: {e}")
            status = {"error": str(e)}
        return status

    def cancel_job(self, item_id: str) -> None:
        """
        Cancel all jobs associated with a given item_id.

        Efficiently:
        - Clear item locks and dependency records in a single synchronized call.
        - Batch-mark jobs as failed in the queue monitor (Dramatiq cannot revoke messages).
        """
        from program.queue.monitoring import dependency_manager, queue_monitor

        # Clear locks and dependency records atomically within DependencyManager
        try:
            affected_job_ids = dependency_manager.clear_item_and_dependencies(item_id)
        except AttributeError:
            # Fallback for older DependencyManager without helper
            locks = dependency_manager.get_item_locks(item_id)
            affected_job_ids = set(locks)

        if not affected_job_ids:
            logger.info(f"Cancelled all jobs for item {item_id}: none found")
            return

        # Batch mark as failed/cancelled in monitor under its own lock
        try:
            if hasattr(queue_monitor, "batch_mark_failed"):
                updated = queue_monitor.batch_mark_failed(affected_job_ids)
                logger.info(f"Marked {updated} jobs as failed/cancelled for item {item_id}")
            else:
                # Fallback: single lookups
                for jid in affected_job_ids:
                    js = queue_monitor.get_job_status(jid)
                    if js:
                        js.state = JobState.FAILED
                logger.info(f"Marked {len(affected_job_ids)} jobs as failed/cancelled for item {item_id}")
        except Exception as e:
            logger.warning(f"Failed to batch-mark jobs for item {item_id}: {e}")


queue_manager = QueueManager()
