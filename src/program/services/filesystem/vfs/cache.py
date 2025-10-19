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


class Cache:
    """
    Simple file-based block cache on disk with cross-chunk boundary support.
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
        self._last_log = 0.0  # Initialize last log timestamp
        try:
            os.makedirs(self.cfg.cache_dir, exist_ok=True)
        except Exception as e:
            # Do not raise here; CacheManager may have attempted to validate and fall back.
            logger.warning(
                f"Disk cache directory init warning for {self.cfg.cache_dir}: {e}"
            )

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
                                entries.append(
                                    (key, int(st.st_size), float(st.st_mtime))
                                )
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

    def get(self, cache_key: str, start: int, end: int) -> bytes:
        needed_len = max(0, end - start + 1)
        if needed_len == 0:
            return b""

        get_start_time = time.time()

        # Fast path: Try to find a single chunk that contains the entire request
        # This avoids holding the lock during file I/O for the common case
        chunk_key = None
        chunk_file = None
        chunk_start_offset = 0

        with self._lock:
            s_list = self._by_path.get(cache_key)
            if s_list:
                # Find chunk that might contain start position
                idx = bisect_right(s_list, start) - 1
                if idx >= 0:
                    chunk_start = s_list[idx]
                    chunk_entry = self._index.get(self._key(cache_key, chunk_start))
                    if chunk_entry:
                        chunk_size, _, _, _ = chunk_entry
                        chunk_end = chunk_start + chunk_size - 1

                        # Check if this single chunk covers the entire request
                        if start >= chunk_start and end <= chunk_end:
                            # Fast path: single chunk covers entire request
                            chunk_key = self._key(cache_key, chunk_start)
                            chunk_file = self._file_for(chunk_key)
                            chunk_start_offset = chunk_start
                            # Don't update timestamps yet - do it after successful read

        # Fast path: read single chunk outside the lock
        if chunk_key and chunk_file:
            try:
                read_start = time.time()

                # Calculate slice within chunk
                copy_start = start - chunk_start_offset
                copy_end = end - chunk_start_offset
                bytes_to_read = copy_end - copy_start + 1

                # Optimization: Only read the slice we need, not the entire chunk!
                # This is much faster for large chunks (128MB) when we only need 131KB
                with chunk_file.open("rb") as f:
                    f.seek(copy_start)
                    result = f.read(bytes_to_read)

                read_time = time.time() - read_start

                if read_time > 0.05:  # Log slow reads (>50ms)
                    logger.warning(
                        f"Slow cache read: {len(result)/(1024*1024):.2f}MB in {read_time*1000:.0f}ms from {chunk_file}"
                    )

                if len(result) == needed_len:
                    # Update LRU (move to end) but only update timestamp periodically
                    # to reduce lock contention and index modifications
                    with self._lock:
                        if chunk_key in self._index:
                            chunk_entry = self._index[chunk_key]
                            self._index.move_to_end(chunk_key, last=True)
                            # Only update timestamp if it's been more than 10 seconds
                            # This reduces write pressure on the index
                            now = time.time()
                            if now - chunk_entry[1] > 10.0:
                                self._index[chunk_key] = (
                                    chunk_entry[0],
                                    now,
                                    chunk_entry[2],
                                    chunk_entry[3],
                                )

                    self._metrics.hits += 1
                    self._metrics.bytes_from_cache += needed_len

                    total_time = time.time() - get_start_time
                    if total_time > 0.1:  # Log if cache.get() takes >100ms
                        logger.warning(
                            f"Slow cache.get(): {total_time*1000:.0f}ms for {needed_len/(1024*1024):.2f}MB (read: {read_time*1000:.0f}ms)"
                        )

                    return result
            except FileNotFoundError:
                # Chunk file missing, fall through to slow path
                pass

        # Slow path: multi-chunk stitching for cross-chunk boundary requests
        # Plan the read operations while holding the lock, then release it for I/O
        chunks_to_read = []

        with self._lock:
            s_list = self._by_path.get(cache_key)
            if s_list:
                current_pos = start

                while current_pos <= end:
                    # Find chunk that contains current_pos
                    idx = bisect_right(s_list, current_pos) - 1
                    if idx < 0:
                        break  # No chunk starts at or before current_pos

                    chunk_start = s_list[idx]
                    chunk_key = self._key(cache_key, chunk_start)
                    chunk_entry = self._index.get(chunk_key)

                    if not chunk_entry:
                        break  # Chunk not in index

                    chunk_size, chunk_ts, _, _ = chunk_entry
                    chunk_end = chunk_start + chunk_size - 1

                    # Check if this chunk covers current_pos
                    if current_pos < chunk_start or current_pos > chunk_end:
                        break  # Gap in coverage

                    # Calculate what portion of this chunk we need
                    copy_start = max(current_pos, chunk_start) - chunk_start
                    copy_end = min(end, chunk_end) - chunk_start
                    bytes_to_read = copy_end - copy_start + 1

                    # Plan this read operation
                    chunk_file = self._file_for(chunk_key)
                    chunks_to_read.append(
                        {
                            "chunk_key": chunk_key,
                            "chunk_ts": chunk_ts,
                            "chunk_file": chunk_file,
                            "copy_start": copy_start,
                            "bytes_to_read": bytes_to_read,
                            "chunk_end": chunk_end,
                        }
                    )

                    current_pos = chunk_end + 1

        # Execute reads outside the lock to reduce contention
        if chunks_to_read:
            result_data = bytearray()
            chunks_used = []

            for chunk_info in chunks_to_read:
                try:
                    with chunk_info["chunk_file"].open("rb") as f:
                        f.seek(chunk_info["copy_start"])
                        chunk_slice = f.read(chunk_info["bytes_to_read"])
                except FileNotFoundError:
                    # Chunk file missing, abort slow path
                    break

                if len(chunk_slice) == chunk_info["bytes_to_read"]:
                    result_data.extend(chunk_slice)
                    chunks_used.append(
                        (chunk_info["chunk_key"], chunk_info["chunk_ts"])
                    )
                else:
                    # Incomplete read, abort slow path
                    break
            else:
                # All chunks read successfully (no break occurred)
                if len(result_data) == needed_len:
                    # Update LRU and timestamps while holding the lock
                    with self._lock:
                        now = time.time()
                        for chunk_key, chunk_ts in chunks_used:
                            if chunk_key in self._index:  # Verify chunk still exists
                                self._index.move_to_end(chunk_key, last=True)
                                # Only update timestamp if it's been more than 10 seconds
                                if now - chunk_ts > 10.0:
                                    chunk_entry = self._index[chunk_key]
                                    self._index[chunk_key] = (
                                        chunk_entry[0],
                                        now,
                                        chunk_entry[2],
                                        chunk_entry[3],
                                    )

                    self._metrics.hits += 1
                    self._metrics.bytes_from_cache += needed_len
                    return bytes(result_data)

        # Fallback: Direct probe for exact key on filesystem and rebuild index
        k = self._key(cache_key, start)
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
            # No log for cache misses - reduces noise (misses are expected and normal)
            return b""

        # If we got here but entry was missing in index, rebuild it
        with self._lock:
            if k not in self._index:
                sz = len(data)
                self._index[k] = (sz, time.time(), cache_key, start)
                lst = self._by_path.setdefault(cache_key, [])
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

        return b""

    def put(self, cache_key: str, start: int, data: bytes) -> None:
        if not data:
            return
        k = self._key(cache_key, start)
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
                lst_prev = self._by_path.get(cache_key)
                if lst_prev:
                    idx_prev = bisect_right(lst_prev, start) - 1
                    if idx_prev >= 0 and lst_prev[idx_prev] == start:
                        del lst_prev[idx_prev]
                    if not lst_prev:
                        self._by_path.pop(cache_key, None)
            self._index[k] = (need, time.time(), cache_key, start)
            lst = self._by_path.setdefault(cache_key, [])
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

    def maybe_log_stats(self) -> None:
        now = time.time()
        if not self.cfg.metrics_enabled:
            return
        if now - self._last_log < 30:  # log at most every 30s
            return
        # Proactive safe trim before logging to keep within caps
        try:
            self.trim()
        except Exception:
            pass
        self._last_log = now
        stats = self.stats()
        logger.bind(component="RivenVFS").log("VFS", f"Cache stats: {stats}")
