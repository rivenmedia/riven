"""Process-wide shutdown flag for cooperative cancellation."""

import threading

_shutting_down = threading.Event()


def request_shutdown() -> None:
    _shutting_down.set()


def shutting_down() -> bool:
    return _shutting_down.is_set()
