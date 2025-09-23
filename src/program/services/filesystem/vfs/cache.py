from __future__ import annotations

import hashlib
import os
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional, Tuple
from bisect import bisect_right, insort


from loguru import logger


@dataclass
class CacheConfig:
    cache_dir: Path = Path("/var/cache/riven")
    max_size_bytes: int = 10 * 1024 * 1024 * 1024  # 10 GiB
    ttl_seconds: int = 2 * 60 * 60  # 2 hours
    eviction: str = "LRU"  # LRU | TTL
    metrics_enabled: bool = True


class _Metrics:
    def __init__(self) -> None:
        self.hits = 0
        self.misses = 0
        self.bytes_from_cache = 0
        self.bytes_written = 0
        self.evictions = 0
        self.lock = threading.Lock()

    def snapshot(self) -> Dict[str, int]:
        with self.lock:
            return dict(
                hits=self.hits,
                misses=self.misses,
                bytes_from_cache=self.bytes_from_cache,
                bytes_written=self.bytes_written,
                evictions=self.evictions,
            )


class CacheBackend:
    def get(self, path: str, start: int, end: int) -> Optional[bytes]:
        raise NotImplementedError

    def put(self, path: str, start: int, data: bytes) -> None:
        raise NotImplementedError

    def trim(self) -> None:
        raise NotImplementedError

    def stats(self) -> Dict[str, int]:
        raise NotImplementedError




