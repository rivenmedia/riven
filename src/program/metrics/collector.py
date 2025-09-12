"""
Lightweight Prometheus-style metrics collector without external dependencies.

Exposes helpers to record counters and histograms in process memory and render
text exposition format at /metrics.
"""
from __future__ import annotations

import threading
import time
from collections import defaultdict
from typing import Dict, Iterable, List, Mapping, MutableMapping, Optional, Tuple

from loguru import logger

# Histogram default buckets (seconds) similar to Prometheus defaults
DEFAULT_BUCKETS: Tuple[float, ...] = (
    0.005, 0.01, 0.025, 0.05, 0.1,
    0.25, 0.5, 1.0, 2.5, 5.0, 10.0,
)


class _Counter:
    def __init__(self, name: str, help_text: str, label_names: Tuple[str, ...]) -> None:
        self.name = name
        self.help = help_text
        self.label_names = label_names
        self._values: Dict[Tuple[str, ...], int] = defaultdict(int)
        self._lock = threading.Lock()

    def inc(self, labels: Mapping[str, str], value: int = 1) -> None:
        key = tuple(labels.get(k, "") for k in self.label_names)
        with self._lock:
            self._values[key] += value

    def render(self) -> str:
        lines = [f"# HELP {self.name} {self.help}", f"# TYPE {self.name} counter"]
        for key, val in self._values.items():
            label_str = ",".join(f"{k}=\"{v}\"" for k, v in zip(self.label_names, key) if v)
            if label_str:
                lines.append(f"{self.name}{{{label_str}}} {val}")
            else:
                lines.append(f"{self.name} {val}")
        return "\n".join(lines)


class _Histogram:
    def __init__(self, name: str, help_text: str, label_names: Tuple[str, ...], buckets: Tuple[float, ...] = DEFAULT_BUCKETS) -> None:
        self.name = name
        self.help = help_text
        self.label_names = label_names
        self.buckets = tuple(sorted(buckets))
        self._counts: Dict[Tuple[str, ...], List[int]] = defaultdict(lambda: [0] * (len(self.buckets) + 1))  # last is +Inf
        self._sum: Dict[Tuple[str, ...], float] = defaultdict(float)
        self._count: Dict[Tuple[str, ...], int] = defaultdict(int)
        self._lock = threading.Lock()

    def observe(self, labels: Mapping[str, str], value: float) -> None:
        key = tuple(labels.get(k, "") for k in self.label_names)
        with self._lock:
            placed = False
            for i, b in enumerate(self.buckets):
                if value <= b:
                    self._counts[key][i] += 1
                    placed = True
                    break
            if not placed:
                self._counts[key][-1] += 1
            self._sum[key] += value
            self._count[key] += 1

    def render(self) -> str:
        lines = [f"# HELP {self.name} {self.help}", f"# TYPE {self.name} histogram"]
        for key, counts in self._counts.items():
            label_base = {k: v for k, v in zip(self.label_names, key) if v}
            cum = 0
            for i, b in enumerate(self.buckets):
                cum += counts[i]
                labels = ",".join([*(f"{k}=\"{v}\"" for k, v in label_base.items()), f"le=\"{b}\""])
                lines.append(f"{self.name}_bucket{{{labels}}} {cum}")
            cum += counts[-1]
            labels = ",".join([*(f"{k}=\"{v}\"" for k, v in label_base.items()), "le=\"+Inf\""])
            lines.append(f"{self.name}_bucket{{{labels}}} {cum}")
            # sum & count
            label_str = ",".join(f"{k}=\"{v}\"" for k, v in label_base.items())
            lines.append(f"{self.name}_sum{{{label_str}}} {self._sum[key]}")
            lines.append(f"{self.name}_count{{{label_str}}} {self._count[key]}")
        return "\n".join(lines)


class MetricsRegistry:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._counters: Dict[str, _Counter] = {}
        self._histograms: Dict[str, _Histogram] = {}
        # timings
        self._enqueue_times: Dict[str, float] = {}
        self._start_times: Dict[str, float] = {}

    def counter(self, name: str, help_text: str, label_names: Iterable[str]) -> _Counter:
        with self._lock:
            if name not in self._counters:
                self._counters[name] = _Counter(name, help_text, tuple(label_names))
            return self._counters[name]

    def histogram(self, name: str, help_text: str, label_names: Iterable[str], buckets: Tuple[float, ...] = DEFAULT_BUCKETS) -> _Histogram:
        with self._lock:
            if name not in self._histograms:
                self._histograms[name] = _Histogram(name, help_text, tuple(label_names), buckets=buckets)
            return self._histograms[name]

    def render(self) -> str:
        parts: List[str] = []
        with self._lock:
            for m in [*self._counters.values(), *self._histograms.values()]:
                try:
                    parts.append(m.render())
                except Exception as e:
                    logger.debug(f"Metric render failed: {e}")
        return "\n".join(parts) + "\n"

    # Convenience helpers specific to queue metrics
    def mark_enqueued(self, job_id: str, job_type: str, partition: str) -> None:
        self._enqueue_times[job_id] = time.time()
        self.counter("jobs_enqueued_total", "Total jobs enqueued", ("job_type", "partition")).inc(
            {"job_type": job_type, "partition": partition}
        )

    def mark_started(self, job_id: str, job_type: str, partition: str) -> None:
        now = time.time()
        self._start_times[job_id] = now
        self.counter("jobs_started_total", "Total jobs started", ("job_type", "partition")).inc(
            {"job_type": job_type, "partition": partition}
        )
        t0 = self._enqueue_times.pop(job_id, None)
        if t0 is not None:
            self.histogram(
                "enqueue_to_start_seconds",
                "Time from enqueue to start",
                ("job_type", "partition"),
            ).observe({"job_type": job_type, "partition": partition}, max(0.0, now - t0))

    def mark_completed(self, job_id: str, job_type: str, partition: str, success: bool) -> None:
        now = time.time()
        self.counter("jobs_completed_total", "Total jobs completed", ("job_type", "partition", "success")).inc(
            {"job_type": job_type, "partition": partition, "success": str(bool(success)).lower()}
        )
        t1 = self._start_times.pop(job_id, None)
        if t1 is not None:
            self.histogram(
                "start_to_complete_seconds",
                "Time from start to completion",
                ("job_type", "partition"),
            ).observe({"job_type": job_type, "partition": partition}, max(0.0, now - t1))

    def mark_retry(self, job_type: str, partition: str) -> None:
        self.counter("jobs_retry_total", "Total delayed retries scheduled", ("job_type", "partition")).inc(
            {"job_type": job_type, "partition": partition}
        )

    def mark_dlq(self, job_type: str, partition: str) -> None:
        self.counter("jobs_dlq_total", "Total jobs sent to DLQ", ("job_type", "partition")).inc(
            {"job_type": job_type, "partition": partition}
        )


metrics_registry = MetricsRegistry()


def parse_partition_from_queue(queue_name: str) -> str:
    """Extract partition label like 'p0' from a queue name 'downloader.p0'."""
    try:
        parts = queue_name.split(".")
        for p in parts[::-1]:
            if p.startswith("p") and p[1:].isdigit():
                return p
    except Exception:
        pass
    return "p0"

