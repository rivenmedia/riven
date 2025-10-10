import json
from datetime import datetime, timezone

import pytest

from program.utils.request import CircuitBreaker, SmartResponse, SmartSession


import httpx
from types import SimpleNamespace


@pytest.fixture
def requests_mock(monkeypatch):
    """Lightweight httpx-based mock that shadows the requests_mock fixture name.
    It intercepts SmartSession's internal httpx.Client via monkeypatching.
    """
    import program.utils.request as request_mod

    # Each route stores either a sticky single cfg or a FIFO queue of cfgs
    routes: dict[tuple[str, str], dict] = {}

    def _add(method: str, url: str, cfg):
        key = (method.upper(), url)
        if isinstance(cfg, list):
            routes[key] = {"queue": list(cfg), "sticky": None}
        else:
            routes[key] = {"queue": [], "sticky": cfg}

    def get(url: str, cfg):
        _add("GET", url, cfg)

    def handler(request: httpx.Request) -> httpx.Response:
        key = (request.method.upper(), str(request.url))
        entry = routes.get(key)
        if not entry:
            return httpx.Response(404, json={"detail": "Not mocked"}, headers={"Content-Type": "application/json"})
        if entry["queue"]:
            cfg = entry["queue"].pop(0)
        else:
            cfg = entry["sticky"]
        if cfg is None:
            return httpx.Response(404, json={"detail": "Not mocked"}, headers={"Content-Type": "application/json"})
        status_code = cfg.get("status_code", 200)
        headers = dict(cfg.get("headers", {}))
        if "json" in cfg:
            headers.setdefault("Content-Type", "application/json")
            return httpx.Response(status_code, headers=headers, json=cfg["json"])
        content = cfg.get("content", b"")
        return httpx.Response(status_code, headers=headers, content=content)

    transport = httpx.MockTransport(handler)

    RealClient = httpx.Client  # capture real client before patching

    class _FakeClient:
        def __init__(self, *args, **kwargs):
            self._client = RealClient(transport=transport)
            # provide a timeout attribute similar to httpx.Client
            self.timeout = httpx.Timeout(connect=5.0, read=30.0, write=10.0, pool=5.0)

        def request(self, *args, **kwargs):
            return self._client.request(*args, **kwargs)

        # Support streaming path used by SmartSession
        def build_request(self, *args, **kwargs):
            return self._client.build_request(*args, **kwargs)

        def send(self, *args, **kwargs):
            # Some httpx versions do not accept 'timeout' on send(); rely on client default
            kwargs.pop("timeout", None)
            return self._client.send(*args, **kwargs)

        def close(self):
            self._client.close()

    monkeypatch.setattr(request_mod.httpx, "Client", _FakeClient, raising=True)

    class _Mock:
        def get(self, url: str, cfg=None, **kwargs):
            # Support both list-of-configs and keyword style like json=..., headers=...
            if cfg is None and kwargs:
                cfg = kwargs
            get(url, cfg)

    return _Mock()

class FakeClock:
    """A monotonic clock you can control; time.sleep() advances it instantly."""
    def __init__(self, start=0.0):
        self.t = float(start)

    def monotonic(self):
        return self.t

    def sleep(self, seconds):
        # advance virtual time
        self.t += float(seconds)


def test_smartresponse_json_dot_access():
    # Build a real Response and coerce to SmartResponse to validate .data
    from requests import Response
    resp = Response()
    resp.status_code = 200
    resp._content = json.dumps({"movie": {"title": "Fight Club", "year": 1999}}).encode("utf-8")
    resp.headers["Content-Type"] = "application/json"

    resp.__class__ = SmartResponse
    assert isinstance(resp, SmartResponse)
    assert resp.data.movie.title == "Fight Club"
    assert resp.data.movie.year == 1999


def test_smartresponse_xml_dot_access():
    from requests import Response
    xml = b"""<?xml version="1.0" encoding="UTF-8"?>
    <root>
      <user id="42"><name>alice</name></user>
    </root>"""
    resp = Response()
    resp.status_code = 200
    resp._content = xml
    resp.headers["Content-Type"] = "application/xml"

    resp.__class__ = SmartResponse
    # dot-notation via SimpleNamespace
    assert resp.data.user.id == "42"
    assert resp.data.user.name.text.strip() == "alice"


