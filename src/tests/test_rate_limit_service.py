import time
from unittest.mock import patch

import httpx
import pytest

from program.services.rate_limit import (
    CircuitBreakerOpen,
    RateLimitService,
    ResourceSpec,
    is_circuit_open,
    parse_retry_after,
    provider_limit_key,
    report_provider_rate_limited,
)


@pytest.fixture
def rl():
    return RateLimitService()


def test_register_and_wait_spacing(rl):
    rl.register(
        "test.bucket",
        ResourceSpec(label="Test", owner="test", rate=1.0, capacity=1),
    )
    t0 = time.monotonic()
    rl.enter("test.bucket")
    rl.enter("test.bucket")
    elapsed = time.monotonic() - t0
    assert elapsed >= 0.08


def test_circuit_breaker_trips_and_recovers(rl):
    rl.register(
        "test.api",
        ResourceSpec(
            label="API",
            owner="test",
            rate=100.0,
            capacity=100,
            failure_threshold=2,
            base_recovery_seconds=0.1,
            max_recovery_seconds=1.0,
        ),
    )
    rl.record_failure("test.api")
    rl.record_failure("test.api")
    with pytest.raises(CircuitBreakerOpen):
        rl.enter("test.api")
    time.sleep(0.15)
    rl.enter("test.api")
    rl.record_success("test.api")
    snap = rl.snapshot("test.api")
    assert snap is not None
    assert snap.breaker_state == "CLOSED"


def test_trip_with_retry_after(rl):
    rl.register(
        "test.scarce",
        ResourceSpec(
            label="Scarce",
            owner="test",
            rate=1 / 3600,
            capacity=1,
            priority="scarce",
            failure_threshold=1,
            base_recovery_seconds=5.0,
        ),
    )
    rl.trip("test.scarce", retry_after=0.2)
    with pytest.raises(CircuitBreakerOpen) as exc:
        rl.enter("test.scarce")
    assert exc.value.retry_after is not None
    assert exc.value.retry_after <= 0.25


def test_snapshot_all_active_within_seconds(rl):
    rl.register(
        "used.api",
        ResourceSpec(label="Used", owner="used", rate=5.0, capacity=10),
    )
    rl.register(
        "idle.api",
        ResourceSpec(label="Idle", owner="idle", rate=5.0, capacity=10),
    )
    rl.enter("used.api")

    assert len(rl.snapshot_all(active_within_seconds=1800.0)) == 1
    assert rl.snapshot_all(active_within_seconds=1800.0)[0].key == "used.api"
    assert len(rl.snapshot_all(active_within_seconds=None)) == 2


def test_snapshot_all_by_owner(rl):
    rl.register(
        "torbox.api",
        ResourceSpec(label="API", owner="torbox", rate=5.0, capacity=10),
    )
    rl.register(
        "torbox.createtorrent",
        ResourceSpec(
            label="Add torrent",
            owner="torbox",
            rate=60 / 3600,
            capacity=1,
            priority="scarce",
        ),
    )
    all_snap = rl.snapshot_all()
    assert len(all_snap) == 2
    torbox_only = rl.snapshot_all(owner="torbox")
    assert len(torbox_only) == 2
    assert torbox_only[0].utilization_pct >= 0


def test_provider_limit_key():
    assert provider_limit_key("torbox") == "torbox.api"


def test_parse_retry_after_seconds():
    response = httpx.Response(429, headers={"Retry-After": "42"})
    assert parse_retry_after(response, fallback=1.0) == 42.0


def test_report_provider_rate_limited_trips_breaker(monkeypatch):
    rl = RateLimitService()
    monkeypatch.setattr("program.services.rate_limit._service", rl)
    rl.register(
        "torbox.api",
        ResourceSpec(label="API", owner="torbox", rate=5.0, capacity=10),
    )

    report_provider_rate_limited("torbox", retry_after=30.0)

    snap = rl.snapshot("torbox.api")
    assert snap is not None
    assert snap.breaker_state == "OPEN"
    assert is_circuit_open("torbox")


def test_report_provider_rate_limited_unknown_provider(monkeypatch):
    rl = RateLimitService()
    monkeypatch.setattr("program.services.rate_limit._service", rl)

    report_provider_rate_limited("unknown_provider", retry_after=10.0)

    assert rl.snapshot("unknown_provider.api") is None
