"""Unified rate limiting and circuit breaking for the application."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from typing import TYPE_CHECKING, Generator
import threading
import time

import httpx
from loguru import logger

if TYPE_CHECKING:
    from program.services.downloaders.shared import DownloaderBase


class CircuitBreakerOpen(RuntimeError):
    """Raised when a circuit breaker is OPEN and requests should fail fast."""

    def __init__(self, name: str, *, retry_after: float | None = None):
        super().__init__(f"Circuit breaker OPEN for {name}")
        self.name = name
        self.retry_after = retry_after


class TokenBucket:
    """Thread-safe token bucket rate limiter."""

    def __init__(self, rate: float, capacity: float | int, name: str | None = None):
        self.name = name
        self.rate: float = float(rate)
        self.capacity: float = float(capacity)
        self.tokens: float = float(capacity)
        self.last_refill: float = time.monotonic()
        self._lock = threading.Lock()

    def _refill(self, now: float | None = None) -> None:
        if now is None:
            now = time.monotonic()
        elapsed = now - self.last_refill
        if elapsed <= 0:
            return
        self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)
        self.last_refill = now

    def wait(self, tokens: float = 1) -> None:
        need = float(tokens)
        while True:
            with self._lock:
                now = time.monotonic()
                self._refill(now)
                if self.tokens >= need:
                    self.tokens -= need
                    return
                deficit = max(0.0, need - self.tokens)
                sleep_for = deficit / self.rate if self.rate > 0 else 0.05
            time.sleep(sleep_for)

    def try_consume(self, tokens: float = 1) -> bool:
        need = float(tokens)
        with self._lock:
            self._refill()
            if self.tokens >= need:
                self.tokens -= need
                return True
            return False

    def seconds_until_token(self, tokens: float = 1) -> float:
        need = float(tokens)
        with self._lock:
            now = time.monotonic()
            self._refill(now)
            if self.tokens >= need:
                return 0.0
            deficit = max(0.0, need - self.tokens)
            return deficit / self.rate if self.rate > 0 else 0.0

    def snapshot_utilization(self) -> tuple[float, float, float, float]:
        """Return (tokens, capacity, rate, utilization_pct)."""
        with self._lock:
            now = time.monotonic()
            self._refill(now)
            tokens = self.tokens
            cap = self.capacity
            rate = self.rate
        util = 0.0
        if cap > 0:
            util = max(0.0, min(100.0, 100.0 * (1.0 - tokens / cap)))
        return tokens, cap, rate, util


class _CircuitBreaker:
    def __init__(
        self,
        key: str,
        *,
        failure_threshold: int,
        base_recovery_seconds: float,
        max_recovery_seconds: float,
    ):
        self.key = key
        self.failure_threshold = failure_threshold
        self.base_recovery_seconds = base_recovery_seconds
        self.max_recovery_seconds = max_recovery_seconds
        self.failures = 0
        self.state = "CLOSED"
        self.last_failure_time: float | None = None
        self.recovery_seconds = base_recovery_seconds
        self.trip_streak = 0
        self._lock = threading.Lock()

    def before_request(self) -> None:
        with self._lock:
            if self.state == "OPEN" and self.last_failure_time is not None:
                elapsed = time.monotonic() - self.last_failure_time
                if elapsed > self.recovery_seconds:
                    self.state = "HALF_OPEN"
                    logger.debug(f"Breaker for {self.key} HALF_OPEN (probe)")
                else:
                    remaining = max(0.0, self.recovery_seconds - elapsed)
                    raise CircuitBreakerOpen(self.key, retry_after=remaining)

    def record_success(self) -> None:
        with self._lock:
            if self.state in ("HALF_OPEN", "OPEN"):
                self._reset_locked()
            elif self.state == "CLOSED":
                self.failures = 0

    def record_failure(self, *, retry_after: float | None = None) -> None:
        with self._lock:
            self.failures += 1
            self.last_failure_time = time.monotonic()
            if self.state == "HALF_OPEN" or self.failures >= self.failure_threshold:
                self._trip_locked(retry_after)

    def trip(self, *, retry_after: float | None = None) -> None:
        with self._lock:
            self._trip_locked(retry_after)

    def _trip_locked(self, retry_after: float | None) -> None:
        self.trip_streak += 1
        if retry_after is not None:
            backoff = min(self.max_recovery_seconds, float(retry_after))
        else:
            backoff = min(
                self.max_recovery_seconds,
                self.base_recovery_seconds * (2 ** max(0, self.trip_streak - 1)),
            )
        self.recovery_seconds = backoff
        self.state = "OPEN"
        self.last_failure_time = time.monotonic()
        logger.warning(
            f"Circuit breaker OPEN for {self.key} (recovery {backoff:.0f}s)"
        )

    def _reset_locked(self) -> None:
        self.failures = 0
        self.state = "CLOSED"
        self.last_failure_time = None
        self.recovery_seconds = self.base_recovery_seconds
        self.trip_streak = 0
        logger.info(f"Circuit breaker reset to CLOSED for {self.key}")

    def recovery_in_seconds(self) -> float:
        with self._lock:
            if self.state != "OPEN" or self.last_failure_time is None:
                return 0.0
            elapsed = time.monotonic() - self.last_failure_time
            return max(0.0, self.recovery_seconds - elapsed)


@dataclass(frozen=True)
class ResourceSpec:
    label: str
    owner: str = ""
    rate: float | None = None
    capacity: float | None = None
    priority: str = "normal"
    warn_at_pct: float = 80.0
    breaker_enabled: bool = True
    failure_threshold: int = 5
    base_recovery_seconds: float = 15.0
    max_recovery_seconds: float = 600.0


@dataclass(frozen=True)
class LimiterSnapshot:
    key: str
    label: str
    owner: str
    tokens: float
    capacity: float
    rate_per_second: float
    utilization_pct: float
    next_token_in_seconds: float
    priority: str
    warn_at_pct: float
    breaker_state: str
    breaker_failures: int
    breaker_recovery_in_seconds: float


@dataclass
class _Resource:
    spec: ResourceSpec
    bucket: TokenBucket | None
    breaker: _CircuitBreaker | None
    last_activity_at: float | None = None


class RateLimitService:
    """Application-wide rate limits and circuit breakers keyed by string."""

    def __init__(self) -> None:
        self._resources: dict[str, _Resource] = {}
        self._lock = threading.Lock()

    def register(self, key: str, spec: ResourceSpec, *, replace: bool = False) -> None:
        with self._lock:
            if key in self._resources and not replace:
                logger.debug(f"Rate limit key already registered: {key}")
                return

            bucket = None
            if spec.rate is not None and spec.capacity is not None:
                bucket = TokenBucket(spec.rate, spec.capacity, name=key)

            breaker = None
            if spec.breaker_enabled:
                breaker = _CircuitBreaker(
                    key,
                    failure_threshold=spec.failure_threshold,
                    base_recovery_seconds=spec.base_recovery_seconds,
                    max_recovery_seconds=spec.max_recovery_seconds,
                )

            self._resources[key] = _Resource(spec=spec, bucket=bucket, breaker=breaker)

    @staticmethod
    def _touch_activity(resource: _Resource) -> None:
        resource.last_activity_at = time.monotonic()

    def register_many(self, specs: dict[str, ResourceSpec], *, replace: bool = False) -> None:
        for key, spec in specs.items():
            self.register(key, spec, replace=replace)

    def enter(self, key: str, tokens: float = 1) -> None:
        resource = self._get(key)
        self._touch_activity(resource)
        if resource.breaker:
            resource.breaker.before_request()
        if resource.bucket:
            resource.bucket.wait(tokens)

    def enter_many(self, keys: list[str], tokens: float = 1) -> None:
        for key in keys:
            self.enter(key, tokens)

    def try_acquire(self, key: str, tokens: float = 1) -> bool:
        resource = self._get(key)
        self._touch_activity(resource)
        if resource.breaker:
            try:
                resource.breaker.before_request()
            except CircuitBreakerOpen:
                return False
        if resource.bucket and not resource.bucket.try_consume(tokens):
            return False
        return True

    def record_success(self, key: str) -> None:
        resource = self._get(key)
        self._touch_activity(resource)
        if resource.breaker:
            resource.breaker.record_success()

    def record_failure(self, key: str, *, retry_after: float | None = None) -> None:
        resource = self._get(key)
        self._touch_activity(resource)
        if not resource.breaker:
            return
        if retry_after is not None:
            resource.breaker.trip(retry_after=retry_after)
        else:
            resource.breaker.record_failure()

    def record_many_success(self, keys: list[str]) -> None:
        for key in keys:
            self.record_success(key)

    def record_many_failure(
        self, keys: list[str], *, retry_after: float | None = None
    ) -> None:
        for key in keys:
            self.record_failure(key, retry_after=retry_after)

    def trip(self, key: str, *, retry_after: float | None = None) -> None:
        resource = self._get(key)
        self._touch_activity(resource)
        if resource.breaker:
            resource.breaker.trip(retry_after=retry_after)

    @contextmanager
    def acquire(self, key: str, tokens: float = 1) -> Generator[None, None, None]:
        self.enter(key, tokens)
        try:
            yield
        except Exception:
            self.record_failure(key)
            raise
        else:
            self.record_success(key)

    def seconds_until_ready(self, key: str, tokens: float = 1) -> float:
        resource = self._get(key)
        wait = 0.0
        if resource.bucket:
            wait = max(wait, resource.bucket.seconds_until_token(tokens))
        if resource.breaker:
            wait = max(wait, resource.breaker.recovery_in_seconds())
        return wait

    def snapshot(self, key: str) -> LimiterSnapshot | None:
        with self._lock:
            resource = self._resources.get(key)
        if resource is None:
            return None
        return self._snapshot_resource(key, resource)

    def snapshot_all(
        self,
        owner: str | None = None,
        *,
        active_within_seconds: float | None = None,
    ) -> list[LimiterSnapshot]:
        with self._lock:
            items = list(self._resources.items())

        if active_within_seconds is not None:
            now = time.monotonic()
            items = [
                (k, r)
                for k, r in items
                if r.last_activity_at is not None
                and (now - r.last_activity_at) <= active_within_seconds
            ]

        snapshots = [self._snapshot_resource(k, r) for k, r in items]
        if owner:
            snapshots = [s for s in snapshots if s.owner == owner]
        return sorted(snapshots, key=lambda s: s.key)

    def keys(self, prefix: str = "") -> list[str]:
        with self._lock:
            all_keys = list(self._resources.keys())
        if not prefix:
            return sorted(all_keys)
        return sorted(k for k in all_keys if k.startswith(prefix))

    def _get(self, key: str) -> _Resource:
        with self._lock:
            resource = self._resources.get(key)
        if resource is None:
            raise KeyError(f"Rate limit key not registered: {key}")
        return resource

    def _snapshot_resource(self, key: str, resource: _Resource) -> LimiterSnapshot:
        spec = resource.spec
        if resource.bucket:
            tokens, capacity, rate, util = resource.bucket.snapshot_utilization()
            next_tok = resource.bucket.seconds_until_token(1)
        else:
            tokens, capacity, rate, util, next_tok = 0.0, 0.0, 0.0, 0.0, 0.0

        breaker_state = "CLOSED"
        breaker_failures = 0
        breaker_recovery = 0.0
        if resource.breaker:
            breaker_state = resource.breaker.state
            breaker_failures = resource.breaker.failures
            breaker_recovery = resource.breaker.recovery_in_seconds()

        return LimiterSnapshot(
            key=key,
            label=spec.label or key,
            owner=spec.owner,
            tokens=tokens,
            capacity=capacity,
            rate_per_second=rate,
            utilization_pct=util,
            next_token_in_seconds=next_tok,
            priority=spec.priority,
            warn_at_pct=spec.warn_at_pct,
            breaker_state=breaker_state,
            breaker_failures=breaker_failures,
            breaker_recovery_in_seconds=breaker_recovery,
        )


_service: RateLimitService | None = None
_service_lock = threading.Lock()


def get_rate_limit_service() -> RateLimitService:
    global _service
    with _service_lock:
        if _service is None:
            _service = RateLimitService()
        return _service


def bootstrap_rate_limit_service() -> RateLimitService:
    """Create and register the global rate limit service in kink di."""
    from kink import di

    svc = get_rate_limit_service()
    di[RateLimitService] = svc
    return svc


def register_http_limit(
    owner: str,
    domain: str,
    *,
    rate: float,
    capacity: float,
    label: str | None = None,
) -> str:
    """Register a standard per-host API limit; returns the limit key."""

    key = f"{owner}.api"
    get_rate_limit_service().register(
        key,
        ResourceSpec(
            label=label or f"API ({domain})",
            owner=owner,
            rate=rate,
            capacity=capacity,
        ),
    )
    return key


def http_rate_limit_map(owner: str, domain: str) -> dict[str, list[str]]:
    """Build a SmartSession rate_limit_map entry for a host."""

    return {domain: [f"{owner}.api"]}


def provider_limit_key(provider: str) -> str:
    """Rate-limit / circuit-breaker key for a debrid provider API (e.g. ``torbox`` → ``torbox.api``)."""

    return f"{provider}.api"


def provider_stream_limit_key(provider: str) -> str:
    """Circuit-breaker key for CDN/VFS media streaming (e.g. ``torbox`` → ``torbox.stream``)."""

    return f"{provider}.stream"


def parse_retry_after(
    response: httpx.Response,
    *,
    fallback: float = 1.0,
) -> float:
    """Parse ``Retry-After`` from an HTTP response (seconds or HTTP-date)."""

    try:
        ra = response.headers.get("Retry-After")
    except Exception:
        ra = None

    if ra:
        try:
            return max(0.0, float(int(ra)))
        except Exception:
            try:
                dt = parsedate_to_datetime(ra)
                return max(0.0, float(int(round(dt.timestamp() - time.time()))))
            except Exception:
                pass

    return fallback


def _is_circuit_open_for_key(key: str) -> bool:
    try:
        snap = get_rate_limit_service().snapshot(key)
    except KeyError:
        return False
    return snap is not None and snap.breaker_state == "OPEN"


def is_circuit_open(provider: str) -> bool:
    """Return True when the provider API circuit breaker is OPEN."""

    return _is_circuit_open_for_key(provider_limit_key(provider))


def is_stream_circuit_open(provider: str) -> bool:
    """Return True when the provider media-stream circuit breaker is OPEN."""

    return _is_circuit_open_for_key(provider_stream_limit_key(provider))


def _record_limit_failure(
    key: str,
    provider: str,
    *,
    retry_after: float | None = None,
) -> RateLimitService | None:
    rl = get_rate_limit_service()
    try:
        rl.record_failure(key, retry_after=retry_after)
    except KeyError:
        logger.debug(f"No rate limit registered for provider {provider!r} key {key}")
        return None
    return rl


def report_provider_stream_rate_limited(
    provider: str,
    *,
    retry_after: float | None = None,
) -> None:
    """
    Trip the media-stream circuit breaker for a provider.

    Does not affect the API limiter or downloader job cooldown.
    """

    _record_limit_failure(
        provider_stream_limit_key(provider),
        provider,
        retry_after=retry_after,
    )


def report_provider_rate_limited(
    provider: str,
    *,
    retry_after: float | None = None,
) -> None:
    """
    Trip the provider API circuit breaker and apply downloader cooldown when available.

    Used for debrid API paths that do not go through SmartSession.
    """

    key = provider_limit_key(provider)
    rl = _record_limit_failure(key, provider, retry_after=retry_after)
    if rl is None:
        return

    _notify_downloader_rate_limited(provider, key, rl, retry_after)


def _notify_downloader_rate_limited(
    provider: str,
    limit_key: str,
    rl: RateLimitService,
    retry_after: float | None,
) -> None:
    try:
        from kink import di

        from program.services.downloaders import Downloader
    except Exception:
        return

    try:
        downloader = di[Downloader]
    except Exception:
        return

    service: DownloaderBase | None = next(
        (s for s in downloader.initialized_services if s.key == provider),
        None,
    )
    if service is None:
        return

    remaining = (
        retry_after
        if retry_after is not None
        else rl.seconds_until_ready(limit_key)
    )
    exc = CircuitBreakerOpen(limit_key, retry_after=remaining)
    downloader._on_circuit_breaker_open(
        service,
        exc,
        context="CDN/VFS rate limited",
    )
