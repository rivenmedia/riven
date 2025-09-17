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
    storage: str = "memory"  # memory | disk | hybrid
    memory_dir: Path = Path("/dev/shm/riven-cache")
    disk_dir: Path = Path("/var/cache/riven")
    max_memory_bytes: int = 2 * 1024 * 1024 * 1024  # 2 GiB
    max_disk_bytes: int = 10 * 1024 * 1024 * 1024  # 10 GiB
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


class MemoryBackend(CacheBackend):
    """
    Simple in-process LRU block cache.
    Keys are (path, start). Values are (data_bytes, last_access_ts).
    """

    def __init__(self, cfg: CacheConfig) -> None:
        self.cfg = cfg
        self._blocks: "OrderedDict[Tuple[str, int], Tuple[bytes, float]]" = OrderedDict()
        self._by_path: Dict[str, list[int]] = {}
        self._total_bytes = 0
        self._lock = threading.Lock()
        self._metrics = _Metrics()
        # Ensure directory exists for optional mmap-style use parity with disk; no-op otherwise
        try:
            os.makedirs(self.cfg.memory_dir, exist_ok=True)
        except Exception:
            pass

    def _evict_lru(self, need_bytes: int = 0) -> None:
        # Evict until we have room for `need_bytes` within max_memory_bytes
        with self._lock:
            target = max(0, self._total_bytes + need_bytes - self.cfg.max_memory_bytes)
            while target > 0 and self._blocks:
                (k, (data, _ts)) = self._blocks.popitem(last=False)  # LRU
                path_k, start_k = k
                lst = self._by_path.get(path_k)
                if lst:
                    idx = bisect_right(lst, start_k) - 1
                    if idx >= 0 and lst[idx] == start_k:
                        del lst[idx]
                    if not lst:
                        self._by_path.pop(path_k, None)
                sz = len(data)
                self._total_bytes -= sz
                target -= sz
                self._metrics.evictions += 1

    def _evict_ttl(self) -> None:
        ttl = self.cfg.ttl_seconds
        now = time.time()
        removed = 0
        with self._lock:
            for k in list(self._blocks.keys()):
                data, ts = self._blocks.get(k, (b"", 0.0))
                if now - ts > ttl:
                    self._blocks.pop(k, None)
                    path_k, start_k = k
                    lst = self._by_path.get(path_k)
                    if lst:
                        idx = bisect_right(lst, start_k) - 1
                        if idx >= 0 and lst[idx] == start_k:
                            del lst[idx]
                        if not lst:
                            self._by_path.pop(path_k, None)
                    self._total_bytes -= len(data)
                    removed += 1
        if removed:
            self._metrics.evictions += removed

    def get(self, path: str, start: int, end: int) -> Optional[bytes]:
        key = (path, start)
        with self._lock:
            blk = self._blocks.get(key)
            if blk:
                data, _ts = blk
                # Move to MRU
                self._blocks.move_to_end(key, last=True)
                self._blocks[key] = (data, time.time())
            else:
                # Fast subrange coverage using per-path sorted starts
                needed_len = max(0, end - start + 1)
                s_list = self._by_path.get(path)
                if s_list:
                    idx = bisect_right(s_list, start) - 1
                    if idx >= 0:
                        cand_start = s_list[idx]
                        cand_key = (path, cand_start)
                        cand = self._blocks.get(cand_key)
                        if cand:
                            c_data, _c_ts = cand
                            offset = start - cand_start
                            if 0 <= offset <= len(c_data) and (len(c_data) - offset) >= needed_len:
                                # Promote to MRU and return slice
                                self._blocks.move_to_end(cand_key, last=True)
                                self._blocks[cand_key] = (c_data, time.time())
                                if needed_len <= 0:
                                    return b""
                                self._metrics.hits += 1
                                self._metrics.bytes_from_cache += needed_len
                                return c_data[offset:offset + needed_len]
                # No coverage found
                self._metrics.misses += 1
                return None
        # Ensure requested range fully covered by the direct block
        if end < start:
            return b""
        length = end - start + 1
        if len(data) >= length:
            self._metrics.hits += 1
            self._metrics.bytes_from_cache += length
            return data[:length]
        # Partial coverage only; treat as miss
        self._metrics.misses += 1
        return None

    def put(self, path: str, start: int, data: bytes) -> None:
        if not data:
            return
        key = (path, start)
        need = len(data)
        if self.cfg.eviction == "TTL":
            self._evict_ttl()
        else:
            self._evict_lru(need)
        with self._lock:
            prev = self._blocks.pop(key, None)
            if prev:
                self._total_bytes -= len(prev[0])
                lst_prev = self._by_path.get(path)
                if lst_prev:
                    idx_prev = bisect_right(lst_prev, start) - 1
                    if idx_prev >= 0 and lst_prev[idx_prev] == start:
                        del lst_prev[idx_prev]
                    if not lst_prev:
                        self._by_path.pop(path, None)
            self._blocks[key] = (data, time.time())
            self._total_bytes += need
            self._metrics.bytes_written += need
            lst = self._by_path.setdefault(path, [])
            insort(lst, start)

    def trim(self) -> None:
        if self.cfg.eviction == "TTL":
            self._evict_ttl()
        else:
            self._evict_lru(0)

    def stats(self) -> Dict[str, int]:
        return self._metrics.snapshot()


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
        self._lock = threading.Lock()
        self._metrics = _Metrics()
        try:
            os.makedirs(self.cfg.disk_dir, exist_ok=True)
        except Exception as e:
            # Do not raise here; CacheManager will have attempted to validate and fall back.
            logger.warning(f"Disk cache directory init warning for {self.cfg.disk_dir}: {e}")

    def _key(self, path: str, start: int) -> str:
        h = hashlib.sha1(f"{path}|{start}".encode()).hexdigest()
        return h

    def _file_for(self, key: str) -> Path:
        # Two-level fanout to avoid too many files in one dir
        sub = key[:2]
        p = self.cfg.disk_dir / sub
        p.mkdir(parents=True, exist_ok=True)
        return p / key

    def _evict_lru(self, need_bytes: int = 0) -> None:
        with self._lock:
            target = max(0, self._total_bytes + need_bytes - self.cfg.max_disk_bytes)
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
                                    if ent2 is None:
                                        self._index[cand_key] = (len(c_data), time.time(), path, c_start)
                                    else:
                                        self._index.move_to_end(cand_key, last=True)
                                        self._index[cand_key] = (len(c_data), time.time(), path, c_start)
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
                self._index[k] = (len(data), time.time(), path, start)
                lst = self._by_path.setdefault(path, [])
                insort(lst, start)
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
            self._evict_ttl()
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
        if self.cfg.eviction == "TTL":
            self._evict_ttl()
        else:
            self._evict_lru(0)

    def stats(self) -> Dict[str, int]:
        return self._metrics.snapshot()


