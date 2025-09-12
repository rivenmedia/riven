"""
Dramatiq actors for worker processes.

This module defines actors and registers them in the actor registry.
Broker configuration must happen before this module is imported.
"""

from __future__ import annotations

import os
from typing import Any, Dict

import dramatiq
from loguru import logger

from program.queue.models import QUEUE_NAMES, JobMessage
from program.queue.monitoring import dependency_manager, queue_monitor
from program.queue.queue_manager import queue_manager, run_service_for_job
from program.queue.partitioning import (
    PARTITION_COUNTS,
    resolve_partitioned_names,
)
from program.metrics.collector import metrics_registry

# debugpy support in workers (optional)
if os.getenv("RIVEN_DEBUGPY", "0") == "1":
    try:
        import debugpy  # type: ignore
        host = os.getenv("RIVEN_DEBUGPY_HOST", "127.0.0.1")
        port_env = os.getenv("RIVEN_DEBUGPY_PORT")
        if port_env:
            port = int(port_env)
        else:
            import socket as _s
            _sock = _s.socket(_s.AF_INET, _s.SOCK_STREAM)
            _sock.bind((host, 0))
            port = _sock.getsockname()[1]
            _sock.close()
        debugpy.listen((host, port))
        logger.info(f"debugpy listening on {host}:{port} (PID {os.getpid()})")
        if os.getenv("RIVEN_DEBUGPY_WAIT_FOR_CLIENT", "0") == "1":
            debugpy.wait_for_client()
    except Exception as _e:
        logger.warning(f"debugpy setup failed: {_e}")

# Ensure a broker is configured before actors are registered (CLI safety net)
try:
    from program.queue.broker import get_broker, setup_dramatiq_broker, verify_broker_config
    if not get_broker():
        setup_dramatiq_broker()
        logger.info("Dramatiq broker configured by worker_actors fallback.")
    verify_broker_config(strict=True)
except Exception as _e:
    logger.error(f"Failed to configure Dramatiq broker in worker_actors: {_e}")


def _run_in_actor(job_data: Dict[str, Any]) -> None:
    """
    Common actor body for all queue types.

    Args:
        job_data: JSON-serializable job dictionary.
    """
    try:
        job = JobMessage.from_dict(job_data)

        # Acquire item lock and register dependencies first; if it fails, keep job pending and register as waiting.
        if not dependency_manager.start_job(job):
            try:
                jm = queue_monitor.get_job_status(job.job_id)
                if not jm:
                    queue_monitor.register_job(job)  # stays PENDING
                # Explicitly mark WAITING for observability
                queue_monitor.mark_waiting(job.job_id)
            except Exception as _e:
                logger.debug(f"monitor pending registration skipped: {_e}")
            try:
                dependency_manager.register_waiting_job(job)
            except Exception as _e:
                logger.warning(f"Failed to register waiting job {job.job_id}: {_e}")
            logger.debug(f"Job {job.job_id} cannot start now; registered as waiting")
            return

        # Lock acquired: now mark monitor RUNNING
        try:
            jm = queue_monitor.get_job_status(job.job_id)
            if not jm:
                queue_monitor.register_job(job)
            queue_monitor.start_job(job.job_id)
        except Exception as _e:
            logger.debug(f"monitor start skipped: {_e}")
        # Metrics: mark started
        try:
            partition = (job.metadata or {}).get("partition", "p0")
            metrics_registry.mark_started(job.job_id, job.job_type.value, partition)
        except Exception:
            pass

        success = False
        try:
            logger.info(f"Processing {job.job_type.value} job {job.job_id} ({job.log_message})")
            success = run_service_for_job(job, queue_manager)
            if success:
                logger.success(f"Job {job.job_id} completed successfully")
            else:
                logger.warning(f"Job {job.job_id} completed with issues")
        except Exception as e:
            logger.error(f"Job {job.job_id} failed: {e}")
            success = False
            raise
        finally:
            dependency_manager.complete_job(job.job_id)
            try:
                jm = queue_monitor.get_job_status(job.job_id)
                if not jm:
                    # Ensure lifecycle closure even if earlier registration was skipped due to limits
                    queue_monitor.register_job(job)
                queue_monitor.complete_job(job.job_id, success=success)
            except Exception as _e:
                logger.warning(f"Monitor completion fallback failed for {job.job_id}: {_e}")
            # Metrics: mark completed
            try:
                partition = (job.metadata or {}).get("partition", "p0")
                metrics_registry.mark_completed(job.job_id, job.job_type.value, partition, success)
            except Exception:
                pass
    except Exception as e:
        logger.error(f"Actor failed to process job: {e}")
        # Don't re-raise to prevent worker crashes
        return


