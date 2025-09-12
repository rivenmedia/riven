"""
Worker entrypoint for Dramatiq.

- Configures the broker exactly once.
- Imports actors so Dramatiq discovers them after the broker is ready.
"""

from __future__ import annotations

from loguru import logger

from program.queue.broker import setup_dramatiq_broker

# Configure the broker first (idempotent).
setup_dramatiq_broker()
logger.info("Dramatiq broker configured in worker entrypoint.")

# Importing registers actor definitions with Dramatiq.
# Keep this import *after* setup_dramatiq_broker().
# Also import callbacks to register DLQ failure handlers.
import program.queue.worker_actors  # noqa: F401
import program.queue.callbacks  # noqa: F401