class HybridBackend(CacheBackend):
    def __init__(self, cfg: CacheConfig) -> None:
        # Use a scaled memory for hot data and disk for overflow
        self.mem = MemoryBackend(cfg)
        self.disk = DiskBackend(cfg)

    def get(self, path: str, start: int, end: int) -> Optional[bytes]:
        data = self.mem.get(path, start, end)
        if data is not None:
            return data
        data = self.disk.get(path, start, end)
        if data is not None:
            # Promote to memory hot cache opportunistically
            self.mem.put(path, start, data)
        return data

    def put(self, path: str, start: int, data: bytes) -> None:
        # Try writing to memory; if it evicts too eagerly, disk still holds it
        self.mem.put(path, start, data)
        self.disk.put(path, start, data)

    def trim(self) -> None:
        self.mem.trim()
        self.disk.trim()

    def stats(self) -> Dict[str, int]:
        m = self.mem.stats()
        d = self.disk.stats()
        return {f"mem_{k}": v for k, v in m.items()} | {f"disk_{k}": v for k, v in d.items()}


class CacheManager:
    def __init__(self, cfg: CacheConfig) -> None:
        self.cfg = cfg
        storage = (cfg.storage or "memory").lower()

        # Prepare disk dir and fall back to user cache or memory if not accessible
        if storage in ("disk", "hybrid"):
            try:
                cfg.disk_dir.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                try:
                    fallback_root = Path(os.environ.get("XDG_CACHE_HOME", str(Path.home() / ".cache")))
                    fallback_dir = fallback_root / "riven"
                    fallback_dir.mkdir(parents=True, exist_ok=True)
                    logger.warning(
                        f"Disk cache dir {cfg.disk_dir} not accessible ({e}). Falling back to {fallback_dir}."
                    )
                    cfg.disk_dir = fallback_dir
                except Exception as e2:
                    logger.warning(
                        f"Disk cache fallback not accessible ({e2}). Falling back to in-memory cache."
                    )
                    storage = "memory"

        if storage == "disk":
            self.backend: CacheBackend = DiskBackend(cfg)
        elif storage == "hybrid":
            self.backend = HybridBackend(cfg)
        else:
            self.backend = MemoryBackend(cfg)
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
        self._last_log = now
        stats = self.backend.stats()
        logger.bind(component="RivenVFS").debug(f"Cache stats: {stats}")

    def trim(self) -> None:
        self.backend.trim()