@dramatiq.actor(queue_name=QUEUE_NAMES["indexing"], max_retries=3, time_limit=300_000)
def indexing_actor(job_data: Dict[str, Any]) -> None:
    _run_in_actor(job_data)


@dramatiq.actor(queue_name=QUEUE_NAMES["scraping"], max_retries=3, time_limit=300_000)
def scraping_actor(job_data: Dict[str, Any]) -> None:
    _run_in_actor(job_data)


@dramatiq.actor(queue_name=QUEUE_NAMES["downloader"], max_retries=3, time_limit=600_000)
def downloader_actor(job_data: Dict[str, Any]) -> None:
    _run_in_actor(job_data)


@dramatiq.actor(queue_name=QUEUE_NAMES["symlinker"], max_retries=3, time_limit=300_000)
def symlinker_actor(job_data: Dict[str, Any]) -> None:
    _run_in_actor(job_data)


@dramatiq.actor(queue_name=QUEUE_NAMES["updater"], max_retries=3, time_limit=300_000)
def updater_actor(job_data: Dict[str, Any]) -> None:
    _run_in_actor(job_data)


@dramatiq.actor(queue_name=QUEUE_NAMES["postprocessing"], max_retries=3, time_limit=300_000)
def postprocessing_actor(job_data: Dict[str, Any]) -> None:
    _run_in_actor(job_data)


# Dynamically register partitioned actors per job type
try:
    partition_specs = {
        "indexing": (JobMessage.JobType.INDEX, 3, 300_000),
        "scraping": (JobMessage.JobType.SCRAPE, 3, 300_000),
        "downloader": (JobMessage.JobType.DOWNLOAD, 3, 600_000),
        "symlinker": (JobMessage.JobType.SYMLINK, 3, 300_000),
        "updater": (JobMessage.JobType.UPDATE, 3, 300_000),
        "postprocessing": (JobMessage.JobType.POST_PROCESS, 3, 300_000),
    }
except AttributeError:
    # Fallback: JobType may be imported differently; use import directly
    from program.queue.models import JobType as _JT  # type: ignore
    partition_specs = {
        "indexing": (_JT.INDEX, 3, 300_000),
        "scraping": (_JT.SCRAPE, 3, 300_000),
        "downloader": (_JT.DOWNLOAD, 3, 600_000),
        "symlinker": (_JT.SYMLINK, 3, 300_000),
        "updater": (_JT.UPDATE, 3, 300_000),
        "postprocessing": (_JT.POST_PROCESS, 3, 300_000),
    }

for jt, _max_retries, _time_limit in partition_specs.values():
    count = PARTITION_COUNTS.get(jt, 1)
    for _p in range(max(1, count)):
        qname, aname = resolve_partitioned_names(jt, _p)

        def _make_actor(queue_name: str, _ar_name: str):  # closure to bind params
            def _fn(job_data: Dict[str, Any]) -> None:
                _run_in_actor(job_data)
            _fn.__name__ = _ar_name  # ensure unique Dramatiq actor name
            return dramatiq.actor(queue_name=queue_name, max_retries=_max_retries, time_limit=_time_limit)(_fn)

        globals()[aname] = _make_actor(qname, aname)
        logger.debug(f"Registered partitioned actor {aname} on {qname}")