class DiskBackend(CacheBackend):
    """
    Simple file-based block cache on disk. Keys map to files under disk_dir.
    We maintain a small in-memory LRU index for eviction decisions.
    """

    def __init__(self, cfg: CacheConfig) -> None:
        self.cfg = cfg
        # key -> (size, last_access, path, start)
        self._index: "OrderedDict[str, Tuple[int, float, str, int]]" = OrderedDict()
        self._by_path: Dict[str, list[int]] = {}
        self._total_bytes = 0
        self._lock = threading.RLock()
        self._metrics = _Metrics()
        try:
            os.makedirs(self.cfg.cache_dir, exist_ok=True)
        except Exception as e:
            # Do not raise here; CacheManager may have attempted to validate and fall back.
            logger.warning(f"Disk cache directory init warning for {self.cfg.cache_dir}: {e}")

        # Lazy-rebuild index for any pre-existing files so size limits apply after restart
        try:
            if (self.cfg.eviction or "LRU").upper() == "LRU":
                self._initial_scan()
        except Exception as e:
            logger.debug(f"Disk cache initial scan skipped: {e}")

    def _initial_scan(self) -> None:
        # Build index from on-disk files, ordered by mtime ascending for LRU correctness
        entries: list[tuple[str, int, float]] = []  # (key, size, mtime)
        try:
            for sub in self.cfg.cache_dir.iterdir():
                try:
                    if sub.is_dir():
                        for fp in sub.iterdir():
                            try:
                                if not fp.is_file():
                                    continue
                                key = fp.name
                                st = fp.stat()
                                entries.append((key, int(st.st_size), float(st.st_mtime)))
                            except Exception:
                                continue
                    elif sub.is_file():
                        st = sub.stat()
                        entries.append((sub.name, int(st.st_size), float(st.st_mtime)))
                except Exception:
                    continue
        finally:
            entries.sort(key=lambda t: t[2])  # by mtime asc
            with self._lock:
                self._index.clear()
                self._by_path.clear()
                self._total_bytes = 0
                for key, sz, ts in entries:
                    self._index[key] = (sz, ts, "", 0)
                    self._total_bytes += sz
            # If we are over budget, evict oldest until within max_disk_bytes
            try:
                self._evict_lru(0)
            except Exception:
                pass

    def _key(self, path: str, start: int) -> str:
        h = hashlib.sha1(f"{path}|{start}".encode()).hexdigest()
        return h

    def _file_for(self, key: str) -> Path:
        # Two-level fanout to avoid too many files in one dir
        sub = key[:2]
        p = self.cfg.cache_dir / sub
        p.mkdir(parents=True, exist_ok=True)
        return p / key

    def _evict_lru(self, need_bytes: int = 0) -> None:
        with self._lock:
            target = max(0, self._total_bytes + need_bytes - self.cfg.max_size_bytes)
            while target > 0 and self._index:
                k, (sz, _ts, _path, _start) = self._index.popitem(last=False)  # LRU
                # Remove from per-path index
                lst = self._by_path.get(_path)
                if lst:
                    idx = bisect_right(lst, _start) - 1
                    if idx >= 0 and lst[idx] == _start:
                        del lst[idx]
                    if not lst:
                        self._by_path.pop(_path, None)
                fp = self._file_for(k)
                try:
                    if fp.exists():
                        fp.unlink()
                except Exception:
                    pass
                self._total_bytes -= sz
                target -= sz
                self._metrics.evictions += 1

    def _evict_ttl(self) -> None:
        ttl = self.cfg.ttl_seconds
        now = time.time()
        removed = 0
        with self._lock:
            for k in list(self._index.keys()):
                info = self._index.get(k, (0, 0.0, "", 0))
                sz, ts, pth, st = info[0], info[1], info[2], info[3]
                if now - ts > ttl:
                    fp = self._file_for(k)
                    try:
                        if fp.exists():
                            fp.unlink()
                    except Exception:
                        pass
                    self._index.pop(k, None)
                    lst = self._by_path.get(pth)
                    if lst:
                        idx = bisect_right(lst, st) - 1
                        if idx >= 0 and lst[idx] == st:
                            del lst[idx]
                        if not lst:
                            self._by_path.pop(pth, None)
                    self._total_bytes -= sz
                    removed += 1
        if removed:
            self._metrics.evictions += removed

    def get(self, path: str, start: int, end: int) -> Optional[bytes]:
        k = self._key(path, start)
        with self._lock:
            ent = self._index.get(k)
            if ent:
                sz, _ts, _p, _s = ent
                self._index.move_to_end(k, last=True)
                self._index[k] = (sz, time.time(), _p, _s)
            else:
                # Fast subrange coverage via per-path sorted starts
                needed_len = max(0, end - start + 1)
                s_list = self._by_path.get(path)
                if s_list:
                    idx = bisect_right(s_list, start) - 1
                    if idx >= 0:
                        c_start = s_list[idx]
                        cand_key = self._key(path, c_start)
                        ent2 = self._index.get(cand_key)
                        c_sz = ent2[0] if ent2 else None
                        if c_sz is None:
                            fp_c = self._file_for(cand_key)
                            try:
                                c_sz = fp_c.stat().st_size if fp_c.exists() else None
                            except Exception:
                                c_sz = None
                        if c_sz is not None:
                            offset = start - c_start
                            if 0 <= offset and (c_sz - offset) >= needed_len:
                                # Read candidate and return slice
                                fp_c = self._file_for(cand_key)
                                try:
                                    with fp_c.open("rb") as f:
                                        c_data = f.read()
                                except FileNotFoundError:
                                    pass
                                else:
                                    sz = len(c_data)
                                    with self._lock:
                                        if ent2 is None:
                                            self._index[cand_key] = (sz, time.time(), path, c_start)
                                            self._total_bytes += sz
                                        else:
                                            self._index.move_to_end(cand_key, last=True)
                                            prev_sz = ent2[0]
                                            self._index[cand_key] = (sz, time.time(), path, c_start)
                                            self._total_bytes += max(0, sz - prev_sz)
                                    self._metrics.hits += 1
                                    self._metrics.bytes_from_cache += needed_len
                                    return c_data[offset:offset + needed_len]
                # no coverage found; proceed to direct file probe below
        # Direct probe for exact key on filesystem and rebuild index
        fp = self._file_for(k)
        data: Optional[bytes] = None
        try:
            with fp.open("rb") as f:
                data = f.read()
        except FileNotFoundError:
            data = None
        if data is None:
            with self._lock:
                self._index.pop(k, None)
            self._metrics.misses += 1
            return None
        # If we got here but entry was missing in index, rebuild it
        with self._lock:
            if k not in self._index:
                sz = len(data)
                self._index[k] = (sz, time.time(), path, start)
                lst = self._by_path.setdefault(path, [])
                insort(lst, start)
                self._total_bytes += sz
        if end < start:
            return b""
        length = end - start + 1
        if len(data) >= length:
            self._metrics.hits += 1
            self._metrics.bytes_from_cache += length
            return data[:length]
        self._metrics.misses += 1
        return None

    def put(self, path: str, start: int, data: bytes) -> None:
        if not data:
            return
        k = self._key(path, start)
        need = len(data)
        if self.cfg.eviction == "TTL":
            # TTL pruning plus size enforcement
            self._evict_ttl()
            self._evict_lru(need)
        else:
            self._evict_lru(need)
        fp = self._file_for(k)
        try:
            with fp.open("wb") as f:
                f.write(data)
        except Exception as e:
            logger.warning(f"Disk cache write failed: {e}")
            return
        with self._lock:
            prev = self._index.pop(k, None)
            if prev:
                self._total_bytes -= prev[0]
                lst_prev = self._by_path.get(path)
                if lst_prev:
                    idx_prev = bisect_right(lst_prev, start) - 1
                    if idx_prev >= 0 and lst_prev[idx_prev] == start:
                        del lst_prev[idx_prev]
                    if not lst_prev:
                        self._by_path.pop(path, None)
            self._index[k] = (need, time.time(), path, start)
            lst = self._by_path.setdefault(path, [])
            insort(lst, start)
            self._total_bytes += need
            self._metrics.bytes_written += need

    def trim(self) -> None:
        # Primary policy-based trimming
        if self.cfg.eviction == "TTL":
            self._evict_ttl()
            self._evict_lru(0)
        else:
            self._evict_lru(0)
        # Hard safety net: if our accounting drifted (e.g., external files), rebuild and prune
        try:
            with self._lock:
                over = self._total_bytes > self.cfg.max_size_bytes
            if over:
                self._initial_scan()
        except Exception:
            pass

    def stats(self) -> Dict[str, int]:
        s = self._metrics.snapshot()
        with self._lock:
            s["total_bytes"] = self._total_bytes
            s["entries"] = len(self._index)
        return s




