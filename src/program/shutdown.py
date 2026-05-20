"""Process-wide shutdown flag for cooperative cancellation."""

import os
import threading

from program.utils.logging import logger

_shutting_down = threading.Event()
_force_exit_timer: threading.Timer | None = None
_force_exit_lock = threading.Lock()

# Hard cap so SIGINT/SIGTERM never leaves a zombie python (thread-pool jobs, FUSE, etc.)
FORCE_EXIT_SECONDS = 5.0


def request_shutdown() -> None:
    _shutting_down.set()


def shutting_down() -> bool:
    return _shutting_down.is_set()


def schedule_force_exit(seconds: float = FORCE_EXIT_SECONDS) -> None:
    """Exit the process if graceful shutdown has not finished in time."""

    def _force() -> None:
        logger.warning(
            f"Shutdown did not finish within {seconds:.0f}s; forcing process exit"
        )
        os._exit(0)

    global _force_exit_timer
    with _force_exit_lock:
        if _force_exit_timer is not None:
            return
        _force_exit_timer = threading.Timer(seconds, _force)
        _force_exit_timer.daemon = True
        _force_exit_timer.start()
