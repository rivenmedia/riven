"""RivenVFS implementation"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .db import VFSDatabase

__all__ = ["RivenVFS", "VFSDatabase"]

if TYPE_CHECKING:
    from .rivenvfs import RivenVFS


def __getattr__(name: str):
    if name == "RivenVFS":
        from .rivenvfs import RivenVFS

        return RivenVFS
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