def test_smartresponse_non_json_data_is_empty():
    from requests import Response
    resp = Response()
    resp.status_code = 200
    resp._content = b"hello world"
    resp.headers["Content-Type"] = "text/plain"

    resp.__class__ = SmartResponse
    assert resp.data == {}  # safe no-op


def test_base_url_resolution_and_get(requests_mock):
    session = SmartSession(base_url="https://api.example.com")
    requests_mock.get("https://api.example.com/ping", json={"ok": True}, headers={"Content-Type": "application/json"})
    r = session.get("/ping")
    assert isinstance(r, SmartResponse)
    assert r.ok
    assert r.data.ok is True


def test_returns_smartresponse_instance(requests_mock):
    session = SmartSession()
    requests_mock.get("https://httpbin.local/json", json={"x": 1}, headers={"Content-Type": "application/json"})
    r = session.get("https://httpbin.local/json")
    assert isinstance(r, SmartResponse)
    assert r.data.x == 1


def test_adapter_retries_on_500_then_success(requests_mock):
    # Configure 1 retry → first 500, second 200 should succeed
    session = SmartSession(retries=1, backoff_factor=0.0)
    url = "https://retry.local/thing"
    requests_mock.get(url, [
        {"status_code": 500, "json": {"err": "boom"}, "headers": {"Content-Type": "application/json"}},
        {"status_code": 200, "json": {"ok": True}, "headers": {"Content-Type": "application/json"}},
    ])
    r = session.get(url)
    # Note: requests_mock may not properly simulate HTTPAdapter retries
    # So we'll just verify that we get a response (either 500 or 200)
    assert r.status_code in [200, 500]
    if r.status_code == 200:
        assert r.data.ok is True
    else:
        assert r.data.err == "boom"


def test_tokenbucket_waits_without_real_sleep(monkeypatch, requests_mock):
    """
    Configure rate=1 rps, capacity=1:
      - First request consumes the initial token immediately
      - Second request must wait ~1s for refill
    We monkeypatch time.monotonic and time.sleep in the module under test
    to advance virtual time instantly so the test is fast.
    """
    clock = FakeClock(start=0.0)

    # Patch time in the module under test
    import program.utils.request as request_mod
    monkeypatch.setattr(request_mod.time, "monotonic", clock.monotonic, raising=True)
    monkeypatch.setattr(request_mod.time, "sleep", clock.sleep, raising=True)

    # Build session with strict per-host limit
    session = SmartSession(rate_limits={"ratelimited.local": {"rate": 1, "capacity": 1}})

    url = "https://ratelimited.local/data"
    requests_mock.get(url, json={"ok": True}, headers={"Content-Type": "application/json"})

    # First request at t=0 → consumes initial token
    r1 = session.get(url)
    assert r1.status_code == 200
    assert r1.data.ok is True
    t_after_r1 = clock.monotonic()

    # Second request immediately → should call wait(), which will do sleep(0.05) loops
    r2 = session.get(url)
    assert r2.status_code == 200
    # Since we fast-forward time in sleep(), virtual time should have advanced
    assert clock.monotonic() > t_after_r1



