"""
Broker configuration for Dramatiq workers.
"""

from __future__ import annotations

import os
from typing import Optional
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import dramatiq
import pika
from dramatiq.brokers.rabbitmq import RabbitmqBroker
from loguru import logger


def _augment_amqp_url(url: str) -> str:
    """Add sane heartbeat/timeouts to AMQP URL if missing."""
    try:
        parsed = urlparse(url)
        query = parse_qs(parsed.query)
        query.setdefault("heartbeat", ["30"])  # seconds
        query.setdefault("blocked_connection_timeout", ["300"])  # seconds
        query.setdefault("socket_timeout", ["30"])  # seconds
        query.setdefault("connection_attempts", ["6"])  # total attempts per connect
        query.setdefault("retry_delay", ["5"])  # seconds between attempts
        return urlunparse(parsed._replace(query=urlencode(query, doseq=True)))
    except Exception:
        return url


def setup_dramatiq_broker() -> RabbitmqBroker:
    """
    Configure and set the global Dramatiq broker exactly once.

    Returns:
        The configured RabbitmqBroker.

    Notes:
        - Idempotently declares exchanges/queues with durability & DLQ.
        - This function is idempotent: if a broker is already configured and looks like
          a RabbitmqBroker pointing at the same URL, it returns it unchanged.
    """
    from program.settings.manager import settings_manager

    base_url = os.getenv("RIVEN_LAVINMQ_URL", settings_manager.settings.lavinmq_url)
    if not base_url or not base_url.startswith("amqp://"):
        raise ValueError("LavinMQ URL is not configured")

    broker_url = _augment_amqp_url(base_url)
    existing = dramatiq.get_broker()

    if isinstance(existing, RabbitmqBroker):
        try:
            existing_url = getattr(existing, "url", None)
        except Exception:
            existing_url = None
        if existing_url == broker_url:
            logger.debug("Dramatiq broker already configured with desired URL; reusing.")
            return existing
        else:
            logger.warning("Replacing existing Dramatiq broker with configured URL.")

    elif existing is not None:
        logger.warning("Non-Rabbitmq broker present; replacing with RabbitmqBroker.")

    # Keep the broker minimal and reliable; avoid speculative kwargs here.
    # Build RabbitmqBroker using url to match Dramatiq expectations (no extra pika kwargs).
    broker = RabbitmqBroker(url=broker_url)
    # Attach middleware once to avoid duplicates if setup is called multiple times.
    def _add_once(mw):
        try:
            existing = getattr(broker, "middleware", [])
            if not any(m.__class__ is mw.__class__ for m in existing):
                broker.add_middleware(mw)
        except Exception:
            # Best-effort: fall back to adding
            try:
                broker.add_middleware(mw)
            except Exception:
                pass
    _add_once(dramatiq.middleware.AgeLimit())
    _add_once(dramatiq.middleware.TimeLimit())
    _add_once(dramatiq.middleware.Retries(max_retries=3))
    _add_once(dramatiq.middleware.Callbacks())
    # Ensure Dramatiq does not auto-declare .DQ queues; we declare via pika.
    try:
        setattr(broker, "declare_queues", False)
    except Exception:
        pass
    dramatiq.set_broker(broker)

    # Declare AMQP infrastructure (idempotent) using pika so queues exist with correct args.
    from program.queue.partitioning import all_partitioned_queue_names
    import time

    max_attempts = int(os.getenv("RIVEN_AMQP_DECLARE_RETRIES", "3"))
    base_backoff = float(os.getenv("RIVEN_AMQP_DECLARE_BACKOFF", "0.5"))  # seconds

    for attempt in range(1, max_attempts + 1):
        connection = None
        try:
            params = pika.URLParameters(broker_url)
            if not params.heartbeat:
                params.heartbeat = 30
            if not params.blocked_connection_timeout:
                params.blocked_connection_timeout = 300
            connection = pika.BlockingConnection(params)
            channel = connection.channel()

            # Prefetch hint for management/declaration channel; consumer prefetch is set by Dramatiq.
            try:
                prefetch = int(os.getenv("RIVEN_BROKER_PREFETCH", "32"))
                channel.basic_qos(prefetch_count=prefetch)
                # Also try to set on broker instance if supported (best-effort).
                if hasattr(broker, "prefetch"):
                    setattr(broker, "prefetch", prefetch)
            except Exception as _e:
                logger.debug(f"Prefetch setup hint skipped: {_e}")

            # Dead-letter exchange
            dlx_name = "riven.dlx"
            channel.exchange_declare(exchange=dlx_name, exchange_type="direct", durable=True, passive=False)

            # Optional DLQ resource bounding
            _dlq_max_len = os.getenv("RIVEN_DLQ_MAX_LENGTH")
            _dlq_ttl = os.getenv("RIVEN_DLQ_MESSAGE_TTL_MS")

            partition_map = all_partitioned_queue_names()  # base -> count
            logger.debug(f"Declaring partition queues: {partition_map}")

            for base_qname, count in partition_map.items():
                for p in range(max(1, count)):
                    qname = f"{base_qname}.p{p}"
                    dlq_name = f"{qname}.dlq"

                    # If the main queue already exists (any args), do not redeclare to avoid PRECONDITION errors.
                    try:
                        channel.queue_declare(queue=qname, passive=True)
                        logger.debug(f"Queue exists, skipping declare: {qname}")
                        continue
                    except Exception:
                        pass

                    dlq_args = {"x-queue-type": "quorum"}
                    try:
                        if _dlq_max_len:
                            dlq_args["x-max-length"] = int(_dlq_max_len)
                    except ValueError:
                        logger.warning(f"Invalid RIVEN_DLQ_MAX_LENGTH: {_dlq_max_len}")
                    try:
                        if _dlq_ttl:
                            dlq_args["x-message-ttl"] = int(_dlq_ttl)
                    except ValueError:
                        logger.warning(f"Invalid RIVEN_DLQ_MESSAGE_TTL_MS: {_dlq_ttl}")

                    # DLQ per partition (quorum, durable)
                    try:
                        channel.queue_declare(
                            queue=dlq_name,
                            durable=True,
                            arguments=dlq_args,
                            passive=False,
                        )
                        channel.queue_bind(exchange=dlx_name, queue=dlq_name, routing_key=dlq_name)
                    except Exception as _e:
                        logger.debug(f"DLQ declare/bind skipped for {dlq_name}: {_e}")

                    # Main queue (quorum, dead-letter to partition DLQ)
                    try:
                        channel.queue_declare(
                            queue=qname,
                            durable=True,
                            arguments={
                                "x-queue-type": "quorum",
                                # priority not supported on quorum queues
                                "x-dead-letter-exchange": dlx_name,
                                "x-dead-letter-routing-key": dlq_name,
                            },
                            passive=False,
                        )
                    except Exception as _e:
                        logger.warning(f"Main queue declare skipped for {qname}: {_e}")

            logger.info("AMQP infrastructure declared: quorum queues + DLQs + DLX")
            return broker
        except pika.exceptions.ChannelClosedByBroker as e:  # type: ignore[attr-defined]
            # Likely argument mismatch with existing queue/exchange definitions.
            logger.error(
                f"AMQP declaration failed due to broker channel close (arg mismatch?): {e}. "
                f"Check existing queues/exchanges for incompatible settings (e.g., quorum vs classic, DLX)."
            )
            break  # Retries won’t fix argument mismatches
        except Exception as e:
            if attempt < max_attempts:
                delay = base_backoff * (2 ** (attempt - 1))
                logger.warning(f"AMQP declaration attempt {attempt}/{max_attempts} failed: {e}. Retrying in {delay:.1f}s...")
                time.sleep(delay)
                continue
            else:
                logger.warning(f"AMQP infrastructure declaration failed/skipped after {attempt} attempts: {e}")
        finally:
            try:
                if connection and connection.is_open:
                    connection.close()
            except Exception:
                pass
    # Fallthrough: broker is still returned so app can continue, but infra may be incomplete.
    return broker



