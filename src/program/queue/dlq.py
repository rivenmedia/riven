"""
Dead Letter Queue (DLQ) publisher utilities.

Publishes final-failure messages to the broker's DLX so operators can triage.
Idempotent and safe to call from signal handlers.
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any, Dict, Optional

import pika
from loguru import logger

from .broker import _augment_amqp_url
from program.settings.manager import settings_manager

DLX_NAME = "riven.dlx"


def _get_amqp_params() -> pika.URLParameters:
    base_url = os.getenv("RIVEN_LAVINMQ_URL", settings_manager.settings.lavinmq_url)
    broker_url = _augment_amqp_url(base_url)
    params = pika.URLParameters(broker_url)
    if not params.heartbeat:
        params.heartbeat = 30
    if not params.blocked_connection_timeout:
        params.blocked_connection_timeout = 300
    return params


def publish_failure_to_dlq(*, queue_name: str, failure: Dict[str, Any]) -> bool:
    """Publish a structured failure payload to the appropriate DLQ via DLX.

    Args:
        queue_name: The original queue name (e.g., "downloader").
        failure: A JSON-serializable dict with failure details.
    """
    routing_key = f"{queue_name}.dlq"
    try:
        params = _get_amqp_params()
        connection = pika.BlockingConnection(params)
        channel = connection.channel()
        # Ensure DLX exists (idempotent)
        channel.exchange_declare(exchange=DLX_NAME, exchange_type="direct", durable=True, passive=False)
        body = json.dumps(failure, default=str).encode("utf-8")
        channel.basic_publish(
            exchange=DLX_NAME,
            routing_key=routing_key,
            body=body,
            properties=pika.BasicProperties(content_type="application/json", delivery_mode=2),  # persistent
        )
        connection.close()
        logger.warning(f"Published final failure to DLQ {routing_key}: job_id={failure.get('job_id')}")
        return True
    except Exception as e:
        logger.error(f"Failed to publish failure to DLQ {routing_key}: {e}")
        return False


def build_failure_payload(*, message, exception: BaseException) -> Dict[str, Any]:
    """Construct a structured failure payload from Dramatiq message and exception."""
    try:
        queue_name: str = getattr(message, "queue_name", "unknown")
        actor_name: str = getattr(message, "actor_name", "unknown")
        options: Dict[str, Any] = getattr(message, "options", {}) or {}
        args = getattr(message, "args", ()) or ()
        job_data: Optional[Dict[str, Any]] = args[0] if args and isinstance(args[0], dict) else None

        payload = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "queue": queue_name,
            "actor": actor_name,
            "job_id": job_data.get("job_id") if job_data else None,
            "job_type": job_data.get("job_type") if job_data else None,
            "item_id": job_data.get("item_id") if job_data else None,
            "external_ids": (job_data.get("content_item_data") or {}) if job_data else None,
            "attempt_count": int(options.get("retries", 0)),
            "max_retries": int(options.get("max_retries", 0)),
            "error": {
                "type": type(exception).__name__,
                "message": str(exception),
            },
        }
        return payload
    except Exception as e:
        logger.debug(f"Building failure payload failed: {e}")
        return {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "queue": getattr(message, "queue_name", "unknown"),
            "actor": getattr(message, "actor_name", "unknown"),
            "error": {"type": type(exception).__name__, "message": str(exception)},
        }