class CacheManager:
    def __init__(self, cfg: CacheConfig) -> None:
        self.cfg = cfg
        # Prepare cache dir and fall back to user cache if not accessible
        try:
            cfg.cache_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            try:
                fallback_root = Path(os.environ.get("XDG_CACHE_HOME", str(Path.home() / ".cache")))
                fallback_dir = fallback_root / "riven"
                fallback_dir.mkdir(parents=True, exist_ok=True)
                logger.warning(
                    f"Cache dir {cfg.cache_dir} not accessible ({e}). Falling back to {fallback_dir}."
                )
                cfg.cache_dir = fallback_dir
            except Exception as e2:
                # If even fallback is not accessible, keep going; DiskBackend will likely fail writes gracefully
                logger.warning(
                    f"Cache fallback dir not accessible ({e2}). Continuing with configured path: {cfg.cache_dir}."
                )
        self.backend: CacheBackend = DiskBackend(cfg)
        self._last_log = 0.0

    def get(self, path: str, start: int, end: int) -> Optional[bytes]:
        return self.backend.get(path, start, end)

    def put(self, path: str, start: int, data: bytes) -> None:
        self.backend.put(path, start, data)

    def maybe_log_stats(self) -> None:
        now = time.time()
        if not self.cfg.metrics_enabled:
            return
        if now - self._last_log < 30:  # log at most every 30s
            return
        # Proactive safe trim before logging to keep within caps
        try:
            self.backend.trim()
        except Exception:
            pass
        self._last_log = now
        stats = self.backend.stats()
        logger.bind(component="RivenVFS").log("VFS", f"Cache stats: {stats}")

    def trim(self) -> None:
        self.backend.trim()

