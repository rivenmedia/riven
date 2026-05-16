"""Thread-safe cumulative I/O metrics for VFS origin/usefulness stats (API + UI).

Lives under streaming/ to avoid importing program.services.filesystem (see package __init__)
while program.services.downloaders still initializes — prevents circular imports via MediaStream.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any


@dataclass
class VfsIoMetrics:
    """Counts network ingress vs client bytes served (warm cache_hit vs cold paths)."""

    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    network_bytes_ingested: int = 0
    client_bytes_served_warm: int = 0
    client_bytes_served_cold: int = 0

    def add_network(self, n: int) -> None:
        if n <= 0:
            return
        with self._lock:
            self.network_bytes_ingested += n

    def record_client_served(self, n: int, *, warm: bool) -> None:
        if n <= 0:
            return
        with self._lock:
            if warm:
                self.client_bytes_served_warm += n
            else:
                self.client_bytes_served_cold += n

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            warm = self.client_bytes_served_warm
            cold = self.client_bytes_served_cold
            net = self.network_bytes_ingested
        total_client = warm + cold
        ratio: float | None
        if total_client > 0:
            ratio = warm / total_client
        else:
            ratio = None
        return {
            "network_bytes_ingested": net,
            "client_bytes_served_warm": warm,
            "client_bytes_served_cold": cold,
            "client_warm_byte_ratio": ratio,
        }


class _NoOpVfsIoMetrics:
    __slots__ = ()

    def add_network(self, n: int) -> None:
        pass

    def record_client_served(self, n: int, *, warm: bool) -> None:
        pass


NOOP_VFS_IO_METRICS: _NoOpVfsIoMetrics = _NoOpVfsIoMetrics()
