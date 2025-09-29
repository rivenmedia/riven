#!/usr/bin/env python3
"""
Riven Virtual File System (RivenVFS)

A high-performance FUSE-based virtual filesystem designed for streaming media content
from various providers like Real-Debrid, Premiumize, and AllDebrid. Built with pyfuse3
and featuring:

- HTTP range request support for efficient streaming
- Provider-based URL resolution and caching
- Automatic FUSE cache invalidation for consistency
- Persistent SQLite storage with SQLAlchemy
- Robust error handling and retry logic
- Support for seeking during playback

The VFS automatically handles:
- Mount lifecycle management (mounting, unmounting, cleanup)
- Process detection and cleanup for mountpoints
- Parent directory creation when adding files
- URL caching with automatic expiration
- FUSE kernel cache invalidation for directory changes

Usage:
    from rivenvfs import RivenVFS

    vfs = RivenVFS("/mnt/riven", db_path="./riven.db", providers=providers)
    vfs.add_file("/movies/example.mp4", "https://real-debrid.com/d/ABC123", size=1073741824)
    # VFS is now mounted and ready for use

    # Clean up when done
    vfs.close()
"""
from __future__ import annotations

import os
import shutil
import errno
import time
from dataclasses import dataclass
from loguru import logger
import subprocess
import io
from typing import Dict, List, Optional, Set, Tuple


import urllib.parse
import threading

class ProviderHTTP:
    """
    Shared pycurl-based HTTP client with connection reuse via CurlShare and a simple
    per-host easy-handle pool. No rate limiting/token buckets here; focus is on
    reusing TCP/TLS sessions across requests to reduce handshake latency.
    """
    def __init__(self) -> None:
        self._share = pycurl.CurlShare()
        try:
            # Share connection cache, DNS, and SSL sessions across easy handles
            self._share.setopt(pycurl.SH_SHARE, pycurl.LOCK_DATA_CONNECT)
            self._share.setopt(pycurl.SH_SHARE, pycurl.LOCK_DATA_DNS)
            self._share.setopt(pycurl.SH_SHARE, pycurl.LOCK_DATA_SSL_SESSION)
        except Exception:
            # Older libcurl may not support all; continue with best effort
            pass
        self._pool: dict[str, list[pycurl.Curl]] = {}
        self._lock = threading.Lock()

    def _configure_common(self, c: pycurl.Curl, http10: bool = False, ignore_content_length: bool = False) -> None:
        c.setopt(pycurl.NOSIGNAL, 1)
        c.setopt(pycurl.FOLLOWLOCATION, 1)
        c.setopt(pycurl.MAXREDIRS, 5)
        c.setopt(pycurl.CONNECTTIMEOUT, 5)
        c.setopt(pycurl.TIMEOUT, 30)
        c.setopt(pycurl.USERAGENT, 'RivenVFS/1.0')
        c.setopt(pycurl.LOW_SPEED_LIMIT, 10 * 1024)
        c.setopt(pycurl.LOW_SPEED_TIME, 15)
        c.setopt(pycurl.HTTP_VERSION, pycurl.CURL_HTTP_VERSION_1_0 if http10 else pycurl.CURL_HTTP_VERSION_1_1)
        c.setopt(pycurl.HTTP09_ALLOWED, 1)
        try:
            c.setshare(self._share)
        except Exception:
            pass
        if ignore_content_length:
            try:
                c.setopt(pycurl.IGNORE_CONTENT_LENGTH, 1)
            except Exception:
                pass

    def _acquire(self, host: str) -> pycurl.Curl:
        with self._lock:
            lst = self._pool.get(host)
            if lst:
                return lst.pop()
        return pycurl.Curl()

    def _release(self, host: str, c: pycurl.Curl) -> None:
        with self._lock:
            self._pool.setdefault(host, []).append(c)

    def perform_range(self, target_url: str, start: int, end: int, http10: bool = False, ignore_content_length: bool = False) -> tuple[int, bytes, str]:
        parsed = urllib.parse.urlparse(target_url)
        host = parsed.netloc or ""
        c = self._acquire(host)
        response_buffer = io.BytesIO()
        header_buffer = io.BytesIO()
        try:
            self._configure_common(c, http10=http10, ignore_content_length=ignore_content_length)
            c.setopt(pycurl.URL, target_url)
            c.setopt(pycurl.HTTPHEADER, [
                f'Range: bytes={start}-{end}',
                'Accept-Encoding: identity',
                'Connection: keep-alive',
            ])
            c.setopt(pycurl.WRITEDATA, response_buffer)
            c.setopt(pycurl.WRITEHEADER, header_buffer)
            c.perform()
            status_code = int(c.getinfo(pycurl.RESPONSE_CODE))
            return status_code, response_buffer.getvalue(), header_buffer.getvalue().decode('utf-8', errors='replace')
        finally:
            # Avoid keeping large buffers referenced
            try:
                c.setopt(pycurl.WRITEDATA, None)
                c.setopt(pycurl.WRITEHEADER, None)
            except Exception:
                pass
            self._release(host, c)

import pyfuse3
import trio
import pycurl
import io
import os

from .db import VFSDatabase
from .providers import ProviderManager

from program.settings.manager import settings_manager
from .cache import Cache, CacheConfig

log = logger

MEDIA_SCANNERS = [
    "PMS ScannerPipe", # Plex
    "Plex Media Scan", # Plex
    "ffprobe" # Jellyfin
]


@dataclass
class PrefetchChunk:
    """Represents a chunk to be prefetched with priority information."""
    path: str
    url: str
    start: int
    end: int
    priority: int  # 0 = highest (first chunk for user), 1+ = lower priority
    user_session: str  # Unique identifier for this user's session
    created_at: float  # Timestamp for aging