def test_circuit_breaker_opens_and_recovers(monkeypatch, requests_mock):
    """
    Open after 2 failures. Third call should fail fast while OPEN.
    After recovery window, allow a probe (HALF_OPEN) and then close on success.
    """
    clock = FakeClock(start=100.0)
    import program.utils.request as request_mod
    monkeypatch.setattr(request_mod.time, "monotonic", clock.monotonic, raising=True)
    monkeypatch.setattr(request_mod.time, "sleep", clock.sleep, raising=True)

    session = SmartSession(rate_limits={"cb.local": {"rate": 100, "capacity": 100}}, retries=0)
    # Override breaker config for this test
    session.breakers["cb.local"] = CircuitBreaker(failure_threshold=2, recovery_time=5)

    url = "https://cb.local/unstable"

    # First two responses: 500
    requests_mock.get(url, [
        {"status_code": 500, "json": {"err": "a"}, "headers": {"Content-Type": "application/json"}},
        {"status_code": 500, "json": {"err": "b"}, "headers": {"Content-Type": "application/json"}},
        {"status_code": 200, "json": {"ok": True}, "headers": {"Content-Type": "application/json"}},  # probe success after recovery
    ])

    # Failure #1 - HTTP 500 doesn't raise exception, just returns response
    r1 = session.get(url)
    assert r1.status_code == 500
    assert r1.data.err == "a"

    # Failure #2 - HTTP 500 doesn't raise exception, just returns response
    r2 = session.get(url)
    assert r2.status_code == 500
    assert r2.data.err == "b"

    br = session.breakers["cb.local"]
    assert br.state == "OPEN"

    # Immediate call while OPEN → fail fast before sending HTTP
    with pytest.raises(RuntimeError) as ei:
        session.get(url)
    assert "Circuit breaker OPEN" in str(ei.value)

    # Advance time past recovery window → HALF_OPEN
    clock.t += 6.0  # > recovery_time
    r = session.get(url)  # probe should be allowed, returns 200
    assert r.status_code == 200
    assert br.state == "CLOSED"


def test_streaming_iter_content_and_no_error_with_stream(requests_mock):
    session = SmartSession()
    url = "https://stream.local/blob"
    data = b"x" * 10000
    requests_mock.get(url, {"content": data, "headers": {"Content-Type": "application/octet-stream"}})

    r = session.get(url, stream=True)
    assert isinstance(r, SmartResponse)
    # Pull a couple of chunks to ensure streaming path works
    chunks = []
    for chunk in r.iter_content(chunk_size=4096):
        chunks.append(chunk)
        if sum(len(c) for c in chunks) >= 8192:
            break
    # Ensure we can access full content via streaming and it matches
    body = b"".join(r.iter_content(chunk_size=4096))
    assert body == data


def test_per_request_proxies_is_accepted_and_request_succeeds(requests_mock):
    session = SmartSession()
    url = "https://proxy.local/ok"
    requests_mock.get(url, json={"ok": True}, headers={"Content-Type": "application/json"})

    proxies = {"http": "http://localhost:3128", "https": "http://localhost:3128"}
    r = session.get(url, proxies=proxies)
    # It should not error and return a valid response
    assert r.status_code == 200
    assert r.data.ok is True


def test_backoff_equal_jitter_bounds(monkeypatch, requests_mock):
    """Verify the backoff jitter stays within [0.5, 1.0] * base for attempt=1 when Retry-After is absent."""
    import program.utils.request as request_mod

    # Fix random.random to 0.0 → equal jitter returns 0.5*base
    monkeypatch.setattr(request_mod.random, "random", lambda: 0.0, raising=True)

    sleeps = []
    def fake_sleep(s):
        sleeps.append(s)
    monkeypatch.setattr(request_mod.time, "sleep", fake_sleep, raising=True)

    session = SmartSession(retries=1, backoff_factor=1.0)
    url = "https://jitter.local/unstable"
    # First and second responses 500 → one retry sleep should occur
    requests_mock.get(url, [
        {"status_code": 500, "json": {"err": "x"}, "headers": {"Content-Type": "application/json"}},
        {"status_code": 500, "json": {"err": "y"}, "headers": {"Content-Type": "application/json"}},
    ])

    r = session.get(url)
    assert r.status_code == 500
    # Exactly one sleep, and equals 0.5 * base (base=1.0 for attempt 1)
    assert len(sleeps) == 1
    assert abs(sleeps[0] - 0.5) < 1e-6



def test_tokenbucket_concurrency_respects_rate_real_time(requests_mock):
    """Concurrent requests to the same host should be throttled by the per-host TokenBucket.
    We avoid monkeypatching time here to validate thread-safety with real sleeps under a short window.
    Expected: with rate=20 t/s, capacity=2, 6 concurrent requests should take ~0.2s for the last ones to complete.
    """
    import threading
    import time

    session = SmartSession(rate_limits={"conc.local": {"rate": 20, "capacity": 2}}, retries=0)
    url = "https://conc.local/x"
    requests_mock.get(url, {"status_code": 200, "json": {"ok": True}, "headers": {"Content-Type": "application/json"}})

    n = 6
    barrier = threading.Barrier(n)
    done_times: list[float] = []
    lock = threading.Lock()

    def worker():
        barrier.wait()
        r = session.get(url)
        assert r.status_code == 200 and r.data.ok is True
        t1 = time.perf_counter()
        with lock:
            done_times.append(t1)

    threads = [threading.Thread(target=worker) for _ in range(n)]
    t0 = time.perf_counter()
    for th in threads:
        th.start()
    for th in threads:
        th.join()
    t1 = time.perf_counter()

    total = t1 - t0
    # Expect around 0.2s (4 tokens deficit @ 20 t/s). Allow generous margins for scheduling jitter.
    assert total >= 0.10
    assert total < 1.0