def test_broker_connection() -> bool:
    """
    Test a TCP connection to LavinMQ/RabbitMQ without declaring queues.

    Returns:
        True if a connection to the broker can be opened and closed; otherwise False.
    """
    from program.settings.manager import settings_manager

    try:
        base_url = os.getenv("RIVEN_LAVINMQ_URL", settings_manager.settings.lavinmq_url)
        broker_url = _augment_amqp_url(base_url)
        params = pika.URLParameters(broker_url)
        # Also ensure heartbeat and timeouts are set for this probe
        if not params.heartbeat:
            params.heartbeat = 30
        if not params.blocked_connection_timeout:
            params.blocked_connection_timeout = 300
        connection = pika.BlockingConnection(params)
        connection.close()
        logger.info(f"Successfully connected to LavinMQ broker!")
        return True
    except Exception as e:
        logger.error(f"Failed to connect to LavinMQ broker: {e}")
        return False


def verify_broker_config(strict: bool = True) -> bool:
    """Ensure broker is RabbitmqBroker with declare_queues=False.

    If strict is True, raise on misconfiguration; otherwise warn and return False.
    """
    try:
        b = dramatiq.get_broker()
    except Exception as e:
        logger.error(f"verify_broker_config: failed to get broker: {e}")
        if strict:
            raise
        return False
    ok = isinstance(b, RabbitmqBroker) and getattr(b, "declare_queues", None) is False
    if not ok:
        msg = "Broker misconfigured: must be RabbitmqBroker with declare_queues=False"
        if strict:
            logger.error(msg)
            raise RuntimeError(msg)
        else:
            logger.warning(msg)
            return False
    return True

def get_broker() -> Optional[dramatiq.Broker]:
    """
    Get the configured broker if present; otherwise return None.

    Returns:
        The current Dramatiq broker instance or None.
    """
    try:
        return dramatiq.get_broker()
    except Exception as e:
        logger.debug(f"get_broker() failed: {e}")
        return None
