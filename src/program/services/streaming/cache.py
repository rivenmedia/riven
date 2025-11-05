from __future__ import annotations
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import trio
import hashlib
import os
import threading
import time
import json
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from bisect import bisect_right, insort
from typing import Literal


from loguru import logger


@dataclass
class CacheConfig:
    cache_dir: Path
    max_size_bytes: int = 10 * 1024 * 1024 * 1024  # 10 GiB
    ttl_seconds: int = 2 * 60 * 60  # 2 hours
    eviction: Literal["LRU", "TTL"] = "LRU"
    metrics_enabled: bool = True


@dataclass(frozen=True)
class CacheEntry:
    key: str
    cache_key: str
    start: int
    size: int
    mtime: float


class Metrics:
    def __init__(self) -> None:
        self.hits = 0
        self.misses = 0
        self.bytes_from_cache = 0
        self.bytes_written = 0
        self.evictions = 0
        self.lock = threading.Lock()

    def snapshot(self) -> dict[str, int]:
        with self.lock:
            return {
                "hits": self.hits,
                "misses": self.misses,
                "bytes_from_cache": self.bytes_from_cache,
                "bytes_written": self.bytes_written,
                "evictions": self.evictions,
            }


class Cache:
    """
    Simple file-based block cache on disk with cross-chunk boundary support.
    We maintain a small in-memory LRU index for eviction decisions.
    """

    def __init__(self, cfg: CacheConfig) -> None:
        self.cfg = cfg
        self._index: "OrderedDict[str, CacheEntry]" = OrderedDict()
        self._by_path: dict[str, list[int]] = {}
        self._total_bytes = 0
        self._lock = trio.Lock()
        # Thread lock for synchronizing _index/_by_path access
        self._thread_lock = threading.Lock()
        self._metrics = Metrics()
        self._last_log = 0.0  # Initialize last log timestamp

        try:
            os.makedirs(self.cfg.cache_dir, exist_ok=True)
        except Exception as e:
            # Do not raise here; CacheManager may have attempted to validate and fall back.
            logger.warning(
                f"Disk cache directory init warning for {self.cfg.cache_dir}: {e}"
            )

        trio.run(self._initialize)

    @asynccontextmanager
    async def locks(self) -> AsyncGenerator[None, None]:
        """Async context manager to acquire the cache locks."""

        async with self._lock:
            with self._thread_lock:
                yield

    async def _initialize(self) -> None:
        # Lazy-rebuild index for any pre-existing files so size limits apply after restart
        try:
            await self._initial_scan()
        except Exception as e:
            logger.debug(f"Disk cache initial scan skipped: {e}")

    async def _initial_scan(self) -> None:
        # Build index from on-disk files, ordered by mtime ascending for LRU correctness
        entries: list[CacheEntry] = []

        try:
            for sub in self.cfg.cache_dir.iterdir():
                try:
                    if sub.is_dir():
                        for fp in sub.iterdir():
                            try:
                                if not fp.is_file() or fp.suffix == ".meta":
                                    continue

                                key = fp.name
                                st = fp.stat()

                                # Try to read metadata for this cache entry
                                metadata = self._read_metadata(key)

                                if metadata:
                                    cache_key, start = metadata
                                    entries.append(
                                        CacheEntry(
                                            key=key,
                                            cache_key=cache_key,
                                            start=start,
                                            size=int(st.st_size),
                                            mtime=float(st.st_mtime),
                                        )
                                    )
                                else:
                                    # No metadata found - this is an orphaned file
                                    logger.warning(
                                        f"Removing orphaned cache file without metadata: {fp}"
                                    )
                                    try:
                                        fp.unlink()
                                        # Also remove any stale metadata file
                                        self._remove_metadata(key)
                                    except Exception as e:
                                        logger.warning(
                                            f"Failed to remove orphaned cache file {fp}: {e}"
                                        )
                            except Exception:
                                continue
                    elif sub.is_file() and sub.suffix != ".meta":
                        key = sub.name
                        st = sub.stat()

                        # Try to read metadata for this cache entry
                        metadata = self._read_metadata(key)
                        if metadata:
                            cache_key, start = metadata
                            entries.append(
                                CacheEntry(
                                    key=key,
                                    cache_key=cache_key,
                                    start=start,
                                    size=int(st.st_size),
                                    mtime=float(st.st_mtime),
                                )
                            )
                        else:
                            # No metadata found - this is an orphaned file
                            logger.warning(
                                f"Removing orphaned cache file without metadata: {sub}"
                            )
                            try:
                                sub.unlink()
                                # Also remove any stale metadata file
                                self._remove_metadata(key)
                            except Exception as e:
                                logger.warning(
                                    f"Failed to remove orphaned cache file {sub}: {e}"
                                )
                except Exception:
                    continue
        finally:
            entries.sort(key=lambda t: t.mtime)  # by mtime asc

            async with self.locks():
                self._index.clear()
                self._by_path.clear()
                self._total_bytes = 0

                for cache_entry in entries:
                    self._index[cache_entry.key] = cache_entry
                    self._total_bytes += cache_entry.size

                    # Rebuild _by_path index
                    lst = self._by_path.setdefault(cache_entry.cache_key, [])
                    insort(lst, cache_entry.start)

            # If we are over budget, evict oldest until within max_disk_bytes
            try:
                await self.trim()
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

    def _metadata_file_for(self, key: str) -> Path:
        """Get the metadata sidecar file path for a cache entry."""

        return self._file_for(key).with_suffix(".meta")

    def _write_metadata(self, key: str, cache_key: str, start: int) -> None:
        """Write metadata for a cache entry to a sidecar file."""

        metadata = {"cache_key": cache_key, "start": start}

        try:
            with self._metadata_file_for(key).open("w") as f:
                json.dump(metadata, f)
        except Exception as e:
            logger.warning(f"Failed to write cache metadata for {key}: {e}")

    def _read_metadata(self, key: str) -> tuple[str, int] | None:
        """Read metadata for a cache entry from its sidecar file."""

        metadata_file = self._metadata_file_for(key)

        if not metadata_file.exists():
            return None

        try:
            with metadata_file.open("r") as f:
                metadata = json.load(f)
                return metadata["cache_key"], metadata["start"]
        except Exception as e:
            logger.warning(f"Failed to read cache metadata for {key}: {e}")
            return None

    def _remove_metadata(self, key: str) -> None:
        """Remove metadata file for a cache entry."""

        try:
            metadata_file = self._metadata_file_for(key)

            if metadata_file.exists():
                metadata_file.unlink()
        except Exception as e:
            logger.warning(f"Failed to remove cache metadata for {key}: {e}")

    async def _evict_lru(self, need_bytes: int = 0) -> None:
        async with self.locks():
            target = max(0, self._total_bytes + need_bytes - self.cfg.max_size_bytes)

            while target > 0 and self._index:
                k, cache_entry = self._index.popitem(last=False)  # LRU

                # Remove from per-path index
                lst = self._by_path.get(cache_entry.cache_key)

                if lst:
                    idx = bisect_right(lst, cache_entry.start) - 1

                    if idx >= 0 and lst[idx] == cache_entry.start:
                        del lst[idx]

                    if not lst:
                        self._by_path.pop(cache_entry.cache_key, None)

                fp = self._file_for(k)

                try:
                    if fp.exists():
                        fp.unlink()

                    # Also remove metadata file
                    self._remove_metadata(k)
                except Exception:
                    pass

                self._total_bytes -= cache_entry.size
                target -= cache_entry.size
                self._metrics.evictions += 1

    async def _evict_ttl(self) -> None:
        ttl = self.cfg.ttl_seconds
        now = time.time()
        removed = 0

        async with self.locks():
            for k in list(self._index.keys()):
                cache_entry = self._index.get(k)

                if not cache_entry:
                    continue

                if now - cache_entry.mtime > ttl:
                    fp = self._file_for(k)

                    try:
                        if fp.exists():
                            fp.unlink()

                        # Also remove metadata file
                        self._remove_metadata(k)
                    except Exception:
                        pass

                    self._index.pop(k, None)
                    lst = self._by_path.get(cache_entry.cache_key)

                    if lst:
                        idx = bisect_right(lst, cache_entry.start) - 1

                        if idx >= 0 and lst[idx] == cache_entry.start:
                            del lst[idx]

                        if not lst:
                            self._by_path.pop(cache_entry.cache_key, None)

                    self._total_bytes -= cache_entry.size
                    removed += 1

        if removed:
            self._metrics.evictions += removed

    async def get(self, cache_key: str, start: int, end: int) -> bytes:
        needed_len = max(0, end - start + 1)

        if needed_len == 0:
            return b""

        get_start_time = time.time()

        # Fast path: Try to find a single chunk that contains the entire request
        # This avoids holding the lock during file I/O for the common case
        chunk_key = None
        chunk_file = None
        chunk_start_offset = 0

        async with self.locks():
            s_list = self._by_path.get(cache_key)

            if s_list:
                # Find chunk that might contain start position
                idx = bisect_right(s_list, start) - 1

                if idx >= 0:
                    chunk_start = s_list[idx]
                    cache_entry = self._index.get(self._key(cache_key, chunk_start))

                    if cache_entry:
                        chunk_end = chunk_start + cache_entry.size - 1

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
                # This is much faster for large chunks (128MB) when we only need 128KB
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
                    async with self.locks():
                        if chunk_key in self._index:
                            cache_entry = self._index[chunk_key]
                            self._index.move_to_end(chunk_key, last=True)

                            # Only update timestamp if it's been more than 10 seconds
                            # This reduces write pressure on the index
                            now = time.time()

                            if now - cache_entry.mtime > 10.0:
                                self._index[chunk_key] = CacheEntry(
                                    key=cache_entry.key,
                                    cache_key=cache_entry.cache_key,
                                    mtime=now,
                                    start=cache_entry.start,
                                    size=cache_entry.size,
                                )

                    self._metrics.hits += 1
                    self._metrics.bytes_from_cache += needed_len

                    total_time = time.time() - get_start_time

                    if total_time > 0.1:  # Log if cache.get() takes >100ms
                        logger.warning(
                            f"Slow cache.get(): {total_time * 1000:.0f}ms for {needed_len / (1024 * 1024):.2f}MB (read: {read_time * 1000:.0f}ms)"
                        )

                    return result
            except FileNotFoundError:
                # Chunk file missing, fall through to slow path
                pass

        # Slow path: multi-chunk stitching for cross-chunk boundary requests
        # Plan the read operations while holding the lock, then release it for I/O
        chunks_to_read = []

        async with self.locks():
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
                    cache_entry = self._index.get(chunk_key)

                    if not cache_entry:
                        break  # Chunk not in index

                    chunk_end = chunk_start + cache_entry.size - 1

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
                            "chunk_ts": cache_entry.mtime,
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
                    async with self.locks():
                        now = time.time()

                        for chunk_key, chunk_ts in chunks_used:
                            if chunk_key in self._index:  # Verify chunk still exists
                                self._index.move_to_end(chunk_key, last=True)

                                # Only update timestamp if it's been more than 10 seconds
                                if now - chunk_ts > 10.0:
                                    cache_entry = self._index[chunk_key]
                                    self._index[chunk_key] = CacheEntry(
                                        key=cache_entry.key,
                                        mtime=now,
                                        cache_key=cache_entry.cache_key,
                                        start=cache_entry.start,
                                        size=cache_entry.size,
                                    )

                    self._metrics.hits += 1
                    self._metrics.bytes_from_cache += needed_len

                    return bytes(result_data)

        # Fallback: Direct probe for exact key on filesystem and rebuild index
        k = self._key(cache_key, start)
        fp = self._file_for(k)
        data: bytes | None = None

        try:
            with fp.open("rb") as f:
                data = f.read()
        except FileNotFoundError:
            data = None

        if data is None:
            async with self.locks():
                self._index.pop(k, None)

            self._metrics.misses += 1
            # No log for cache misses - reduces noise (misses are expected and normal)
            return b""

        # If we got here but entry was missing in index, rebuild it
        async with self.locks():
            if k not in self._index:
                sz = len(data)
                self._index[k] = CacheEntry(
                    key=k,
                    cache_key=cache_key,
                    start=start,
                    size=sz,
                    mtime=time.time(),
                )
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

    async def put(self, cache_key: str, start: int, data: bytes) -> None:
        if not data:
            return

        k = self._key(cache_key, start)
        need = len(data)

        if self.cfg.eviction == "TTL":
            await self._evict_ttl()
        else:
            await self._evict_lru(need)

        fp = self._file_for(k)

        try:
            with fp.open("wb") as f:
                f.write(data)

            # Write metadata after successful data write
            self._write_metadata(k, cache_key, start)
        except Exception as e:
            logger.warning(f"Disk cache write failed: {e}")
            return

        async with self.locks():
            prev = self._index.pop(k, None)

            if prev:
                self._total_bytes -= prev.size
                lst_prev = self._by_path.get(cache_key)

                if lst_prev:
                    idx_prev = bisect_right(lst_prev, start) - 1

                    if idx_prev >= 0 and lst_prev[idx_prev] == start:
                        del lst_prev[idx_prev]

                    if not lst_prev:
                        self._by_path.pop(cache_key, None)

            self._index[k] = CacheEntry(
                key=k,
                cache_key=cache_key,
                start=start,
                size=need,
                mtime=time.time(),
            )
            lst = self._by_path.setdefault(cache_key, [])
            insort(lst, start)
            self._total_bytes += need
            self._metrics.bytes_written += need

    def has(self, cache_key: str, start: int, end: int) -> bool:
        """
        Check if the cache contains the full range [start, end] for the given cache_key.

        This uses a thread-safe approach to prevent data races with concurrent writers.
        """

        k = self._key(cache_key, start)

        # Use a separate thread lock to protect _index reads from async writers
        # This avoids the need to make this method async
        with self._thread_lock:
            cache_entry = self._index.get(k)

            if not cache_entry:
                return False

            chunk_end = cache_entry.start + cache_entry.size - 1

            if end > chunk_end:
                return False

        # Check file existence outside the lock
        fp = self._file_for(k)

        return fp.exists()

    async def trim(self) -> None:
        # Primary policy-based trimming
        if self.cfg.eviction == "TTL":
            await self._evict_ttl()
        else:
            await self._evict_lru()

        # Hard safety net: if our accounting drifted (e.g., external files), rebuild and prune
        try:
            async with self.locks():
                over = self._total_bytes > self.cfg.max_size_bytes

            if over:
                await self._initial_scan()
        except Exception:
            pass

    async def stats(self) -> dict[str, int]:
        s = self._metrics.snapshot()

        async with self._lock:
            s["total_bytes"] = self._total_bytes
            s["entries"] = len(self._index)

        return s

    async def maybe_log_stats(self) -> None:
        now = time.time()

        if not self.cfg.metrics_enabled:
            return

        if now - self._last_log < 30:  # log at most every 30s
            return

        # Proactive safe trim before logging to keep within caps
        try:
            await self.trim()
        except Exception:
            pass

        self._last_log = now
        stats = await self.stats()

        logger.log("VFS", f"Cache stats: {stats}")
