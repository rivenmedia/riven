"""
Dramatiq signal receivers for handling final failures and publishing to DLQ.
"""
from __future__ import annotations

from typing import Any

from loguru import logger

try:
    from dramatiq import signals
except Exception:  # pragma: no cover - dramatiq might not be loaded in some contexts
    signals = None  # type: ignore

from .dlq import build_failure_payload, publish_failure_to_dlq
from program.metrics.collector import metrics_registry, parse_partition_from_queue


def _is_final_failure(message) -> bool:
    """Best-effort detection of final failure based on message options."""
    try:
        options = getattr(message, "options", {}) or {}
        retries = int(options.get("retries", 0))
        max_retries = int(options.get("max_retries", 0))
        # Dramatiq increments retries per attempt; consider final when retries >= max_retries
        return max_retries > 0 and retries >= max_retries
    except Exception:
        return True


def _queue_name_for(message) -> str:
    return getattr(message, "queue_name", "unknown")


if signals is not None:
    @signals.message_failed.connect
    def on_message_failed(sender: Any, message: Any, exception: BaseException, **kwargs: Any) -> None:  # pragma: no cover
        try:
            if _is_final_failure(message):
                queue_name = _queue_name_for(message)
                payload = build_failure_payload(message=message, exception=exception)
                publish_failure_to_dlq(queue_name=queue_name, failure=payload)
                # Metrics: DLQ count with labels
                try:
                    partition = parse_partition_from_queue(queue_name)
                    # job_type is inside message.args[0]['job_type']
                    args = getattr(message, "args", []) or []
                    job_type = None
                    if args and isinstance(args[0], dict):
                        job_type = args[0].get("job_type")
                    if job_type:
                        metrics_registry.mark_dlq(job_type, partition)
                except Exception:
                    pass
            else:
                # Not final; allow Retries middleware to handle requeue
                pass
        except Exception as e:
            logger.warning(f"DLQ failure handler encountered an error: {e}")

