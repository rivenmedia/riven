"""Detect whether the optional pyfuse3 (FUSE) extra is installed."""

from __future__ import annotations

import importlib.util
from functools import lru_cache


@lru_cache
def is_fuse_available() -> bool:
    return importlib.util.find_spec("pyfuse3") is not None