class PrefetchScheduler:
    """Fair multi-user prefetch scheduler with priority-based round-robin allocation."""

    def __init__(self):
        self._queue: List[PrefetchChunk] = []
        self._active_chunks: Dict[str, PrefetchChunk] = {}  # chunk_key -> chunk
        self._user_sessions: Dict[str, int] = {}  # path -> session_counter
        self._lock = trio.Lock()
        self._scheduler_nursery = None
        self._running = False

    async def start(self):
        """Start the scheduler background task."""
        if not self._running:
            self._running = True
            # The scheduler will be started when first chunk is queued

    async def stop(self):
        """Stop the scheduler and cancel all pending chunks."""
        self._running = False
        if self._scheduler_nursery:
            self._scheduler_nursery.cancel_scope.cancel()

    def _get_user_session(self, path: str) -> str:
        """Get or create a unique session ID for this path."""
        if path not in self._user_sessions:
            self._user_sessions[path] = 0
        self._user_sessions[path] += 1
        return f"{path}#{self._user_sessions[path]}"

    def _chunk_key(self, chunk: PrefetchChunk) -> str:
        """Generate unique key for chunk tracking."""
        return f"{chunk.path}:{chunk.start}-{chunk.end}"

    async def schedule_chunks(self, path: str, url: str, chunks: List[tuple[int, int]],
                            cache_manager, fetch_func) -> None:
        """Schedule multiple chunks for prefetching with fair allocation."""
        if not chunks:
            return

        user_session = self._get_user_session(path)
        current_time = time.time()

        # Create prioritized chunks (first chunk gets priority 0, others get 1, 2, 3...)
        prefetch_chunks = []
        for i, (start, end) in enumerate(chunks):
            chunk = PrefetchChunk(
                path=path,
                url=url,
                start=start,
                end=end,
                priority=i,  # First chunk has highest priority
                user_session=user_session,
                created_at=current_time
            )
            prefetch_chunks.append(chunk)

        async with self._lock:
            # Add chunks to queue with priority ordering
            self._queue.extend(prefetch_chunks)
            # Sort by priority first, then by creation time for fairness
            self._queue.sort(key=lambda c: (c.priority, c.created_at))

            # Start scheduler if not running
            if not self._scheduler_nursery and self._running:
                # We'll start the scheduler in the background
                trio.lowlevel.spawn_system_task(self._run_scheduler, cache_manager, fetch_func)

    async def _run_scheduler(self, cache_manager, fetch_func):
        """Main scheduler loop that processes chunks fairly."""
        async with trio.open_nursery() as nursery:
            self._scheduler_nursery = nursery

            while self._running:
                try:
                    # Check if we can start more chunks
                    async with self._lock:
                        if self._queue:
                            # Get next chunk to process
                            chunk = self._queue.pop(0)
                            chunk_key = self._chunk_key(chunk)

                            # Skip if already being processed
                            if chunk_key not in self._active_chunks:
                                self._active_chunks[chunk_key] = chunk
                                nursery.start_soon(self._process_chunk, chunk, cache_manager, fetch_func)

                    # Brief pause to prevent busy waiting
                    await trio.sleep(0.1)

                except Exception as e:
                    log.trace(f"Prefetch scheduler error: {e}")

    async def _process_chunk(self, chunk: PrefetchChunk, cache_manager, fetch_func):
        """Process a single chunk fetch."""
        chunk_key = self._chunk_key(chunk)
        try:
            # Check cache first
            cached_data = cache_manager.get(chunk.path, chunk.start, chunk.end)
            if cached_data is not None:
                log.trace(f"Prefetch chunk {chunk.path} [{chunk.start}-{chunk.end}] already cached")
                return

            # Fetch the chunk
            log.trace(f"Prefetching chunk {chunk.path} [{chunk.start}-{chunk.end}] priority={chunk.priority}")
            data = await fetch_func(chunk.path, chunk.url, chunk.start, chunk.end)

            if data:
                cache_manager.put(chunk.path, chunk.start, data)
                chunk_size_mb = len(data) // (1024*1024)
                log.trace(f"Prefetched chunk {chunk.path} [{chunk.start}-{chunk.end}] = {chunk_size_mb}MB")

        except Exception as e:
            log.trace(f"Prefetch chunk failed for {chunk.path} [{chunk.start}-{chunk.end}]: {e}")
        finally:
            # Remove from active tracking
            async with self._lock:
                self._active_chunks.pop(chunk_key, None)