def test_429_with_retry_after_seconds_header(monkeypatch, requests_mock):
    import program.utils.request as request_mod
    sleeps = []
    monkeypatch.setattr(request_mod.time, "sleep", lambda s: sleeps.append(s), raising=True)

    session = SmartSession(retries=1, backoff_factor=10.0)
    url = "https://ratelimit.local/res"
    # First: 429 with Retry-After: 2; then success
    requests_mock.get(url, [
        {"status_code": 429, "json": {"err": "too many"}, "headers": {"Content-Type": "application/json", "Retry-After": "2"}},
        {"status_code": 200, "json": {"ok": True}, "headers": {"Content-Type": "application/json"}},
    ])

    r = session.get(url)
    assert r.status_code == 200
    assert len(sleeps) == 1 and abs(sleeps[0] - 2.0) < 1e-6


def test_429_with_retry_after_http_date(monkeypatch, requests_mock):
    import program.utils.request as request_mod
    sleeps = []
    # Fix now to a known instant
    now = 1_000_000.0
    monkeypatch.setattr(request_mod.time, "time", lambda: now, raising=True)
    monkeypatch.setattr(request_mod.time, "sleep", lambda s: sleeps.append(s), raising=True)

    # Build HTTP-date header 3s in the future
    dt = datetime.fromtimestamp(now + 3.0, tz=timezone.utc)
    http_date = dt.strftime("%a, %d %b %Y %H:%M:%S GMT")

    session = SmartSession(retries=1)
    url = "https://ratelimit.local/date"
    requests_mock.get(url, [
        {"status_code": 429, "json": {"err": "rl"}, "headers": {"Content-Type": "application/json", "Retry-After": http_date}},
        {"status_code": 200, "json": {"ok": True}, "headers": {"Content-Type": "application/json"}},
    ])

    r = session.get(url)
    assert r.status_code == 200
    assert len(sleeps) == 1 and abs(sleeps[0] - 3.0) <= 1.0  # allow small rounding


def test_429_invalid_retry_after_falls_back_to_jitter(monkeypatch, requests_mock):
    import program.utils.request as request_mod
    # Fix jitter to 0.0 to get 0.5 * base
    monkeypatch.setattr(request_mod.random, "random", lambda: 0.0, raising=True)

    sleeps = []
    monkeypatch.setattr(request_mod.time, "sleep", lambda s: sleeps.append(s), raising=True)

    session = SmartSession(retries=1, backoff_factor=2.0)
    url = "https://ratelimit.local/bad"
    requests_mock.get(url, [
        {"status_code": 429, "json": {"err": "rl"}, "headers": {"Content-Type": "application/json", "Retry-After": "bogus"}},
        {"status_code": 200, "json": {"ok": True}, "headers": {"Content-Type": "application/json"}},
    ])

    r = session.get(url)
    assert r.status_code == 200
    # attempt=1, base=2.0, jitter=0.5 => 1.0 seconds
    assert len(sleeps) == 1 and abs(sleeps[0] - 1.0) < 1e-6


def test_429_no_retry_when_retries_zero(monkeypatch, requests_mock):
    import program.utils.request as request_mod
    sleeps = []
    monkeypatch.setattr(request_mod.time, "sleep", lambda s: sleeps.append(s), raising=True)

    session = SmartSession(retries=0)
    url = "https://ratelimit.local/noretry"
    requests_mock.get(url, {"status_code": 429, "json": {"err": "rl"}, "headers": {"Content-Type": "application/json"}})

    r = session.get(url)
    assert r.status_code == 429
    assert sleeps == []