class RivenVFS(pyfuse3.Operations):
    """
    Riven Virtual File System - A FUSE-based VFS for streaming media content.

    This class provides a complete virtual filesystem implementation optimized for
    streaming large media files from various debrid providers. It features:

    - Efficient HTTP range request handling for seeking
    - Provider-based URL resolution with caching
    - Automatic FUSE cache invalidation
    - Persistent metadata storage
    - Robust error handling and recovery

    The VFS manages its own mount lifecycle and provides a clean API for adding,
    removing, and managing virtual files and directories.
    """

    def __init__(self, mountpoint: str, providers: Optional[Dict[str, object]] = None) -> None:
        """
        Initialize the Riven Virtual File System.

        Args:
            mountpoint: Directory where the VFS will be mounted
            providers: Dictionary of provider instances (e.g., Real-Debrid, Premiumize)

        Raises:
            OSError: If mountpoint cannot be prepared or FUSE initialization fails
        """
        super().__init__()
        self.providers: Dict[str, object] = providers or {}
        # Initialize VFS cache from settings
        try:
            fs = settings_manager.settings.filesystem
        except Exception:
            fs = None
        cache_dir = fs.cache_dir
        size_mb = fs.cache_max_size_mb
        try:
            cache_dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
        try:
            usage = shutil.disk_usage(str(cache_dir if cache_dir.exists() else cache_dir.parent))
            free_bytes = int(usage.free)
        except Exception:
            free_bytes = 0
        configured_bytes = int(size_mb) * 1024 * 1024
        effective_max_bytes = configured_bytes
        if free_bytes > 0 and configured_bytes > int(free_bytes * 0.9):
            effective_max_bytes = int(free_bytes * 0.9)
            logger.bind(component="RivenVFS").warning(
                f"cache_max_size_mb clamped to available space: {effective_max_bytes // (1024*1024)} MB"
            )
        cfg = CacheConfig(
            cache_dir=cache_dir,
            max_size_bytes=effective_max_bytes,
            ttl_seconds=int(getattr(fs, "cache_ttl_seconds", 2 * 60 * 60)),
            eviction=(getattr(fs, "cache_eviction", "LRU") or "LRU"),
            metrics_enabled=bool(getattr(fs, "cache_metrics", True)),
        )
        self.cache = Cache(cfg)

        self.provider_manager = ProviderManager(self.providers)
        self.db = VFSDatabase(provider_manager=self.provider_manager)

        # Core path <-> inode mapping for FUSE operations
        self._path_to_inode: Dict[str, int] = {"/": pyfuse3.ROOT_INODE}
        self._inode_to_path: Dict[int, str] = {pyfuse3.ROOT_INODE: "/"}
        self._next_inode = pyfuse3.ROOT_INODE + 1

        # URL cache for provider links with automatic expiration
        self._url_cache: Dict[str, Dict[str, object]] = {}
        self.url_cache_ttl = 15 * 60  # 15 minutes
        # Entry info cache to reduce redundant DB lookups in FUSE ops
        self._entry_cache: Dict[str, tuple[Optional[Dict], float]] = {}
        self._entry_cache_ttl = 30.0  # seconds

        # Shared HTTP client (pycurl + CurlShare) for connection reuse
        self.http = ProviderHTTP()

        # Chunking
        self.chunk_size = fs.chunk_size_mb * 1024 * 1024

        # Prefetch window size (number of chunks to prefetch ahead of current read position)
        # This determines how many chunks ahead we prefetch for smooth streaming
        # Will be wired to FilesystemModel configuration separately
        self.fetch_ahead_chunks = fs.fetch_ahead_chunks

        # Open file handles: fh -> handle info
        self._file_handles: Dict[int, Dict] = {}
        self._next_fh = 1

        # Opener statistics
        self._opener_stats: Dict[str, Dict] = {}

        # Per-file-handle prefetch tracking (for proper multi-user coordination)
        self._fh_prefetch_state: Dict[int, Dict] = {}  # fh -> {last_prefetch_pos: int, prefetch_window_end: int}
        # Per-path coordination for avoiding duplicate chunk fetches across file handles
        self._path_chunks_in_progress: Dict[str, Set[int]] = {}  # path -> set of chunk_starts being fetched
        self._prefetch_locks: Dict[str, trio.Lock] = {}  # path -> lock for coordinating prefetch

        # Global prefetch scheduler for fair multi-user resource allocation
        self._prefetch_scheduler = PrefetchScheduler()
        self._scheduler_started = False

        # Mount management
        self._mountpoint = os.path.abspath(mountpoint)
        self._thread = None
        self._mounted = False
        self._trio_token = None

        # Prepare mountpoint (unmount, create directory)
        self._prepare_mountpoint(self._mountpoint)

        # Initialize pyfuse3 and start main loop in background thread
        fuse_options = set(pyfuse3.default_options)
        fuse_options |= {
            'fsname=rivenvfs',
            'allow_other',
        }

        pyfuse3.init(self, self._mountpoint, fuse_options)
        self._mounted = True

        import threading
        def _fuse_runner():
            async def _async_main():
                # capture Trio token so we can call into the loop from other threads
                self._trio_token = trio.lowlevel.current_trio_token()
                await pyfuse3.main()

            try:
                # pyfuse3.main is a coroutine that needs to run in its own trio event loop
                trio.run(_async_main)
            except Exception as e:
                log.error(f"FUSE main loop exited with error: {e}")
                # Log the full traceback for debugging
                import traceback
                log.error(f"Full traceback: {traceback.format_exc()}")

        self._thread = threading.Thread(target=_fuse_runner, daemon=True)
        self._thread.start()

        log.log("VFS", f"RivenVFS mounted at {self._mountpoint}")

    def close(self) -> None:
        """Clean up and unmount the filesystem."""
        if self._mounted:
            log.log("VFS", f"Unmounting RivenVFS from {self._mountpoint}")
            self._cleanup_mountpoint(self._mountpoint)
            self._mounted = False

    def __del__(self):
        """Ensure cleanup on garbage collection."""
        try:
            self.close()
        except Exception:
            pass

    def _prepare_mountpoint(self, mountpoint: str) -> None:
        """Prepare mountpoint by killing processes and unmounting if necessary."""

        # Attempt to unmount if already mounted or in a stale state
        try:
            # Detect if something is mounted there
            is_mounted = False
            try:
                with open('/proc/mounts', 'r') as f:
                    for line in f:
                        if f" {mountpoint} " in line:
                            is_mounted = True
                            break
            except Exception:
                # If we cannot check, attempt unmounts anyway
                is_mounted = True

            if is_mounted:
                # Try a sequence of unmount strategies (graceful -> lazy)
                for cmd in (
                    ['fusermount3', '-u', '-z', mountpoint],
                    ['fusermount', '-u', '-z', mountpoint],
                    ['umount', '-l', mountpoint],
                ):
                    try:
                        subprocess.run(cmd, capture_output=True, timeout=10, check=False)
                    except (subprocess.TimeoutExpired, FileNotFoundError):
                        continue
        except Exception:
            pass

        # Ensure mountpoint directory exists (recreate if necessary)
        try:
            os.makedirs(mountpoint, exist_ok=True)
        except OSError:
            try:
                os.rmdir(mountpoint)
            except Exception:
                pass
            os.makedirs(mountpoint, exist_ok=True)

    def _cleanup_mountpoint(self, mountpoint: str) -> None:
        """Clean up mountpoint after unmounting."""
        if not self._mounted:
            return

        try:
            # Terminate FUSE main loop from the Trio event loop context
            if self._trio_token is not None:
                try:
                    trio.from_thread.run(self._terminate_async, trio_token=self._trio_token)
                except Exception as e:
                    log.warning(f"Error requesting FUSE termination: {e}")
            else:
                log.warning("No Trio token available; skipping graceful terminate")

            if self._thread and self._thread.is_alive():
                self._thread.join(timeout=5)
        except Exception as e:
            log.warning(f"Error terminating FUSE: {e}")

        try:
            # Close FUSE session after main loop has exited
            pyfuse3.close(unmount=True)
        except Exception as e:
            log.warning(f"Error closing FUSE session: {e}")

        # Force unmount if necessary
        try:
            subprocess.run(['fusermount', '-u', mountpoint],
                          capture_output=True, timeout=10, check=False)
        except Exception:
            pass

    async def _terminate_async(self) -> None:
        """Async helper to call pyfuse3.terminate() within the Trio loop."""
        try:
            pyfuse3.terminate()
        except Exception as e:
            log.warning(f"pyfuse3.terminate() failed: {e}")

    # Public API methods
    def add_file(self, path: str, url: str, size: Optional[int] = None,
                 provider: Optional[str] = None, provider_download_id: Optional[str] = None) -> bool:
        """
        Add a virtual file to the filesystem.

        Args:
            path: Virtual path where the file should appear
            url: Source URL or provider-specific restricted URL
            size: File size in bytes (optional, will be detected if not provided)
            provider: Provider name (e.g., 'realdebrid', 'premiumize')
            provider_download_id: Provider-specific download ID

        Returns:
            True if file was added successfully

        Raises:
            ValueError: If parent directory doesn't exist or path is invalid
        """
        path = self._normalize_path(path)

        # Add file to database (creates parent directories automatically)
        self.db.add_file(path, url, int(size or 0), provider=provider,
                         provider_download_id=provider_download_id)
        # Invalidate entry cache for this path and its parent
        self._entry_cache_invalidate_path(path)


        # Assign inode for the new file
        self._assign_inode(path)

        # Assign inodes for any newly created parent directories
        parent = self._normalize_path(self._get_parent_path(path))
        parent_inodes_to_invalidate = []
        while parent != "/" and parent not in self._path_to_inode:
            parent_ino = self._assign_inode(parent)
            parent_inodes_to_invalidate.append(parent_ino)
            parent = self._normalize_path(self._get_parent_path(parent))

        # Invalidate FUSE cache to ensure directory listings are updated
        # This is crucial for media players that cache directory structure
        self._invalidate_directory_cache(path, parent_inodes_to_invalidate)

        log.debug(f"Added virtual file: {path}")
        return True

    def register_existing_file(self, path: str) -> bool:
        """
        Register an existing file with the FUSE layer without creating database entries.

        This is useful when FilesystemEntry records already exist in the database
        but need to be made accessible via FUSE.

        Args:
            path: Virtual path of the existing file

        Returns:
            True if file was registered successfully
        """
        path = self._normalize_path(path)

        # Check if file exists in database
        if not self.db.exists(path):
            log.warning(f"Cannot register non-existent file: {path}")
            return False

        # Assign inode for the file
        self._assign_inode(path)

        # Assign inodes for any parent directories that need them
        parent = self._normalize_path(self._get_parent_path(path))
        parent_inodes_to_invalidate = []
        while parent != "/" and parent not in self._path_to_inode:
            parent_ino = self._assign_inode(parent)
            parent_inodes_to_invalidate.append(parent_ino)
            parent = self._normalize_path(self._get_parent_path(parent))

        # Invalidate FUSE cache to ensure directory listings are updated
        self._invalidate_directory_cache(path, parent_inodes_to_invalidate)

        log.debug(f"Registered existing file with FUSE: {path}")
        return True

    def rename_file(self, old_path: str, new_path: str) -> bool:
        """
        Rename/move a file from old_path to new_path and update FUSE layer.

        This is useful for moving files from incoming paths to their final VFS paths.

        Args:
            old_path: Current path of the file in database
            new_path: New path where the file should appear in VFS

        Returns:
            True if file was renamed successfully
        """
        old_path = self._normalize_path(old_path)
        new_path = self._normalize_path(new_path)

        # Rename in database
        if not self.db.rename(old_path, new_path):
            log.warning(f"Failed to rename file in database: {old_path} -> {new_path}")
            return False

        # Invalidate entry cache for old and new paths
        self._entry_cache_invalidate_path(old_path)
        self._entry_cache_invalidate_path(new_path)

        # Update FUSE layer
        # Remove old inode mapping if it exists
        if old_path in self._path_to_inode:
            old_inode = self._path_to_inode[old_path]
            del self._path_to_inode[old_path]
            del self._inode_to_path[old_inode]

        # Assign inode for the new path
        self._assign_inode(new_path)

        # Assign inodes for any parent directories that need them
        parent = self._normalize_path(self._get_parent_path(new_path))
        parent_inodes_to_invalidate = []
        while parent != "/" and parent not in self._path_to_inode:
            parent_ino = self._assign_inode(parent)
            parent_inodes_to_invalidate.append(parent_ino)
            parent = self._normalize_path(self._get_parent_path(parent))

        # Invalidate FUSE cache for both old and new locations
        self._invalidate_rename_cache(old_path, new_path, None)
        self._invalidate_directory_cache(new_path, parent_inodes_to_invalidate)

        log.debug(f"Renamed file: {old_path} -> {new_path}")
        return True

    def remove_file(self, path: str) -> bool:
        """
        Remove a virtual file from the filesystem.

        Args:
            path: Virtual path of the file to remove

        Returns:
            True if file was removed successfully
        """
        path = self._normalize_path(path)
        if path == "/":
            return False

        # Get inode before removal for cache invalidation
        ino = self._path_to_inode.pop(path, None)
        if ino is not None:
            self._inode_to_path.pop(ino, None)

        result = self.db.remove(path)

        # Invalidate FUSE cache for the removed entry
        if result:
            # Invalidate entry cache for removed path
            self._entry_cache_invalidate_path(path)

            self._invalidate_removed_entry_cache(path, ino)
            # Also attempt to invalidate parent directories that may have been pruned
            self._invalidate_potentially_removed_dirs(path)
            log.info(f"Removed virtual file: {path}")

        return result

    def file_exists(self, path: str) -> bool:
        """Check if a virtual file exists."""
        return self.db.exists(self._normalize_path(path))

    def get_file_info(self, path: str) -> Optional[Dict]:
        """Get information about a virtual file."""
        return self.db.get_entry(self._normalize_path(path))

    def list_directory(self, path: str) -> list[Dict]:
        """List contents of a virtual directory."""
        return self.db.list_directory(self._normalize_path(path))
    
    def get_opener_stats(self) -> Dict[str, Dict]:
        """Get statistics for each opener (process that opened files)."""
        return self._opener_stats.copy()

    # Helper methods
    def _normalize_path(self, path: str) -> str:
        """Normalize a virtual path to canonical form."""
        path = (path or "/").strip()
        if not path.startswith("/"):
            path = "/" + path
        # Remove trailing slashes except for root
        if len(path) > 1 and path.endswith("/"):
            path = path.rstrip("/")
        return path

    def _get_parent_path(self, path: str) -> str:
        """Get the parent directory path."""
        if path == "/":
            return "/"
        return "/".join(path.rstrip("/").split("/")[:-1]) or "/"

    def _join_paths(self, base: str, *parts: str) -> str:
        """Join path components safely."""
        from pathlib import PurePosixPath
        p = PurePosixPath(base)
        for part in parts:
            p = p / part
        return self._normalize_path(str(p))

    def _get_entry_cached(self, path: str) -> Optional[Dict]:
        """Cached wrapper around self.db.get_entry to reduce repeated queries."""
        import time
        path = self._normalize_path(path)
        ent_ts = self._entry_cache.get(path)
        now = time.time()
        if ent_ts is not None:
            ent, ts = ent_ts
            try:
                if now - float(ts) < float(self._entry_cache_ttl):
                    return ent
            except Exception:
                pass
        ent = self.db.get_entry(path)
        self._entry_cache[path] = (ent, now)
        return ent

    def _exists_cached(self, path: str) -> bool:
        return self._get_entry_cached(path) is not None

    def _list_directory_cached(self, path: str) -> list[Dict]:
        # Keep listing uncached for simplicity and freshness; can be cached if needed later
        return self.db.list_directory(self._normalize_path(path))

    def _entry_cache_invalidate_path(self, path: str) -> None:
        """Invalidate cached entry info for a path and its parent directory."""
        try:
            path = self._normalize_path(path)
            self._entry_cache.pop(path, None)
            parent = self._normalize_path(self._get_parent_path(path))
            self._entry_cache.pop(parent, None)
        except Exception:
            pass

    def _assign_inode(self, path: str) -> int:
        """Assign an inode number to a path."""
        if path in self._path_to_inode:
            return self._path_to_inode[path]
        ino = self._next_inode
        self._next_inode += 1
        self._path_to_inode[path] = ino
        self._inode_to_path[ino] = path
        return ino

    def _get_path_from_inode(self, inode: int) -> str:
        """Get path from inode number."""
        try:
            return self._inode_to_path[inode]
        except KeyError:
            raise pyfuse3.FUSEError(errno.ENOENT)

    @staticmethod
    def _current_time_ns() -> int:
        """Get current time in nanoseconds."""
        import time
        return int(time.time() * 1e9)

    def _invalidate_directory_cache(self, file_path: str, parent_inodes: list[int]) -> None:
        """Invalidate FUSE cache when adding files."""
        try:
            # Invalidate the immediate parent directory where the file was added
            immediate_parent = self._normalize_path(self._get_parent_path(file_path))
            if immediate_parent in self._path_to_inode:
                parent_ino = self._path_to_inode[immediate_parent]
                pyfuse3.invalidate_entry_async(parent_ino, os.path.basename(file_path).encode('utf-8'),
                                               ignore_enoent=True)
                log.trace(f"Invalidated directory entry for {file_path} in parent {immediate_parent}")

            # Also invalidate any newly created parent directories
            for ino in parent_inodes:
                try:
                    pyfuse3.invalidate_inode(ino, attr_only=True)
                    log.trace(f"Invalidated inode {ino} for newly created parent directory")
                except OSError as e:
                    # Benign if kernel has not cached the inode yet
                    if getattr(e, 'errno', None) == errno.ENOENT:
                        log.trace(f"Skip invalidating uncached inode {ino} after adding {file_path}: {e}")
                    else:
                        raise
        except OSError as e:
            # Downgrade ENOENT during add: often means kernel never cached the parent dir yet
            if getattr(e, 'errno', None) == errno.ENOENT:
                log.trace(f"Benign ENOENT while invalidating after adding {file_path}: {e}")
            else:
                log.warning(f"Failed to invalidate FUSE cache when adding {file_path}: {e}")

    def _invalidate_removed_entry_cache(self, file_path: str, inode: Optional[int]) -> None:
        """Invalidate FUSE cache when removing files."""
        try:
            parent_path = self._normalize_path(self._get_parent_path(file_path))
            if parent_path in self._path_to_inode:
                parent_ino = self._path_to_inode[parent_path]
                pyfuse3.invalidate_entry_async(parent_ino, os.path.basename(file_path).encode('utf-8'),
                                               deleted=inode or 0, ignore_enoent=True)
                log.trace(f"Invalidated directory entry for removed {file_path}")
        except OSError as e:
            if getattr(e, 'errno', None) == errno.ENOENT:
                log.trace(f"Benign ENOENT while invalidating after removing {file_path}: {e}")
            else:
                log.warning(f"Failed to invalidate FUSE cache when removing {file_path}: {e}")

    def _invalidate_potentially_removed_dirs(self, file_path: str) -> None:
        """Invalidate parent directory entries that may have been removed due to pruning."""
        try:
            parent = self._normalize_path(self._get_parent_path(file_path))
            grandparent = self._normalize_path(self._get_parent_path(parent))

            # Invalidate the entry for 'parent' under its parent directory (grandparent)
            if grandparent in self._path_to_inode:
                name = os.path.basename(parent.rstrip('/'))
                if name:
                    pyfuse3.invalidate_entry_async(self._path_to_inode[grandparent], name.encode('utf-8'), ignore_enoent=True)
                    log.trace(f"Invalidated potential removed dir entry '{name}' under {grandparent}")

            # One more level up (e.g., title dir)
            ggparent = self._normalize_path(self._get_parent_path(grandparent))
            gname = os.path.basename(grandparent.rstrip('/'))
            if ggparent in self._path_to_inode and gname:
                pyfuse3.invalidate_entry_async(self._path_to_inode[ggparent], gname.encode('utf-8'), ignore_enoent=True)
                log.trace(f"Invalidated potential removed dir entry '{gname}' under {ggparent}")
        except Exception as e:
            if getattr(e, 'errno', None) == errno.ENOENT:
                log.trace(f"Benign ENOENT while invalidating parent dirs for {file_path}: {e}")
            else:
                log.warning(f"Failed to invalidate parent dir entries for {file_path}: {e}")
        except OSError as e:
            log.warning(f"Failed to invalidate FUSE cache when removing {file_path}: {e}")

    def _invalidate_rename_cache(self, old_path: str, new_path: str, inode: Optional[int]) -> None:
        """Invalidate FUSE cache when renaming files."""
        try:
            # Invalidate old parent directory
            old_parent = self._normalize_path(self._get_parent_path(old_path))
            if old_parent in self._path_to_inode:
                old_parent_ino = self._path_to_inode[old_parent]
                pyfuse3.invalidate_entry_async(old_parent_ino, os.path.basename(old_path).encode('utf-8'),
                                               deleted=inode or 0, ignore_enoent=True)
                log.trace(f"Invalidated old directory entry for renamed {old_path}")

            # Invalidate new parent directory
            new_parent = self._normalize_path(self._get_parent_path(new_path))
            if new_parent in self._path_to_inode:
                new_parent_ino = self._path_to_inode[new_parent]
                pyfuse3.invalidate_entry_async(new_parent_ino, os.path.basename(new_path).encode('utf-8'),
                                               ignore_enoent=True)
                log.debug(f"Invalidated new directory entry for renamed {new_path}")
        except OSError as e:
            log.warning(f"Failed to invalidate FUSE cache when renaming {old_path} to {new_path}: {e}")

    # FUSE Operations
    async def getattr(self, inode: int, ctx=None) -> pyfuse3.EntryAttributes:
        """Get file/directory attributes."""
        try:
            path = self._get_path_from_inode(inode)

            attrs = pyfuse3.EntryAttributes()
            attrs.st_ino = inode
            attrs.generation = 0
            attrs.entry_timeout = 300
            attrs.attr_timeout = 300
            attrs.st_uid = os.getuid() if hasattr(os, 'getuid') else 0
            attrs.st_gid = os.getgid() if hasattr(os, 'getgid') else 0
            attrs.st_blksize = 131072  # Hint larger block size to kernel (128 KiB)
            attrs.st_blocks = 1

            import stat
            now_ns = self._current_time_ns()
            attrs.st_atime_ns = now_ns
            attrs.st_mtime_ns = now_ns
            attrs.st_ctime_ns = now_ns

            # Special case for root directory
            if path == "/":
                attrs.st_mode = stat.S_IFDIR | 0o755
                attrs.st_nlink = 2
                attrs.st_size = 0
                return attrs

            # For other paths, check database
            entry_info = self._get_entry_cached(path)
            if entry_info is None:
                raise pyfuse3.FUSEError(errno.ENOENT)

            if entry_info["is_directory"]:
                attrs.st_mode = stat.S_IFDIR | 0o755
                attrs.st_nlink = 2
                attrs.st_size = 0
            else:
                attrs.st_mode = stat.S_IFREG | 0o644
                attrs.st_nlink = 1
                size = int(entry_info.get("size") or 0)
                if size == 0:
                    size = 1337 * 1024 * 1024  # Default size when unknown
                attrs.st_size = size

            return attrs
        except pyfuse3.FUSEError:
            raise
        except Exception as ex:
            log.exception("getattr error for inode=%s: %s", inode, ex)
            raise pyfuse3.FUSEError(errno.EIO)

    async def lookup(self, parent_inode: int, name: bytes, ctx=None) -> pyfuse3.EntryAttributes:
        """Look up a directory entry."""
        try:
            parent_path = self._get_path_from_inode(parent_inode)
            name_str = name.decode('utf-8')

            if name_str == '.':
                return await self.getattr(parent_inode)
            if name_str == '..':
                parent_inode = self._path_to_inode.get(self._get_parent_path(parent_path), pyfuse3.ROOT_INODE)
                return await self.getattr(parent_inode)

            child_path = self._join_paths(parent_path, name_str)
            if not self._exists_cached(child_path):
                raise pyfuse3.FUSEError(errno.ENOENT)

            child_inode = self._assign_inode(child_path)
            return await self.getattr(child_inode)
        except pyfuse3.FUSEError:
            raise
        except Exception as ex:
            log.exception("lookup error: parent=%s name=%s: %s", parent_inode, name, ex)
            raise pyfuse3.FUSEError(errno.EIO)

    async def opendir(self, inode: int, ctx):
        """Open a directory for reading."""
        try:
            path = self._get_path_from_inode(inode)

            # Special case for root directory
            if path == "/":
                return inode  # Return the inode as file handle

            entry_info = self._get_entry_cached(path)
            if entry_info is None or not entry_info["is_directory"]:
                raise pyfuse3.FUSEError(errno.ENOTDIR)
            return inode  # Return the inode as file handle for directories
        except pyfuse3.FUSEError:
            raise
        except Exception as ex:
            log.exception("opendir error for inode=%s: %s", inode, ex)
            raise pyfuse3.FUSEError(errno.EIO)

    async def readdir(self, inode: int, off: int, token: pyfuse3.ReaddirToken):
        """Read directory entries."""
        try:
            path = self._get_path_from_inode(inode)
            entries = self._list_directory_cached(path)

            # Build directory listing
            items = [
                (b'.', inode),
                (b'..', self._path_to_inode.get(self._get_parent_path(path), pyfuse3.ROOT_INODE))
            ]

            for entry in entries:
                name_bytes = entry["name"].encode('utf-8')
                child_inode = self._assign_inode(self._join_paths(path, entry["name"]))
                items.append((name_bytes, child_inode))

            # Send directory entries starting from offset
            for idx in range(off, len(items)):
                name_bytes, child_ino = items[idx]
                attrs = await self.getattr(child_ino)
                if not pyfuse3.readdir_reply(token, name_bytes, attrs, idx + 1):
                    break
        except pyfuse3.FUSEError:
            raise
        except Exception as ex:
            log.exception("readdir error for inode=%s: %s", inode, ex)
            raise pyfuse3.FUSEError(errno.EIO)

    async def open(self, inode: int, flags: int, ctx):
        """Open a file for reading."""
        try:
            path = self._get_path_from_inode(inode)
            file_info = self._get_entry_cached(path)

            opener_pid = ctx.pid if ctx and hasattr(ctx, 'pid') else 0
            opener_name = None
            opener_cmdline = None
            if opener_pid > 0:
                try:
                    with open(f"/proc/{opener_pid}/comm", "r") as f:
                        opener_name = f.read().strip()
                    with open(f"/proc/{opener_pid}/cmdline", "r") as f:
                        opener_cmdline = f.read().replace('\0', ' ').strip()
                except Exception:
                    pass

            opener_name = opener_name or "unknown"
            log.trace(f"Opening file {path} (inode={inode}) with flags {flags} by PID {opener_pid} ({opener_name})")

            self._opener_stats.setdefault(opener_name, {"bytes_read": 0, "files_opened": 0})["files_opened"] += 1

            if file_info is None or file_info["is_directory"]:
                raise pyfuse3.FUSEError(errno.ENOENT)

            # Only allow read access
            if flags & os.O_RDWR or flags & os.O_WRONLY:
                raise pyfuse3.FUSEError(errno.EACCES)

            # Create file handle with readahead buffer
            fh = self._next_fh
            self._next_fh += 1
            # Minimal handle info
            self._file_handles[fh] = {
                "path": path,
                "file_info": file_info,
                "opener_name": opener_name,
                "is_scanner": opener_name in MEDIA_SCANNERS,
                "buffers": [],
                "sequential_reads": 0,
                "last_read_end": 0,
            }

            # Initialize per-file-handle prefetch state
            self._fh_prefetch_state[fh] = {
                'last_prefetch_pos': -1,
                'prefetch_window_end': -1
            }

            log.trace(f"Opened file {path} with handle {fh}")
            return pyfuse3.FileInfo(fh=fh)
        except pyfuse3.FUSEError:
            raise

    async def read(self, fh: int, off: int, size: int) -> bytes:
        """Simplified read path: fixed-size chunking and straightforward sequential prefetch."""
        try:
            try:
                self.cache.maybe_log_stats()
            except Exception:
                pass

            handle_info = self._file_handles.get(fh) or {}
            if not handle_info:
                raise pyfuse3.FUSEError(errno.EBADF)
            path = handle_info.get("path") or ""
            if not path:
                raise pyfuse3.FUSEError(errno.EBADF)

            file_info = handle_info.get("file_info") or self._get_entry_cached(path)
            if file_info is None or file_info.get("is_directory"):
                raise pyfuse3.FUSEError(errno.ENOENT)
            size_raw = file_info.get("size")
            file_size = int(size_raw) if size_raw is not None else None

            if size == 0:
                return b""

            # Resolve URL with caching
            import time
            now = time.time()
            cached_url_info = self._url_cache.get(path)
            if not cached_url_info or (now - float(cached_url_info.get("timestamp", 0))) > self.url_cache_ttl:
                url = self.db.get_download_url(path, for_http=True, force_resolve=False)
                if not url:
                    raise pyfuse3.FUSEError(errno.ENOENT)
                self._url_cache[path] = {"url": url, "timestamp": now}
            else:
                url = str(cached_url_info.get("url"))

            is_scanner = handle_info.get("is_scanner", False)
            if is_scanner:
                # Check if scanner has been promoted to larger reads after 3 sequential reads
                sequential_reads = handle_info.get("sequential_reads", 0)
                is_promoted = sequential_reads >= 3

                if is_promoted:
                    # Use chunk_size for promoted scanner reads to reduce HTTP requests
                    fetch_start = off
                    fetch_end = off + max(size, self.chunk_size) - 1
                    if file_size is not None:
                        fetch_end = min(fetch_end, file_size - 1)
                else:
                    # For non-promoted scanners, fetch exactly the requested range
                    fetch_start = off
                    fetch_end = off + size - 1
                    if file_size is not None:
                        fetch_end = min(fetch_end, file_size - 1)

                if fetch_end < fetch_start:
                    return b""

                # Try cache first for exactly what kernel asked
                cached_bytes = self.cache.get(path, off, off + size - 1)
                if cached_bytes is not None:
                    returned_data = cached_bytes
                else:
                    # Fetch the determined range (exact for non-promoted, larger for promoted)
                    data = await self._fetch_data_block(path, url, fetch_start, fetch_end)
                    if data:
                        # Cache the fetched data
                        self.cache.put(path, fetch_start, data)

                        # Always slice to return exactly what was requested
                        start_idx = off - fetch_start
                        returned_data = data[start_idx:start_idx + size]
                    else:
                        returned_data = b""

                # Track sequential reads for scanners
                if off == handle_info.get("last_read_end", 0):
                    handle_info["sequential_reads"] = handle_info.get("sequential_reads", 0) + 1
                handle_info["last_read_end"] = off + len(returned_data)

                # Data integrity check: ensure we return exactly the requested size
                # But account for file size boundaries - we can't read past EOF
                expected_size = size
                if file_size is not None and off + size > file_size:
                    expected_size = max(0, file_size - off)

                if returned_data and len(returned_data) != expected_size:
                    # This should never happen, but if it does, truncate/pad to exact size
                    if len(returned_data) > expected_size:
                        returned_data = returned_data[:expected_size]
                        log.warning(f"Scanner read returned too much data: got {len(returned_data)} bytes, expected {expected_size}")
                    else:
                        log.error(f"Scanner read returned too little data: got {len(returned_data)} bytes, expected {expected_size}")
                        # For media playbook, returning partial data is worse than returning empty
                        returned_data = b""

                opener = handle_info.get("opener_name")
                if opener and returned_data:
                    self._opener_stats[opener]["bytes_read"] += len(returned_data)
                return returned_data
            else:
                # Normal chunking logic
                # Calculate request and aligned chunk boundaries (use inclusive end)
                request_start = off
                request_end = off + size - 1
                if file_size is not None:
                    # Clamp to last byte index
                    request_end = min(request_end, file_size - 1)
                if request_end < request_start:
                    return b""

                # Determine the range of chunks needed to satisfy the request
                first_chunk_start = (request_start // self.chunk_size) * self.chunk_size
                last_chunk_start = (request_end // self.chunk_size) * self.chunk_size

                # For prefetch calculation (next chunk after the last chunk we need)
                next_aligned_start = last_chunk_start + self.chunk_size
                next_aligned_end = next_aligned_start + self.chunk_size - 1

                # Try cache first for exactly what kernel asked
                cached_bytes = self.cache.get(path, request_start, request_end)
                if cached_bytes is not None:
                    returned_data = cached_bytes
                    log.trace(f"fh={fh} path={path} start={request_start} end={request_end} bytes={request_end - request_start} source=cache-hit")
                else:
                    # Fetch all chunks needed to satisfy the request
                    all_data = b""
                    current_chunk_start = first_chunk_start

                    while current_chunk_start <= last_chunk_start:
                        chunk_end = current_chunk_start + self.chunk_size - 1
                        if file_size is not None:
                            chunk_end = min(chunk_end, file_size - 1)

                        # Try cache first for this chunk
                        chunk_data = self.cache.get(path, current_chunk_start, chunk_end)
                        if chunk_data is None:
                            # Fetch this chunk
                            chunk_data = await self._fetch_data_block(path, url, current_chunk_start, chunk_end)
                            if chunk_data:
                                self.cache.put(path, current_chunk_start, chunk_data)

                        if chunk_data:
                            all_data += chunk_data

                        current_chunk_start += self.chunk_size

                    data = all_data

                    if data:
                        log.trace(f"fh={fh} path={path} off={request_start} end={request_end} bytes={request_end - request_start} source=fetch")

                    if not data:
                        returned_data = b""
                    else:
                        # Return only the requested subrange from the fetched data
                        start_idx = request_start - first_chunk_start
                        need_len = request_end - request_start + 1
                        returned_data = data[start_idx:start_idx + need_len]

                # Data integrity check: ensure we return exactly the requested size
                # The expected_size is already correctly calculated as request_end - request_start + 1
                # which accounts for file size clamping done earlier
                expected_size = request_end - request_start + 1
                if returned_data and len(returned_data) != expected_size:
                    # This should never happen, but if it does, truncate/pad to exact size
                    if len(returned_data) > expected_size:
                        returned_data = returned_data[:expected_size]
                        log.warning(f"Normal read returned too much data: got {len(returned_data)} bytes, expected {expected_size}")
                    else:
                        log.error(f"Normal read returned too little data: got {len(returned_data)} bytes, expected {expected_size}")
                        # For media playback, returning partial data is worse than returning empty
                        returned_data = b""

                if off == handle_info.get("last_read_end", 0):
                    handle_info["sequential_reads"] = handle_info.get("sequential_reads", 0) + 1
                handle_info["last_read_end"] = off + len(returned_data)

                # Prefetch if promoted
                if handle_info["sequential_reads"] >= 3:
                    if file_size is None or next_aligned_start < file_size:
                        pf_end = next_aligned_end if file_size is None else min(next_aligned_end, file_size - 1)
                        trio.lowlevel.spawn_system_task(self._prefetch_next_chunk, fh, path, url, next_aligned_start, pf_end)

                opener = handle_info.get("opener_name")
                if opener and returned_data:
                    self._opener_stats[opener]["bytes_read"] += len(returned_data)
                return returned_data
        except pyfuse3.FUSEError:
            raise
        except Exception as ex:
            log.exception("read(simple) error fh=%s: %s", fh, ex)
            raise pyfuse3.FUSEError(errno.EIO)

    async def _prefetch_next_chunk(self, fh: int, path: str, url: str, start: int, end: int) -> None:
        """Prefetch multiple chunk_size requests for fetch_ahead_chunks chunks.

        Architecture:
        - chunk_size (eg. 32MB) = individual CDN request size
        - fetch_ahead_chunks (eg. 4) = number of chunks to prefetch ahead
        - Schedules 4 x 32MB requests = 128MB total prefetch window
        - Coordinates across multiple users reading the same file with fair scheduling
        """
        if fh not in self._file_handles:
            return

        # Get file size to avoid prefetching beyond EOF
        handle_info = self._file_handles[fh]
        file_info = handle_info.get("file_info")
        file_size = None
        if file_info:
            size_raw = file_info.get("size")
            file_size = int(size_raw) if size_raw is not None else None

        # Get or create prefetch lock for this path
        if path not in self._prefetch_locks:
            self._prefetch_locks[path] = trio.Lock()

        async with self._prefetch_locks[path]:
            try:
                # Start scheduler on first use (lazy initialization)
                if not self._scheduler_started:
                    await self._prefetch_scheduler.start()
                    self._scheduler_started = True

                # Initialize per-file-handle prefetch state
                if fh not in self._fh_prefetch_state:
                    self._fh_prefetch_state[fh] = {
                        'last_prefetch_pos': -1,
                        'prefetch_window_end': -1
                    }

                # Initialize per-path chunk tracking
                if path not in self._path_chunks_in_progress:
                    self._path_chunks_in_progress[path] = set()

                fh_state = self._fh_prefetch_state[fh]
                path_chunks = self._path_chunks_in_progress[path]

                # Determine prefetch window: from current file handle's read position for fetch_ahead_chunks chunks
                # This ensures each file handle only prefetches its own window, not the entire file
                desired_prefetch_end = start + (self.fetch_ahead_chunks * self.chunk_size) - 1

                # Clamp prefetch window to file size boundaries
                if file_size is not None:
                    desired_prefetch_end = min(desired_prefetch_end, file_size - 1)

                # If we're already at or past EOF, nothing to prefetch
                if file_size is not None and start >= file_size:
                    return

                # Calculate chunk-aligned prefetch start to ensure we cover the current read position
                read_chunk_start = (start // self.chunk_size) * self.chunk_size

                # Optimize: only prefetch the NEW portion beyond what this file handle has already prefetched
                if fh_state['last_prefetch_pos'] >= start:
                    # This file handle has already prefetched past this read position
                    # Only prefetch the new portion beyond our last prefetch for this file handle
                    prefetch_start = fh_state['last_prefetch_pos'] + 1
                    prefetch_end = desired_prefetch_end

                    # If there's nothing new to prefetch for this file handle, skip
                    if prefetch_start > prefetch_end:
                        return
                else:
                    # This file handle hasn't prefetched this area yet, prefetch from the chunk containing current read
                    prefetch_start = read_chunk_start
                    prefetch_end = desired_prefetch_end

                # Calculate chunk-aligned ranges to prefetch
                chunks_to_fetch = []
                current_chunk_start = (prefetch_start // self.chunk_size) * self.chunk_size

                while current_chunk_start <= prefetch_end:
                    chunk_end = min(current_chunk_start + self.chunk_size - 1, prefetch_end)

                    # Clamp chunk end to file size
                    if file_size is not None:
                        chunk_end = min(chunk_end, file_size - 1)

                    # Skip if chunk start is beyond file end
                    if file_size is not None and current_chunk_start >= file_size:
                        break

                    # Skip if already cached
                    if self.cache.get(path, current_chunk_start, chunk_end) is not None:
                        current_chunk_start += self.chunk_size
                        continue

                    # Skip if already being fetched by any file handle for this path
                    if current_chunk_start in path_chunks:
                        current_chunk_start += self.chunk_size
                        continue

                    # Mark as in-progress IMMEDIATELY to prevent race conditions
                    path_chunks.add(current_chunk_start)
                    chunks_to_fetch.append((current_chunk_start, chunk_end))
                    current_chunk_start += self.chunk_size

                # Update last prefetch position for this specific file handle
                fh_state['last_prefetch_pos'] = prefetch_end
                fh_state['prefetch_window_end'] = prefetch_end

                # Schedule chunk fetches using global scheduler for fair multi-user allocation
                if chunks_to_fetch:
                    window_size_mb = (prefetch_end - prefetch_start + 1) // (1024*1024)
                    log.trace(f"Scheduling {len(chunks_to_fetch)} chunks for {path}: NEW window [{prefetch_start}-{prefetch_end}] = {window_size_mb}MB")

                    # Chunks are already marked as in-progress above to prevent race conditions
                    # Schedule chunks with the global scheduler for fair allocation
                    await self._prefetch_scheduler.schedule_chunks(
                        path=path,
                        url=url,
                        chunks=chunks_to_fetch,
                        cache_manager=self.cache,
                        fetch_func=self._fetch_data_block_with_cleanup
                    )
                else:
                    log.trace(f"No NEW chunks to prefetch for fh={fh} path={path}: desired_end={desired_prefetch_end}, fh_last_pos={fh_state['last_prefetch_pos']}")

            except Exception as e:
                log.trace(f"Prefetch coordination failed for {path}: {e}")
                # Best-effort: ignore prefetch errors

    async def _fetch_data_block_with_cleanup(self, path: str, url: str, start: int, end: int) -> bytes:
        """Wrapper for _fetch_data_block that handles prefetch state cleanup."""
        try:
            data = await self._fetch_data_block(path, url, start, end)
            return data
        finally:
            # Clean up in-progress tracking for this path
            if path in self._path_chunks_in_progress:
                self._path_chunks_in_progress[path].discard(start)

    async def release(self, fh: int):
        """Release/close a file handle."""
        try:
            handle_info = self._file_handles.pop(fh, None)
            if handle_info:
                path = handle_info.get("path")

                # Clean up per-file-handle prefetch state
                self._fh_prefetch_state.pop(fh, None)

                # Clean up per-path state if no other handles are using this path
                if path:
                    remaining_handles = [h for h in self._file_handles.values() if h.get("path") == path]
                    if not remaining_handles:
                        # No other handles for this path, clean up shared path state
                        self._path_chunks_in_progress.pop(path, None)
                        self._prefetch_locks.pop(path, None)
            log.trace(f"Released file handle {fh}")
        except Exception as ex:
            log.exception("release error fh=%s: %s", fh, ex)
            raise pyfuse3.FUSEError(errno.EIO)

    async def flush(self, fh: int) -> None:
        """Flush file data (no-op for read-only filesystem)."""
        return None

    async def fsync(self, fh: int, datasync: bool) -> None:
        """Sync file data (no-op for read-only filesystem)."""
        return None

    async def access(self, inode: int, mode: int, ctx=None) -> None:
        """Check file access permissions.
        Be permissive for write checks to avoid client false negatives; actual writes still fail with EROFS.
        """
        try:
            # Check existence only; permission enforcement happens at operation time
            path = self._get_path_from_inode(inode)
            if not self.db.exists(path):
                raise pyfuse3.FUSEError(errno.ENOENT)
            return None
        except pyfuse3.FUSEError:
            raise
        except Exception as ex:
            log.exception("access error inode=%s mode=%s: %s", inode, mode, ex)
            raise pyfuse3.FUSEError(errno.EIO)

    async def unlink(self, parent_inode: int, name: bytes, ctx):
        """Remove a file."""
        try:
            # Deny user-initiated deletes; managed via provider interfaces only
            log.info(f"Denied unlink via FUSE: parent_inode={parent_inode}, name={name!r}")
            raise pyfuse3.FUSEError(errno.EROFS)
        except pyfuse3.FUSEError:
            raise
        except Exception as ex:
            log.exception("unlink error: parent=%s name=%s: %s", parent_inode, name, ex)
            raise pyfuse3.FUSEError(errno.EIO)

    async def rmdir(self, parent_inode: int, name: bytes, ctx):
        """Remove a directory."""
        try:
            # Deny user-initiated directory deletes; managed via provider interfaces only
            log.info(f"Denied rmdir via FUSE: parent_inode={parent_inode}, name={name!r}")
            raise pyfuse3.FUSEError(errno.EROFS)
        except pyfuse3.FUSEError:
            raise
        except Exception as ex:
            log.exception("rmdir error: parent=%s name=%s: %s", parent_inode, name, ex)
            raise pyfuse3.FUSEError(errno.EIO)

    async def rename(self, parent_inode_old: int, name_old: bytes,
                    parent_inode_new: int, name_new: bytes, flags: int, ctx):
        """Rename/move a file or directory."""
        try:
            # Allow only internal/provider-driven renames; deny user-initiated via FUSE
            log.info(
                f"Denied rename via FUSE: old_parent={parent_inode_old}, new_parent={parent_inode_new}, "
                f"name_old={name_old!r}, name_new={name_new!r}, flags={flags}"
            )
            raise pyfuse3.FUSEError(errno.EROFS)
        except pyfuse3.FUSEError:
            raise
        except Exception as ex:
            log.exception("rename error: old_parent=%s new_parent=%s name_old=%s name_new=%s: %s",
                          parent_inode_old, parent_inode_new, name_old, name_new, ex)
            raise pyfuse3.FUSEError(errno.EIO)
        except pyfuse3.FUSEError:
            raise
        except Exception as ex:
            log.exception("rename error: old=%s/%s new=%s/%s: %s",
                         parent_inode_old, name_old, parent_inode_new, name_new, ex)
            raise pyfuse3.FUSEError(errno.EIO)

    # HTTP helpers

    def _http_range_request(self, target_url: str, start: int, end: int) -> tuple[int, bytes]:
        try:
            status_code, body, _ = self.http.perform_range(target_url, start, end, http10=False, ignore_content_length=False)
            return status_code, body
        except pycurl.error as e:
            log.warning(f"pycurl error for {target_url} range {start}-{end}: {e}")
            # Content-Length workaround (HTTP/1.0 + ignore length)
            if e.args and e.args[0] == 8:
                status_code, body, _ = self.http.perform_range(target_url, start, end, http10=True, ignore_content_length=True)
                log.info(f"Content-Length workaround successful for {target_url}")
                return status_code, body
            raise
        except Exception:
            raise

    async def _fetch_data_block(self, path: str, target_url: str, start: int, end: int) -> bytes:
        max_attempts = 4
        import time
        backoffs = [0.2, 0.5, 1.0]
        for attempt in range(max_attempts):
            try:
                status, content = await trio.to_thread.run_sync(
                    self._http_range_request, target_url, start, end
                )
                if status == 206:
                    log.trace(f"path={path} start={start} end={end} bytes={end-start}")
                    return content
                elif status == 200 and start == 0:
                    # Full body returned; slice to requested range length
                    log.trace(f"path={path} start={0} end={end + 1} bytes={end + 1}")
                    return content[:(end - start + 1)]
                elif status == 416:
                    # Requested range not satisfiable; treat as EOF
                    return b''
                elif status == 404:
                    # File not found - URL likely expired, try refreshing once
                    if attempt == 0:  # Only try refresh on first attempt
                        self._url_cache.pop(path, None)
                        fresh_url = self.db.get_download_url(path, for_http=True, force_resolve=True)
                        if fresh_url and fresh_url != target_url:
                            self._url_cache[path] = {'url': fresh_url, 'timestamp': time.time()}
                            target_url = fresh_url
                            log.info(f"Retrying with fresh URL after 404 for {path}")
                            await trio.sleep(0.5)  # Brief pause before retry
                            continue
                    # No fresh URL or still 404 after refresh
                    raise pyfuse3.FUSEError(errno.ENOENT)
                elif status == 403:
                    # Forbidden - could be rate limiting or auth issue, don't refresh URL
                    log.warning(f"HTTP 403 Forbidden for {path} (attempt {attempt + 1})")
                    if attempt < max_attempts - 1:
                        await trio.sleep(backoffs[min(attempt, len(backoffs) - 1)])
                        continue
                    raise pyfuse3.FUSEError(errno.EACCES)
                elif status == 410:
                    # Gone - URL expired, try refreshing once
                    if attempt == 0:  # Only try refresh on first attempt
                        self._url_cache.pop(path, None)
                        fresh_url = self.db.get_download_url(path, for_http=True, force_resolve=True)
                        if fresh_url and fresh_url != target_url:
                            self._url_cache[path] = {'url': fresh_url, 'timestamp': time.time()}
                            target_url = fresh_url
                            log.info(f"Retrying with fresh URL after 404 for {path}")
                            await trio.sleep(0.5)  # Brief pause before retry
                            continue
                    raise pyfuse3.FUSEError(errno.ENOENT)
                elif status == 429:
                    # Rate limited - back off exponentially, don't refresh URL
                    log.warning(f"HTTP 429 Rate Limited for {path} (attempt {attempt + 1})")
                    if attempt < max_attempts - 1:
                        backoff_time = min(backoffs[min(attempt, len(backoffs) - 1)] * 2, 5.0)
                        await trio.sleep(backoff_time)
                        continue
                    raise pyfuse3.FUSEError(errno.EAGAIN)
                elif status == 200 and start > 0:
                    # Server doesn't support ranges but returned full content
                    log.warning(f"Server returned full content instead of range for {path}")
                    raise pyfuse3.FUSEError(errno.EIO)
                else:
                    # Other unexpected status codes
                    log.warning(f"Unexpected HTTP status {status} for {path}")
                    raise pyfuse3.FUSEError(errno.EIO)
            except pycurl.error as e:
                error_code = e.args[0] if e.args else 0
                log.warning(f"HTTP request failed (attempt {attempt + 1}/{max_attempts}) for {path}: {e}")

                # Only refresh URL on connection-related errors, not rate limiting
                if error_code in (6, 7, 28) and attempt == 0:  # Host resolution, connection, timeout
                    self._url_cache.pop(path, None)
                    fresh_url = self.db.get_download_url(path, for_http=True, force_resolve=True)
                    if fresh_url and fresh_url != target_url:
                        self._url_cache[path] = {'url': fresh_url, 'timestamp': time.time()}
                        target_url = fresh_url
                        log.info(f"Retrying with fresh URL after connection error for {path}")

                if attempt < max_attempts - 1:
                    await trio.sleep(backoffs[min(attempt, len(backoffs) - 1)])
                    continue
                raise pyfuse3.FUSEError(errno.EIO)
        raise pyfuse3.FUSEError(errno.EIO)


