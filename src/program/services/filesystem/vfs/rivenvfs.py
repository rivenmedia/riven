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
from kink import di
from loguru import logger
import subprocess
from typing import Dict, List, Optional, Set, TypedDict
from http import HTTPStatus

import threading

from program.services.downloaders import Downloader
import httpx

from program.settings.models import FilesystemModel


import pyfuse3
import trio
import os

from .db import VFSDatabase, VFSEntry

from program.settings.manager import settings_manager
from .cache import Cache, CacheConfig

log = logger


@dataclass
class VFSNode:
    """
    Represents a node (file or directory) in the VFS tree.

    This is the core data structure for the in-memory VFS tree, providing
    O(1) lookups and eliminating the need for path resolution.

    Attributes:
        name: Name of this node (e.g., "Frozen.mkv" or "movies")
        is_directory: True if this is a directory, False if it's a file
        base_path: Path in database for files (e.g., "/movies/Frozen.mkv")
                   For profile paths, this points to the canonical base path.
                   For directories, this is None.
        inode: FUSE inode number assigned to this node
        children: Dict of child name -> VFSNode (only for directories)
        parent: Reference to parent VFSNode (None for root)

        # Cached file metadata (for files only, eliminates DB queries in getattr)
        file_size: File size in bytes (None for directories)
        created_at: Creation timestamp as ISO string (None for directories)
        updated_at: Modification timestamp as ISO string (None for directories)
        entry_type: Entry type ("media" or "subtitle", None for directories)
    """

    name: str
    is_directory: bool
    base_path: Optional[str] = None
    inode: Optional[pyfuse3.InodeT] = None
    parent: Optional["VFSNode"] = None

    # Cached metadata for files (eliminates database queries)
    file_size: Optional[int] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    entry_type: Optional[str] = None

    def __post_init__(self):
        """Initialize children dict after dataclass init."""
        if not hasattr(self, "_children"):
            self._children: Dict[str, VFSNode] = {}

    @property
    def children(self) -> Dict[str, "VFSNode"]:
        """Get children dict."""
        if not hasattr(self, "_children"):
            self._children = {}
        return self._children

    def get_full_path(self) -> str:
        """Get the full VFS path for this node by walking up to root."""
        if self.parent is None:
            return "/"

        parts = []
        current = self
        while current.parent is not None:
            parts.append(current.name)
            current = current.parent

        if not parts:
            return "/"

        return "/" + "/".join(reversed(parts))

    def add_child(self, child: "VFSNode") -> None:
        """Add a child node to this directory."""
        if not self.is_directory:
            raise ValueError(f"Cannot add child to non-directory node: {self.name}")

        child.parent = self
        self.children[child.name] = child

    def remove_child(self, name: str) -> Optional["VFSNode"]:
        """Remove and return a child node by name."""
        child = self.children.pop(name, None)
        if child:
            child.parent = None
        return child

    def get_child(self, name: str) -> Optional["VFSNode"]:
        """Get a child node by name."""
        return self.children.get(name)

    def __repr__(self) -> str:
        return f"VFSNode(name={self.name!r}, is_dir={self.is_directory}, inode={self.inode}, children={len(self.children)})"


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

    def __init__(self, vfs_instance):
        self._vfs = vfs_instance  # Reference to VFS for accessing chunk locks
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

    async def schedule_chunks(
        self,
        path: str,
        url: str,
        chunks: List[tuple[int, int]],
        cache_manager: Cache,
        fetch_func,
    ) -> None:
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
                created_at=current_time,
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
                trio.lowlevel.spawn_system_task(
                    self._run_scheduler, cache_manager, fetch_func
                )

    async def _run_scheduler(self, cache_manager: Cache, fetch_func):
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
                                nursery.start_soon(
                                    self._process_chunk,
                                    chunk,
                                    cache_manager,
                                    fetch_func,
                                )

                    # Brief pause to prevent busy waiting
                    await trio.sleep(0.1)

                except Exception as e:
                    log.debug(f"Prefetch scheduler error: {e}")

    async def _process_chunk(
        self,
        chunk: PrefetchChunk,
        cache_manager: Cache,
        fetch_func,
    ):
        """Process a single chunk fetch with per-chunk locking to prevent duplicate fetches."""
        chunk_key = self._chunk_key(chunk)
        try:
            # Get lock for this specific chunk to prevent duplicate fetches
            # This is shared with read() method's fetch_one_chunk to prevent races
            # Note: async with trio.Lock() is non-blocking for the event loop - it yields
            # control to other tasks while waiting, so this doesn't block concurrent reads
            chunk_lock = await self._vfs._get_chunk_lock(chunk.path, chunk.start)

            async with chunk_lock:
                # Check cache first (inside lock to prevent race with read())
                cached_data = await trio.to_thread.run_sync(
                    lambda: cache_manager.get(chunk.path, chunk.start, chunk.end)
                )
                if cached_data is not None:
                    # Already cached, skip (no log needed - reduces noise)
                    return

                # Fetch the chunk (while holding lock to prevent duplicate fetches)
                # This is safe because Trio's async with yields control to other tasks
                data = await fetch_func(chunk.path, chunk.url, chunk.start, chunk.end)

                if data:
                    await trio.to_thread.run_sync(
                        lambda: cache_manager.put(chunk.path, chunk.start, data)
                    )
                    chunk_size_mb = len(data) / (1024 * 1024)
                    log.debug(
                        f"Prefetched chunk: path={chunk.path} range=[{chunk.start}-{chunk.end}] size={chunk_size_mb:.1f}MB priority={chunk.priority:.1f}"
                    )

        except Exception as e:
            log.debug(
                f"Prefetch failed: path={chunk.path} range=[{chunk.start}-{chunk.end}] error={e}"
            )
        finally:
            # Remove from active tracking
            async with self._lock:
                self._active_chunks.pop(chunk_key, None)


class URLCacheItem(TypedDict):
    url: str
    timestamp: float


class FileHandle(TypedDict):
    path: str
    file_size: int | None
    entry_type: str | None
    buffers: list
    sequential_reads: int
    last_read_end: int
    subtitle_content: bytes | None


class FileHandlePrefetchState(TypedDict):
    last_prefetch_pos: int
    prefetch_window_end: int


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

    def __init__(self, mountpoint: str, downloader: Downloader) -> None:
        """
        Initialize the Riven Virtual File System.

        Args:
            mountpoint: Directory where the VFS will be mounted
            downloader: Downloader service instance

        Raises:
            OSError: If mountpoint cannot be prepared or FUSE initialization fails
        """
        super().__init__()
        # Initialize VFS cache from settings
        try:
            fs = settings_manager.settings.filesystem
        except Exception:
            fs = FilesystemModel()
        cache_dir = fs.cache_dir
        size_mb = fs.cache_max_size_mb
        try:
            cache_dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
        try:
            usage = shutil.disk_usage(
                str(cache_dir if cache_dir.exists() else cache_dir.parent)
            )
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

        self.downloader = downloader
        self.db = VFSDatabase(downloader=downloader)

        # VFS Tree: In-memory tree structure for O(1) path lookups
        # This replaces _path_to_inode, _path_aliases, and _dir_tree
        self._root = VFSNode(name="", is_directory=True, inode=pyfuse3.ROOT_INODE)
        self._inode_to_node: Dict[int, VFSNode] = {pyfuse3.ROOT_INODE: self._root}
        self._next_inode = pyfuse3.InodeT(pyfuse3.ROOT_INODE + 1)

        # Tree lock to prevent race conditions between FUSE operations and tree rebuilds
        # pyfuse3 runs FUSE operations in threads, so we use threading.RLock()
        self._tree_lock = threading.RLock()

        # URL cache for provider links with automatic expiration
        self._url_cache: Dict[str, URLCacheItem] = {}
        self.url_cache_ttl = 15 * 60  # 15 minutes

        try:
            self.async_client = di[httpx.AsyncClient]
        except KeyError:
            raise RuntimeError("httpx.AsyncClient not found in dependency injector")

        # Chunking
        self.chunk_size = fs.chunk_size_mb * 1024 * 1024

        # Prefetch window size (number of chunks to prefetch ahead of current read position)
        # This determines how many chunks ahead we prefetch for smooth streaming
        # Will be wired to FilesystemModel configuration separately
        self.fetch_ahead_chunks = fs.fetch_ahead_chunks

        # Validate cache size vs chunk size + prefetch
        # Cache needs to hold: current chunk + prefetch chunks + buffer for concurrent reads
        # Minimum: chunk_size * (fetch_ahead_chunks + 4 for concurrent reads)
        min_cache_mb = fs.chunk_size_mb * (self.fetch_ahead_chunks + 4)
        if size_mb < min_cache_mb:
            logger.bind(component="RivenVFS").warning(
                f"Cache size ({size_mb}MB) is too small for chunk_size ({fs.chunk_size_mb}MB) "
                f"and fetch_ahead_chunks ({self.fetch_ahead_chunks}). "
                f"Minimum recommended: {min_cache_mb}MB. "
                f"Cache thrashing may occur with concurrent reads, causing poor performance."
            )

        # Open file handles: fh -> handle info
        self._file_handles: Dict[int, FileHandle] = {}
        self._next_fh = 1

        # Opener statistics
        self._opener_stats: Dict[str, Dict] = {}

        # Per-file-handle prefetch tracking (for proper multi-user coordination)
        self._fh_prefetch_state: Dict[int, FileHandlePrefetchState] = {}
        # Per-path coordination for avoiding duplicate chunk fetches across file handles
        self._path_chunks_in_progress: Dict[str, Set[int]] = (
            {}
        )  # path -> set of chunk_starts being fetched
        self._prefetch_locks: Dict[str, trio.Lock] = (
            {}
        )  # path -> lock for coordinating prefetch

        # Per-chunk locks to prevent duplicate fetches of the same chunk
        self._chunk_locks: Dict[str, trio.Lock] = {}  # "path:chunk_start" -> lock
        self._chunk_locks_lock = trio.Lock()  # Lock for managing chunk locks dict

        # Global prefetch scheduler for fair multi-user resource allocation
        self._prefetch_scheduler = PrefetchScheduler(
            self
        )  # Pass VFS instance for chunk locking
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
            "fsname=rivenvfs",
            "allow_other",
        }

        pyfuse3.init(self, self._mountpoint, fuse_options)
        self._mounted = True

        def _fuse_runner():
            async def _async_main():
                # capture Trio token so we can call into the loop from other threads
                self._trio_token = trio.lowlevel.current_trio_token()
                await pyfuse3.main()

            try:
                # pyfuse3.main is a coroutine that needs to run in its own trio event loop
                trio.run(_async_main)
            except Exception as e:
                log.error(f"FUSE main loop error: {e}")
                import traceback

                log.error(f"Traceback:\n{traceback.format_exc()}")

        self._thread = threading.Thread(target=_fuse_runner, daemon=True)
        self._thread.start()

        log.log("VFS", f"RivenVFS mounted at {self._mountpoint}")

        # Synchronize library profiles with VFS structure
        self.sync_library_profiles()

    # ========== VFS Tree Helper Methods ==========

    def _get_node_by_path(self, path: str) -> Optional[VFSNode]:
        """
        Get a VFSNode by walking the tree from root.

        This is O(depth) instead of O(n) like the old path iteration approach.

        Args:
            path: NORMALIZED VFS path (e.g., "/movies/Frozen.mkv")
                  Caller must normalize before calling this method.

        Returns:
            VFSNode if found, None otherwise
        """
        if path == "/":
            return self._root

        # Split path and walk tree
        parts = [p for p in path.split("/") if p]
        current = self._root

        for part in parts:
            current = current.get_child(part)
            if current is None:
                return None

        return current

    def _get_or_create_node(
        self, path: str, is_directory: bool, base_path: Optional[str] = None
    ) -> VFSNode:
        """
        Get or create a node at the given path, creating parent directories as needed.

        Args:
            path: NORMALIZED VFS path (caller must normalize)
            is_directory: Whether this is a directory
            base_path: Base path in database (for files)

        Returns:
            The VFSNode at the path
        """
        if path == "/":
            return self._root

        # Split path and walk/create tree
        parts = [p for p in path.split("/") if p]
        current = self._root

        for i, part in enumerate(parts):
            child = current.get_child(part)

            if child is None:
                # Create the node
                is_last = i == len(parts) - 1

                if is_last:
                    # This is the target node
                    child = VFSNode(
                        name=part,
                        is_directory=is_directory,
                        base_path=base_path,
                        inode=self._assign_inode(),
                    )
                else:
                    # This is a parent directory
                    child = VFSNode(
                        name=part, is_directory=True, inode=self._assign_inode()
                    )

                current.add_child(child)

                if child.inode is not None:
                    self._inode_to_node[child.inode] = child

            current = child

        return current

    def _remove_node(self, path: str) -> bool:
        """
        Remove a node from the tree.

        Args:
            path: NORMALIZED VFS path to remove (caller must normalize)

        Returns:
            True if removed, False if not found
        """
        if path == "/":
            return False  # Can't remove root

        node = self._get_node_by_path(path)
        if node is None:
            return False

        # Remove from parent
        if node.parent:
            node.parent.remove_child(node.name)

        # Remove from inode map
        if node.inode:
            self._inode_to_node.pop(node.inode, None)

        # Recursively remove all children from inode map
        self._remove_node_recursive(node)

        return True

    def _remove_node_recursive(self, node: VFSNode) -> None:
        """Recursively remove all children from inode map."""
        for child in list(node.children.values()):
            if child.inode:
                self._inode_to_node.pop(child.inode, None)
            self._remove_node_recursive(child)

    def _assign_inode(self) -> pyfuse3.InodeT:
        """Assign a new inode number."""
        inode = self._next_inode
        self._next_inode = pyfuse3.InodeT(inode + 1)
        return inode

    def _get_parent_inodes(self, node: VFSNode) -> List[pyfuse3.InodeT]:
        """
        Get all parent inodes from node up to root.

        This is useful for collecting parent directories that need cache invalidation.

        Args:
            node: Starting node

        Returns:
            List of parent inodes (excluding root)
        """
        inodes = []
        current = node.parent
        while current and current != self._root:
            if current.inode:
                inodes.append(current.inode)
            current = current.parent
        return inodes

    # ========== End VFS Tree Helper Methods ==========

    async def _get_chunk_lock(self, path: str, chunk_start: int) -> trio.Lock:
        """
        Get or create a lock for a specific chunk to prevent duplicate fetches.

        Args:
            path: File path
            chunk_start: Starting offset of the chunk

        Returns:
            Lock for this specific chunk
        """
        chunk_key = f"{path}:{chunk_start}"
        async with self._chunk_locks_lock:
            if chunk_key not in self._chunk_locks:
                self._chunk_locks[chunk_key] = trio.Lock()
            return self._chunk_locks[chunk_key]

    def sync_library_profiles(self) -> None:
        """
        Synchronize VFS with library profiles from settings.

        This method:
        1. Re-matches all MediaEntry items against current library profiles
        2. Builds the set of current VFS paths based on matched profiles
        3. Removes stale paths (paths that no longer exist)
        4. Adds new paths (paths that didn't exist before)

        Note: Uses incremental updates to preserve kernel inode cache consistency.
        Directories are created automatically by the VFS based on file paths.

        Called automatically:
        - During RivenVFS initialization
        - When settings change (via FilesystemService)
        """
        from program.media.media_entry import MediaEntry
        from program.services.library_profile_matcher import LibraryProfileMatcher

        log.log("VFS", "Synchronizing library profiles with VFS")

        matcher = LibraryProfileMatcher()

        # Step 1: Re-match all entries against current library profiles and build metadata map
        from program.db.db import db as db_module

        with db_module.Session() as session:
            entries = (
                session.query(MediaEntry).filter(MediaEntry.is_directory == False).all()
            )

            current_paths = set()
            path_to_base = {}  # Build inside session to avoid detached instance errors
            path_to_metadata = {}  # Cache metadata for each path
            rematched_count = 0

            for entry in entries:
                # Get the MediaItem for this entry to re-match profiles
                item = entry.media_item
                if not item:
                    log.warning(
                        f"MediaEntry {entry.id} has no associated MediaItem, skipping"
                    )
                    continue

                # Re-match library profiles based on current settings
                new_profiles = matcher.get_matching_profiles(item)
                old_profiles = entry.library_profiles or []

                # Update if profiles changed
                if set(new_profiles) != set(old_profiles):
                    entry.library_profiles = new_profiles
                    rematched_count += 1

                # Get all current VFS paths for this entry
                vfs_paths = entry.get_library_paths()
                current_paths.update(vfs_paths)

                # Build path to base path mapping and metadata cache (inside session)
                if vfs_paths:
                    base_path = vfs_paths[0]  # First path is always base path

                    # Extract metadata from entry (use correct attribute names!)
                    metadata = {
                        "file_size": entry.file_size,
                        "created_at": (
                            entry.created_at.isoformat() if entry.created_at else None
                        ),
                        "updated_at": (
                            entry.updated_at.isoformat() if entry.updated_at else None
                        ),
                        "entry_type": entry.entry_type,
                    }

                    for vfs_path in vfs_paths:
                        path_to_base[vfs_path] = base_path
                        path_to_metadata[vfs_path] = metadata

            session.commit()
            log.info(
                f"Re-matched {rematched_count} entries with updated library profiles"
            )

        # Step 2: Rebuild VFS tree from current paths
        # Build new tree outside the lock to minimize critical section
        new_root = VFSNode(name="", is_directory=True, inode=pyfuse3.ROOT_INODE)
        new_inode_to_node: Dict[int, VFSNode] = {pyfuse3.ROOT_INODE: new_root}
        new_next_inode = self._next_inode  # Preserve inode counter

        added_count = 0
        directories_to_invalidate = set()

        # Build the new tree (temporarily use instance variables for _get_or_create_node to work)
        # This is safe because sync_library_profiles is only called from one thread at a time
        saved_root = self._root
        saved_inode_to_node = self._inode_to_node
        saved_next_inode = self._next_inode

        self._root = new_root
        self._inode_to_node = new_inode_to_node
        self._next_inode = new_next_inode

        for vfs_path in current_paths:
            # Get base path and metadata for this VFS path
            base_path = path_to_base.get(vfs_path, vfs_path)
            metadata = path_to_metadata.get(vfs_path, {})

            # Create node in tree (creates parent directories automatically)
            node = self._get_or_create_node(
                path=vfs_path,
                is_directory=False,  # We know these are files
                base_path=base_path,
            )

            # Populate cached metadata in the node (eliminates DB queries in getattr!)
            node.file_size = metadata.get("file_size")
            node.created_at = metadata.get("created_at")
            node.updated_at = metadata.get("updated_at")
            node.entry_type = metadata.get("entry_type")

            added_count += 1

            # Collect parent directories for invalidation
            parent_node = node.parent
            while parent_node and parent_node != new_root:
                directories_to_invalidate.add(parent_node.get_full_path())
                parent_node = parent_node.parent

        # Capture the new tree state
        new_next_inode = self._next_inode

        # Atomic swap: Replace old tree with new tree under lock
        with self._tree_lock:
            self._root = new_root
            self._inode_to_node = new_inode_to_node
            self._next_inode = new_next_inode

        log.log(
            "VFS",
            f"Sync complete: rebuilt tree with {added_count} files, "
            f"re-matched {rematched_count} entries",
        )

        # Step 3: Invalidate directory caches for changed directories
        if added_count > 0:
            try:
                # Invalidate root directory
                pyfuse3.invalidate_inode(pyfuse3.ROOT_INODE, attr_only=False)

                # Invalidate all affected parent directories
                for dir_path in directories_to_invalidate:
                    node = self._get_node_by_path(dir_path)
                    if node and node.inode:
                        try:
                            pyfuse3.invalidate_inode(node.inode, attr_only=False)
                        except OSError:
                            pass  # Ignore if kernel hasn't cached this inode yet

                log.info(
                    f"Invalidated {len(directories_to_invalidate)} directory caches after library sync"
                )
            except Exception as e:
                log.debug(f"Could not invalidate directory caches: {e}")

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
                with open("/proc/mounts", "r") as f:
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
                    ["fusermount3", "-u", "-z", mountpoint],
                    ["fusermount", "-u", "-z", mountpoint],
                    ["umount", "-l", mountpoint],
                ):
                    try:
                        subprocess.run(
                            cmd, capture_output=True, timeout=10, check=False
                        )
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
                    trio.from_thread.run(
                        self._terminate_async, trio_token=self._trio_token
                    )
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
            subprocess.run(
                ["fusermount", "-u", mountpoint],
                capture_output=True,
                timeout=10,
                check=False,
            )
        except Exception:
            pass

    async def _terminate_async(self) -> None:
        """Async helper to call pyfuse3.terminate() within the Trio loop."""
        try:
            pyfuse3.terminate()
        except Exception as e:
            log.warning(f"pyfuse3.terminate() failed: {e}")

    # Public API methods
    def add_file(
        self,
        path: str,
        url: str,
        size: Optional[int] = None,
        provider: Optional[str] = None,
        provider_download_id: Optional[str] = None,
    ) -> bool:
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
        self.db.add_file(
            path,
            url,
            int(size or 0),
            provider=provider,
            provider_download_id=provider_download_id,
        )

        # Create node in tree (creates parent directories automatically)
        with self._tree_lock:
            node = self._get_or_create_node(
                path=path,
                is_directory=False,
                base_path=path,  # For add_file, path is always the base path
            )

            # Populate metadata in node (so getattr doesn't need DB query)
            from datetime import datetime, timezone

            now = datetime.now(timezone.utc)
            node.file_size = int(size or 0)
            node.created_at = now.isoformat()
            node.updated_at = now.isoformat()
            node.entry_type = "media"  # add_file creates media entries

            # Get parent inodes for invalidation (must be done inside lock)
            parent_inodes = self._get_parent_inodes(node)

        # Invalidate FUSE cache to ensure directory listings are updated
        # This is crucial for media players that cache directory structure
        self._invalidate_directory_cache(path, parent_inodes)

        log.info(f"Added file to VFS: {path}")
        return True

    def register_existing_file(self, path: str) -> bool:
        """
        Register an existing file with the FUSE layer without creating database entries.

        This is useful when FilesystemEntry records already exist in the database
        but need to be made accessible via FUSE.

        For library profile paths (e.g., /kids/movies/...), this method resolves them
        to the base path (e.g., /movies/...) for database lookup, then creates a node
        in the tree with the base_path reference.

        Args:
            path: Virtual path of the existing file (can be base path or profile path)

        Returns:
            True if file was registered successfully
        """
        path = self._normalize_path(path)

        with self._tree_lock:
            # Get base path from node if it exists, otherwise resolve it
            node = self._get_node_by_path(path)
            if node:
                base_path = node.base_path or path
            else:
                base_path = self._resolve_path(path)

        # Check if base path exists in database and get metadata
        entry_info = self.db.get_entry(base_path)
        if not entry_info:
            log.warning(
                f"Cannot register non-existent file: {path} (resolved: {base_path})"
            )
            return False

        with self._tree_lock:
            # Create node in tree (creates parent directories automatically)
            # Note: This is called during sync, so the node might already exist
            if not node:
                node = self._get_or_create_node(
                    path=path, is_directory=False, base_path=base_path
                )

            # Populate metadata in node from database entry
            node.file_size = entry_info.get("size", 0)
            node.created_at = entry_info.get("created")
            node.updated_at = entry_info.get("modified")
            node.entry_type = entry_info.get("entry_type", "media")

            # Get parent inodes for invalidation (must be done inside lock)
            parent_inodes = self._get_parent_inodes(node)

        # Invalidate FUSE cache to ensure directory listings are updated
        self._invalidate_directory_cache(path, parent_inodes)

        return True

    def _resolve_path(self, path: str) -> str:
        """
        Resolve a path to its base path using the VFS tree.

        If the path is a library profile path, returns the base path stored in the node.
        If the node doesn't exist yet, attempts to strip library profile prefixes.

        Args:
            path: NORMALIZED path to resolve (caller must normalize)

        Returns:
            Resolved path (base path if it's a profile path, otherwise original path)
        """
        # Check if node exists and has base_path
        node = self._get_node_by_path(path)
        if node and node.base_path:
            return node.base_path

        # If not in tree, try to strip library profile prefix
        # This handles the case where we're registering a library profile path
        # before the node exists in the tree
        base_path = self._strip_library_profile_prefix(path)
        return base_path

    def _strip_library_profile_prefix(self, path: str) -> str:
        """
        Strip library profile prefix from a path if present.

        Args:
            path: Path that may have a library profile prefix (e.g., /recent/movies/...)

        Returns:
            Base path without library profile prefix (e.g., /movies/...)
        """
        from program.settings.manager import settings_manager

        profiles = settings_manager.settings.filesystem.library_profiles or {}

        for profile in profiles.values():
            if not profile.enabled:
                continue

            prefix = profile.library_path
            if path.startswith(prefix + "/"):
                # Strip the prefix and return the base path
                # e.g., "/recent/movies/Title..." -> "/movies/Title..."
                return path[len(prefix) :]

        # No profile prefix found, return as-is
        return path

    def rename_file(self, old_path: str, new_path: str) -> bool:
        """
        Rename a file from old_path to new_path and update VFS caches and inode mappings.

        Performs a database rename and ensures FUSE entry caches, path↔inode mappings, and parent directory cache entries are updated or invalidated to reflect the move.

        Parameters:
            old_path (str): Current filesystem path of the file.
            new_path (str): Target filesystem path for the file.

        Returns:
            bool: `True` if the file was renamed successfully, `False` otherwise.
        """
        old_path = self._normalize_path(old_path)
        new_path = self._normalize_path(new_path)

        # Rename in database
        if not self.db.rename(old_path, new_path):
            log.warning(f"Failed to rename file in database: {old_path} -> {new_path}")
            return False

        # Update VFS tree
        with self._tree_lock:
            # Get old node to preserve metadata
            old_node = self._get_node_by_path(old_path)
            old_metadata = None
            if old_node:
                # Save metadata before removing
                old_metadata = {
                    "file_size": old_node.file_size,
                    "created_at": old_node.created_at,
                    "updated_at": old_node.updated_at,
                    "entry_type": old_node.entry_type,
                }
                self._remove_node(old_path)

            # Create new node
            new_node = self._get_or_create_node(
                path=new_path,
                is_directory=False,
                base_path=new_path,  # For rename, new_path is the base path
            )

            # Restore metadata to new node
            if old_metadata:
                new_node.file_size = old_metadata["file_size"]
                new_node.created_at = old_metadata["created_at"]
                new_node.updated_at = old_metadata["updated_at"]
                new_node.entry_type = old_metadata["entry_type"]

            # Get parent inodes for invalidation (must be done inside lock)
            parent_inodes = self._get_parent_inodes(new_node)

        # Invalidate FUSE cache for both old and new locations
        self._invalidate_rename_cache(old_path, new_path, None)
        self._invalidate_directory_cache(new_path, parent_inodes)

        log.info(f"Renamed file in VFS: {old_path} -> {new_path}")
        return True

    def file_exists(self, path: str) -> bool:
        """
        Check whether a virtual file exists at the given path.

        Returns:
            true if the file exists, false otherwise.
        """
        return self.db.exists(self._normalize_path(path))

    def get_file_info(self, path: str) -> Optional[VFSEntry]:
        """
        Get information about a virtual file.

        Resolves library profile paths to base paths for database lookup using alias map.
        """
        path = self._normalize_path(path)
        resolved_path = self._resolve_path(path)
        return self.db.get_entry(resolved_path)

    def list_directory(self, path: str) -> list[Dict]:
        """List contents of a virtual directory using VFS tree."""
        return self._list_directory_cached(self._normalize_path(path))

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

    def _exists_cached(self, path: str) -> bool:
        """Check if path exists in VFS tree (no database query)."""
        return self._get_node_by_path(path) is not None

    def _list_directory_cached(self, path: str) -> list[Dict]:
        """
        List directory contents using VFS tree for O(1) lookups.

        The VFS tree is built during sync_library_profiles() and provides
        instant directory listings without any database queries.

        Args:
            path: NORMALIZED VFS path (caller must normalize)
        """
        with self._tree_lock:
            # Get node from tree
            node = self._get_node_by_path(path)
            if node is None or not node.is_directory:
                return []

            # Build result list from node's children - no database queries!
            children = []
            for name, child in node.children.items():
                children.append({"name": name, "is_directory": child.is_directory})

            return children

    def _get_path_from_inode(self, inode: int) -> str:
        """Get path from inode number using the VFS tree."""
        with self._tree_lock:
            node = self._inode_to_node.get(inode)
            if node is None:
                raise pyfuse3.FUSEError(errno.ENOENT)
            return node.get_full_path()

    @staticmethod
    def _current_time_ns() -> int:
        """Get current time in nanoseconds."""
        import time

        return int(time.time() * 1e9)

    def _invalidate_entry(
        self,
        parent_path: str,
        entry_name: str,
        deleted_inode: Optional[pyfuse3.InodeT] = None,
        operation: str = "modify",
    ) -> None:
        """
        Helper to invalidate a directory entry in the kernel cache.

        Args:
            parent_path: Path to the parent directory
            entry_name: Name of the entry to invalidate
            deleted_inode: If provided, marks the entry as deleted with this inode
            operation: Description of operation for logging (add/remove/rename)
        """
        try:
            parent_node = self._get_node_by_path(parent_path)
            if parent_node and parent_node.inode:
                pyfuse3.invalidate_entry_async(
                    parent_node.inode,
                    pyfuse3.FileNameT(entry_name.encode("utf-8")),
                    deleted=pyfuse3.InodeT(deleted_inode or 0),
                    ignore_enoent=True,
                )
        except OSError as e:
            if getattr(e, "errno", None) != errno.ENOENT:
                log.warning(
                    f"Failed to invalidate entry '{entry_name}' in {parent_path}: {e}"
                )

    def _invalidate_inode_list(
        self,
        inodes: list[pyfuse3.InodeT],
        attr_only: bool = True,
        operation: str = "modify",
    ) -> None:
        """
        Helper to invalidate a list of inodes.

        Args:
            inodes: List of inode numbers to invalidate
            attr_only: If True, only invalidate attributes; if False, invalidate content too
            operation: Description of operation for logging
        """
        for ino in inodes:
            try:
                pyfuse3.invalidate_inode(ino, attr_only=attr_only)
            except OSError as e:
                if getattr(e, "errno", None) == errno.ENOENT:
                    # Expected - inode not cached by kernel yet
                    pass
                else:
                    log.warning(f"Failed to invalidate inode {ino}: {e}")

    def _invalidate_directory_cache(
        self, file_path: str, parent_inodes: list[pyfuse3.InodeT]
    ) -> None:
        """
        Invalidate FUSE cache when adding files.

        Args:
            file_path: NORMALIZED file path (caller must normalize)
            parent_inodes: List of parent inodes to invalidate
        """
        # Invalidate the immediate parent directory entry
        immediate_parent = self._get_parent_path(file_path)
        self._invalidate_entry(
            immediate_parent, os.path.basename(file_path), operation="add"
        )

        # Invalidate any newly created parent directories
        self._invalidate_inode_list(
            parent_inodes, attr_only=True, operation="add parent"
        )

    def _invalidate_removed_entry_cache(
        self, file_path: str, inode: Optional[pyfuse3.InodeT]
    ) -> None:
        """
        Invalidate FUSE cache when removing files.

        Args:
            file_path: NORMALIZED file path (caller must normalize)
            inode: Inode of removed file
        """
        parent_path = self._get_parent_path(file_path)
        self._invalidate_entry(
            parent_path,
            os.path.basename(file_path),
            deleted_inode=inode,
            operation="remove",
        )

    def _invalidate_potentially_removed_dirs(self, file_path: str) -> None:
        """
        Invalidate parent directory entries that may have been removed due to pruning.

        Args:
            file_path: NORMALIZED file path (caller must normalize)
        """
        try:
            parent = self._get_parent_path(file_path)
            grandparent = self._get_parent_path(parent)

            # Invalidate the entry for 'parent' under its parent directory (grandparent)
            name = os.path.basename(parent.rstrip("/"))
            if name:
                self._invalidate_entry(grandparent, name, operation="prune")

            # One more level up (e.g., title dir)
            ggparent = self._get_parent_path(grandparent)
            gname = os.path.basename(grandparent.rstrip("/"))
            if gname:
                self._invalidate_entry(ggparent, gname, operation="prune")
        except Exception as e:
            if getattr(e, "errno", None) != errno.ENOENT:
                log.warning(
                    f"Failed to invalidate parent dir entries for {file_path}: {e}"
                )

    def _invalidate_rename_cache(
        self, old_path: str, new_path: str, inode: Optional[pyfuse3.InodeT]
    ) -> None:
        """
        Invalidate FUSE cache when renaming files.

        Args:
            old_path: NORMALIZED old file path (caller must normalize)
            new_path: NORMALIZED new file path (caller must normalize)
            inode: Inode of renamed file
        """
        # Invalidate old parent directory (mark as deleted)
        old_parent = self._get_parent_path(old_path)
        self._invalidate_entry(
            old_parent,
            os.path.basename(old_path),
            deleted_inode=inode,
            operation="rename (old)",
        )

        # Invalidate new parent directory (mark as added)
        new_parent = self._get_parent_path(new_path)
        self._invalidate_entry(
            new_parent, os.path.basename(new_path), operation="rename (new)"
        )

    # FUSE Operations
    async def getattr(self, inode: pyfuse3.InodeT, ctx=None) -> pyfuse3.EntryAttributes:
        """Get file/directory attributes."""
        try:
            path = self._get_path_from_inode(inode)

            attrs = pyfuse3.EntryAttributes()
            attrs.st_ino = inode
            attrs.generation = 0
            attrs.entry_timeout = 300
            attrs.attr_timeout = 300
            attrs.st_uid = os.getuid() if hasattr(os, "getuid") else 0
            attrs.st_gid = os.getgid() if hasattr(os, "getgid") else 0
            attrs.st_blksize = 131072  # Hint larger block size to kernel (128 KiB)
            attrs.st_blocks = 1

            import stat

            # Special case for root directory
            if path == "/":
                attrs.st_mode = pyfuse3.ModeT(stat.S_IFDIR | 0o755)
                attrs.st_nlink = 2
                attrs.st_size = 0
                # Use current time for root directory
                now_ns = self._current_time_ns()
                attrs.st_atime_ns = now_ns
                attrs.st_mtime_ns = now_ns
                attrs.st_ctime_ns = now_ns
                return attrs

            # For other paths, get node from tree
            node = self._get_node_by_path(path)
            if node is None:
                raise pyfuse3.FUSEError(errno.ENOENT)

            # Check if it's a directory
            if node.is_directory:
                # This is a virtual directory (e.g., /kids, /anime, /movies)
                attrs.st_mode = pyfuse3.ModeT(stat.S_IFDIR | 0o755)
                attrs.st_nlink = 2
                attrs.st_size = 0
                now_ns = self._current_time_ns()
                attrs.st_atime_ns = now_ns
                attrs.st_mtime_ns = now_ns
                attrs.st_ctime_ns = now_ns
                return attrs

            # It's a file - use cached metadata from node (NO DATABASE QUERY!)
            # Metadata was populated during sync_library_profiles()

            # Parse timestamps from cached metadata
            if node.created_at:
                from datetime import datetime

                try:
                    created_dt = datetime.fromisoformat(node.created_at)
                    created_ns = int(created_dt.timestamp() * 1_000_000_000)
                except Exception:
                    created_ns = self._current_time_ns()
            else:
                created_ns = self._current_time_ns()

            if node.updated_at:
                from datetime import datetime

                try:
                    updated_dt = datetime.fromisoformat(node.updated_at)
                    updated_ns = int(updated_dt.timestamp() * 1_000_000_000)
                except Exception:
                    updated_ns = created_ns
            else:
                updated_ns = created_ns

            # Set timestamps: ctime = creation, mtime = modification, atime = access (use mtime)
            attrs.st_ctime_ns = created_ns
            attrs.st_mtime_ns = updated_ns
            attrs.st_atime_ns = (
                updated_ns  # Use mtime for atime to avoid constant updates
            )

            # We already know it's a file from node.is_directory check above
            attrs.st_mode = pyfuse3.ModeT(stat.S_IFREG | 0o644)
            attrs.st_nlink = 1
            size = int(node.file_size or 0)
            if size == 0:
                size = 1337 * 1024 * 1024  # Default size when unknown
            attrs.st_size = size

            return attrs
        except pyfuse3.FUSEError:
            raise
        except Exception as ex:
            log.exception("getattr error for inode=%s: %s", inode, ex)
            raise pyfuse3.FUSEError(errno.EIO)

    async def lookup(
        self, parent_inode: pyfuse3.InodeT, name: bytes, ctx=None
    ) -> pyfuse3.EntryAttributes:
        """Look up a directory entry using VFS tree."""
        try:
            with self._tree_lock:
                # Get parent node from tree
                parent_node = self._inode_to_node.get(parent_inode)
                if parent_node is None:
                    raise pyfuse3.FUSEError(errno.ENOENT)

                name_str = name.decode("utf-8")

                if name_str == ".":
                    child_inode = parent_inode
                elif name_str == "..":
                    # Get parent's parent
                    if parent_node.parent:
                        child_inode = parent_node.parent.inode
                    else:
                        child_inode = pyfuse3.ROOT_INODE
                else:
                    # Look up child in parent's children
                    child_node = parent_node.get_child(name_str)
                    if child_node is None:
                        raise pyfuse3.FUSEError(errno.ENOENT)
                    child_inode = child_node.inode

                if child_inode is None:
                    raise pyfuse3.FUSEError(errno.ENOENT)

            return await self.getattr(child_inode)
        except pyfuse3.FUSEError:
            raise
        except Exception as ex:
            log.exception("lookup error: parent=%s name=%s: %s", parent_inode, name, ex)
            raise pyfuse3.FUSEError(errno.EIO)

    async def opendir(self, inode: pyfuse3.InodeT, ctx):
        """Open a directory for reading."""
        try:
            with self._tree_lock:
                # Get node from tree
                node = self._inode_to_node.get(inode)
                if node is None:
                    raise pyfuse3.FUSEError(errno.ENOENT)

                # Check if it's a directory
                if not node.is_directory:
                    raise pyfuse3.FUSEError(errno.ENOTDIR)

            return inode  # Return the inode as file handle for directories
        except pyfuse3.FUSEError:
            raise
        except Exception as ex:
            log.exception("opendir error for inode=%s: %s", inode, ex)
            raise pyfuse3.FUSEError(errno.EIO)

    async def readdir(
        self, inode: pyfuse3.InodeT, off: int, token: pyfuse3.ReaddirToken
    ):
        """Read directory entries."""
        try:
            path = self._get_path_from_inode(inode)
            entries = self._list_directory_cached(path)

            # Build directory listing
            with self._tree_lock:
                node = self._inode_to_node.get(inode)
                parent_inode = (
                    node.parent.inode if node and node.parent else pyfuse3.ROOT_INODE
                )

                items = [(b".", inode), (b"..", parent_inode)]

                for entry in entries:
                    name_bytes = entry["name"].encode("utf-8")
                    # Get child node from tree
                    child_node = node.get_child(entry["name"]) if node else None
                    if child_node and child_node.inode:
                        items.append((name_bytes, child_node.inode))

            # Send directory entries starting from offset
            for idx in range(off, len(items)):
                name_bytes, child_ino = items[idx]
                attrs = await self.getattr(child_ino)
                if not pyfuse3.readdir_reply(
                    token, pyfuse3.FileNameT(name_bytes), attrs, idx + 1
                ):
                    break
        except pyfuse3.FUSEError:
            raise
        except Exception as ex:
            log.exception("readdir error for inode=%s: %s", inode, ex)
            raise pyfuse3.FUSEError(errno.EIO)

    async def open(self, inode: pyfuse3.InodeT, flags: int, ctx):
        """Open a file for reading."""
        try:
            with self._tree_lock:
                # Get node from tree and verify it's a file
                node = self._inode_to_node.get(inode)
                if node is None or node.is_directory:
                    raise pyfuse3.FUSEError(
                        errno.EISDIR if node and node.is_directory else errno.ENOENT
                    )

                path = node.get_full_path()
                # Cache metadata from node
                file_size = node.file_size
                entry_type = node.entry_type

            log.trace(f"open: path={path} inode={inode} fh_pending flags={flags}")

            # Only allow read access
            if flags & os.O_RDWR or flags & os.O_WRONLY:
                raise pyfuse3.FUSEError(errno.EACCES)

            # Create file handle with cached node metadata (no DB query!)
            fh = self._next_fh
            self._next_fh += 1
            # Store metadata in handle (don't store node reference to avoid holding lock)
            self._file_handles[fh] = {
                "path": path,
                "file_size": file_size,
                "entry_type": entry_type,
                "buffers": [],
                "sequential_reads": 0,
                "last_read_end": 0,
                "subtitle_content": None,
            }

            # Initialize per-file-handle prefetch state
            self._fh_prefetch_state[fh] = {
                "last_prefetch_pos": -1,
                "prefetch_window_end": -1,
            }

            log.trace(f"open: path={path} fh={fh} size={file_size} type={entry_type}")
            return pyfuse3.FileInfo(fh=pyfuse3.FileHandleT(fh))
        except pyfuse3.FUSEError:
            raise

    async def read(self, fh: pyfuse3.FileHandleT, off: int, size: int) -> bytes:
        """Simplified read path: fixed-size chunking and straightforward sequential prefetch."""
        try:
            # Log cache stats asynchronously (don't block on trim/I/O)
            try:
                await trio.to_thread.run_sync(self.cache.maybe_log_stats)
            except Exception:
                pass

            handle_info = self._file_handles.get(fh)
            if not handle_info:
                raise pyfuse3.FUSEError(errno.EBADF)
            path = handle_info.get("path") or ""
            if not path:
                raise pyfuse3.FUSEError(errno.EBADF)

            # Get cached metadata from file handle (populated in open())
            file_size = handle_info.get("file_size")
            entry_type = handle_info.get("entry_type")

            if size == 0:
                return b""

            # Check if this is a subtitle entry - if so, read from database instead of HTTP
            if entry_type == "subtitle":
                # Subtitles are stored in the database, not fetched via HTTP
                # Check if we've already cached the subtitle content in the handle
                subtitle_content = handle_info.get("subtitle_content")
                if subtitle_content is None:
                    # Resolve path alias before querying database for subtitle content
                    resolved_path = self._resolve_path(path)
                    # Fetch subtitle content from database (async to avoid blocking)
                    subtitle_content = await trio.to_thread.run_sync(
                        lambda: self.db.get_subtitle_content(resolved_path)
                    )
                    if subtitle_content is None:
                        log.error(f"Subtitle content not found for {path}")
                        raise pyfuse3.FUSEError(errno.ENOENT)
                    # Cache in handle for subsequent reads
                    handle_info["subtitle_content"] = subtitle_content

                # Slice subtitle content in thread (could be large)
                def slice_subtitle():
                    end_offset = min(off + size, len(subtitle_content))
                    return subtitle_content[off:end_offset]

                returned_data = await trio.to_thread.run_sync(slice_subtitle)

                # Update opener stats
                opener = handle_info.get("opener_name")
                if opener and returned_data:
                    self._opener_stats[opener]["bytes_read"] += len(returned_data)

                return returned_data

            # For media entries, continue with normal HTTP streaming logic

            # Resolve path alias to base path for consistent cache keys
            # This ensures cache is shared between base path and all alias paths
            resolved_path = self._resolve_path(path)

            now = time.time()
            cached_url_info = self._url_cache.get(resolved_path)
            if (
                not cached_url_info
                or (now - float(cached_url_info.get("timestamp", 0)))
                > self.url_cache_ttl
            ):
                # Query database for download URL using resolved path (async to avoid blocking)
                url = await trio.to_thread.run_sync(
                    lambda: self.db.get_download_url(
                        resolved_path, for_http=True, force_resolve=False
                    )
                )

                if not url:
                    raise pyfuse3.FUSEError(errno.ENOENT)
                self._url_cache[resolved_path] = {"url": url, "timestamp": now}
            else:
                url = str(cached_url_info.get("url"))

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

            # Try cache first for the exact request (cache handles chunk lookup and slicing)
            # Use resolved_path for cache to share cache between base and alias paths
            cached_bytes = await trio.to_thread.run_sync(
                lambda: self.cache.get(resolved_path, request_start, request_end)
            )

            if cached_bytes is not None:
                # Cache hit - data already sliced to exact request
                returned_data = cached_bytes
                # No log for cache hits - reduces noise
            else:
                # Cache miss - fetch all chunks needed concurrently
                # Build list of chunks to fetch
                chunks_to_fetch = []
                current_chunk_start = first_chunk_start
                while current_chunk_start <= last_chunk_start:
                    chunk_end = current_chunk_start + self.chunk_size - 1
                    if file_size is not None:
                        chunk_end = min(chunk_end, file_size - 1)
                    chunks_to_fetch.append((current_chunk_start, chunk_end))
                    current_chunk_start += self.chunk_size

                # Fetch all chunks concurrently using Trio nursery
                chunk_results = {}  # chunk_start -> data

                async def fetch_one_chunk(chunk_start: int, chunk_end: int):
                    """Fetch a single chunk with per-chunk locking."""
                    # Get lock for this specific chunk to prevent duplicate fetches
                    chunk_lock = await self._get_chunk_lock(resolved_path, chunk_start)

                    async with chunk_lock:
                        # Check cache again inside lock (another request might have fetched it)
                        chunk_data = await trio.to_thread.run_sync(
                            lambda: self.cache.get(
                                resolved_path, chunk_start, chunk_end
                            )
                        )

                        if chunk_data is None:
                            # Fetch this chunk
                            chunk_data = await self._fetch_data_block(
                                resolved_path, url, chunk_start, chunk_end
                            )
                            if chunk_data:
                                chunk_size_mb = len(chunk_data) / (1024 * 1024)
                                log.debug(
                                    f"Fetched chunk: path={path} range=[{chunk_start}-{chunk_end}] chunk_size={chunk_size_mb:.1f}MB"
                                )
                                # Cache immediately (async to avoid blocking event loop)
                                await trio.to_thread.run_sync(
                                    lambda: self.cache.put(
                                        resolved_path, chunk_start, chunk_data
                                    )
                                )

                        if chunk_data:
                            chunk_results[chunk_start] = chunk_data

                # Launch all chunk fetches concurrently
                async with trio.open_nursery() as nursery:
                    for chunk_start, chunk_end in chunks_to_fetch:
                        nursery.start_soon(fetch_one_chunk, chunk_start, chunk_end)

                # Reassemble chunks in order (in thread to avoid blocking event loop)
                def reassemble_chunks():
                    all_data = b""
                    for chunk_start, _ in chunks_to_fetch:
                        if chunk_start in chunk_results:
                            all_data += chunk_results[chunk_start]

                    if not all_data:
                        return b""
                    else:
                        # Return only the requested subrange from the fetched data
                        start_idx = request_start - first_chunk_start
                        need_len = request_end - request_start + 1
                        return all_data[start_idx : start_idx + need_len]

                returned_data = await trio.to_thread.run_sync(reassemble_chunks)

            # Data integrity check: ensure we return exactly the requested size
            # The expected_size is already correctly calculated as request_end - request_start + 1
            # which accounts for file size clamping done earlier
            expected_size = request_end - request_start + 1
            if returned_data and len(returned_data) != expected_size:
                # This should never happen, but if it does, truncate/pad to exact size
                if len(returned_data) > expected_size:
                    returned_data = returned_data[:expected_size]
                    log.warning(
                        f"Read returned too much data: got {len(returned_data)} bytes, expected {expected_size}"
                    )
                else:
                    log.error(
                        f"Read returned too little data: got {len(returned_data)} bytes, expected {expected_size}"
                    )
                    # For media playback, returning partial data is worse than returning empty
                    returned_data = b""

            # Track sequential reads for prefetching
            if off == handle_info.get("last_read_end", 0):
                handle_info["sequential_reads"] = (
                    handle_info.get("sequential_reads", 0) + 1
                )
            else:
                # Non-sequential read, reset counter
                handle_info["sequential_reads"] = 0
            handle_info["last_read_end"] = off + len(returned_data)

            # Prefetch ahead after 3 sequential reads (works for both playback and scanning)
            # Only trigger prefetch if we're approaching the end of the previously prefetched window
            if handle_info["sequential_reads"] >= 3:
                # Get prefetch state for this file handle
                fh_prefetch_state = self._fh_prefetch_state.get(fh, {})
                last_prefetch_end = fh_prefetch_state.get("prefetch_window_end", -1)

                # Only trigger prefetch if we're within 2 chunks of the prefetch window end
                # or if we haven't prefetched yet
                trigger_threshold = last_prefetch_end - (2 * self.chunk_size)

                if last_prefetch_end == -1 or off >= trigger_threshold:
                    if file_size is None or next_aligned_start < file_size:
                        pf_end = (
                            next_aligned_end
                            if file_size is None
                            else min(next_aligned_end, file_size - 1)
                        )
                        # Use resolved_path for prefetch to share cache between base and alias paths
                        trio.lowlevel.spawn_system_task(
                            self._prefetch_next_chunks,
                            fh,
                            resolved_path,
                            url,
                            next_aligned_start,
                            pf_end,
                        )

            # Update opener stats and return data
            opener = handle_info.get("opener_name")
            if opener and returned_data:
                self._opener_stats[opener]["bytes_read"] += len(returned_data)
            return returned_data
        except pyfuse3.FUSEError:
            raise
        except Exception as ex:
            log.exception("read(simple) error fh=%s: %s", fh, ex)
            raise pyfuse3.FUSEError(errno.EIO)

    async def _prefetch_next_chunks(
        self, fh: int, path: str, url: str, start: int, end: int
    ) -> None:
        """Prefetch multiple chunks ahead of current read position.

        Architecture:
        - chunk_size (eg. 32MB) = individual CDN request size
        - fetch_ahead_chunks (eg. 4) = number of chunks to prefetch ahead
        - Schedules 4 x 32MB requests = 128MB total prefetch window
        - Coordinates across multiple users reading the same file with fair scheduling
        """
        if fh not in self._file_handles:
            return

        # Get file size to avoid prefetching beyond EOF
        file_size = self._file_handles[fh].get("file_size")

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
                        "last_prefetch_pos": -1,
                        "prefetch_window_end": -1,
                    }

                # Initialize per-path chunk tracking
                if path not in self._path_chunks_in_progress:
                    self._path_chunks_in_progress[path] = set()

                fh_state = self._fh_prefetch_state[fh]
                path_chunks = self._path_chunks_in_progress[path]

                # Determine prefetch window: from current file handle's read position for fetch_ahead_chunks chunks
                # This ensures each file handle only prefetches its own window, not the entire file
                desired_prefetch_end = (
                    start + (self.fetch_ahead_chunks * self.chunk_size) - 1
                )

                # Clamp prefetch window to file size boundaries
                if file_size is not None:
                    desired_prefetch_end = min(desired_prefetch_end, file_size - 1)

                # If we're already at or past EOF, nothing to prefetch
                if file_size is not None and start >= file_size:
                    return

                # Calculate chunk-aligned prefetch start
                # Note: 'start' parameter is already next_aligned_start from read() caller,
                # which is the chunk AFTER the current read, so we can use it directly
                read_chunk_start = (start // self.chunk_size) * self.chunk_size

                # Optimize: only prefetch the NEW portion beyond what this file handle has already prefetched
                if fh_state["last_prefetch_pos"] >= start:
                    # This file handle has already prefetched past this read position
                    # Only prefetch the new portion beyond our last prefetch for this file handle
                    prefetch_start = fh_state["last_prefetch_pos"] + 1
                    prefetch_end = desired_prefetch_end

                    # If there's nothing new to prefetch for this file handle, skip
                    if prefetch_start > prefetch_end:
                        return
                else:
                    # This file handle hasn't prefetched this area yet
                    # Start from the chunk passed in (which is already the next chunk after current read)
                    prefetch_start = read_chunk_start
                    prefetch_end = desired_prefetch_end

                # Calculate chunk-aligned ranges to prefetch
                chunks_to_fetch = []
                current_chunk_start = (
                    prefetch_start // self.chunk_size
                ) * self.chunk_size

                while current_chunk_start <= prefetch_end:
                    chunk_end = min(
                        current_chunk_start + self.chunk_size - 1, prefetch_end
                    )

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
                fh_state["last_prefetch_pos"] = prefetch_end
                fh_state["prefetch_window_end"] = prefetch_end

                # Schedule chunk fetches using global scheduler for fair multi-user allocation
                if chunks_to_fetch:
                    num_chunks = len(chunks_to_fetch)
                    window_size_mb = (prefetch_end - prefetch_start + 1) / (1024 * 1024)
                    log.debug(
                        f"Prefetch scheduled: path={path} count={num_chunks} window=[{prefetch_start}-{prefetch_end}] size={window_size_mb:.1f}MB"
                    )

                    # Chunks are already marked as in-progress above to prevent race conditions
                    # Schedule chunks with the global scheduler for fair allocation
                    await self._prefetch_scheduler.schedule_chunks(
                        path=path,
                        url=url,
                        chunks=chunks_to_fetch,
                        cache_manager=self.cache,
                        fetch_func=self._fetch_data_block_with_cleanup,
                    )
                # No log when no chunks to prefetch - reduces noise

            except Exception as e:
                log.debug(f"Prefetch coordination failed: path={path} error={e}")
                # Best-effort: ignore prefetch errors

    async def _fetch_data_block_with_cleanup(
        self, path: str, url: str, start: int, end: int
    ) -> bytes:
        """Wrapper for _fetch_data_block that handles prefetch state cleanup."""
        try:
            return await self._fetch_data_block(path, url, start, end)
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
                    remaining_handles = [
                        h for h in self._file_handles.values() if h.get("path") == path
                    ]
                    if not remaining_handles:
                        # No other handles for this path, clean up shared path state
                        self._path_chunks_in_progress.pop(path, None)
                        self._prefetch_locks.pop(path, None)
            log.trace(f"release: fh={fh} path={path}")
        except Exception as ex:
            log.exception("release error fh=%s: %s", fh, ex)
            raise pyfuse3.FUSEError(errno.EIO)

    async def flush(self, fh: int) -> None:
        """Flush file data (no-op for read-only filesystem)."""
        return None

    async def fsync(self, fh: int, datasync: bool) -> None:
        """Sync file data (no-op for read-only filesystem)."""
        return None

    async def access(self, inode: pyfuse3.InodeT, mode: int, ctx=None) -> None:
        """Check file access permissions.
        Be permissive for write checks to avoid client false negatives; actual writes still fail with EROFS.
        """
        try:
            with self._tree_lock:
                # Check existence in tree (no database query needed!)
                node = self._inode_to_node.get(inode)
                if node is None:
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
            log.debug(
                f"Denied unlink via FUSE: parent_inode={parent_inode}, name={name!r}"
            )
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
            log.debug(
                f"Denied rmdir via FUSE: parent_inode={parent_inode}, name={name!r}"
            )
            raise pyfuse3.FUSEError(errno.EROFS)
        except pyfuse3.FUSEError:
            raise
        except Exception as ex:
            log.exception("rmdir error: parent=%s name=%s: %s", parent_inode, name, ex)
            raise pyfuse3.FUSEError(errno.EIO)

    async def rename(
        self,
        parent_inode_old: int,
        name_old: bytes,
        parent_inode_new: int,
        name_new: bytes,
        flags: int,
        ctx,
    ):
        """Rename/move a file or directory."""
        try:
            # Allow only internal/provider-driven renames; deny user-initiated via FUSE
            log.debug(
                f"Denied rename via FUSE: old_parent={parent_inode_old}, new_parent={parent_inode_new}, "
                f"name_old={name_old!r}, name_new={name_new!r}, flags={flags}"
            )
            raise pyfuse3.FUSEError(errno.EROFS)
        except pyfuse3.FUSEError:
            raise
        except Exception as ex:
            log.exception(
                "rename error: old_parent=%s new_parent=%s name_old=%s name_new=%s: %s",
                parent_inode_old,
                parent_inode_new,
                name_old,
                name_new,
                ex,
            )
            raise pyfuse3.FUSEError(errno.EIO)

    # HTTP helpers

    def _refresh_download_url(self, path: str, target_url: str) -> str | None:
        import time

        self._url_cache.pop(path, None)
        fresh_url = self.db.get_download_url(path, for_http=True, force_resolve=True)

        if fresh_url and fresh_url != target_url:
            self._url_cache[path] = {"url": fresh_url, "timestamp": time.time()}
            return fresh_url

    def _get_range_request_headers(self, start: int, end: int) -> httpx.Headers:
        return httpx.Headers(
            {
                "Accept-Encoding": "identity",
                "Connection": "keep-alive",
                "Range": f"bytes={start}-{end}",
            }
        )

    async def _attempt_range_preflight_checks(
        self, path: str, target_url: str, headers: httpx.Headers
    ) -> str:
        """
        Attempts to verify that the server will honour range requests by requesting the HEAD of the media URL.

        Sometimes, the request will return a 200 OK with the full content instead of a 206 Partial Content,
        even when the server *does* support range requests.

        This wastes bandwidth, and is undesirable for streaming large media files.

        Returns:
            The effective URL that was successfully used (may differ from input if refreshed).
        """

        max_preflight_attempts = 4
        backoffs = [0.2, 0.5, 1.0]

        for preflight_attempt in range(max_preflight_attempts):
            is_max_attempt = preflight_attempt == (max_preflight_attempts - 1)

            try:
                preflight_response = await self.async_client.head(
                    url=target_url,
                    headers=headers,
                )
                preflight_response.raise_for_status()

                preflight_status_code = preflight_response.status_code

                if preflight_status_code == HTTPStatus.PARTIAL_CONTENT:
                    # Preflight passed, proceed to actual request
                    return target_url
                elif preflight_status_code == HTTPStatus.OK:
                    if not is_max_attempt:
                        # Server refused range request. Serving this request would return the full media file,
                        # which eats downloader bandwidth usage unnecessarily. Wait and retry.
                        log.warning(
                            f"Server doesn't support range requests yet: path={path} (retrying)"
                        )
                        await trio.sleep(0.5)
                        continue
                    # Unable to get range support after retries
                    raise pyfuse3.FUSEError(errno.EIO)
            except httpx.RemoteProtocolError as e:
                log.debug(
                    f"HTTP protocol error (attempt {preflight_attempt + 1}/{max_preflight_attempts}): path={path} error={type(e).__name__}"
                )
                if not is_max_attempt:
                    await trio.sleep(
                        backoffs[min(preflight_attempt, len(backoffs) - 1)]
                    )
                    continue
                raise pyfuse3.FUSEError(errno.EIO) from e
            except httpx.HTTPStatusError as e:
                preflight_status_code = e.response.status_code

                log.debug(f"Preflight HTTP error {preflight_status_code}: path={path}")

                if (
                    preflight_status_code == HTTPStatus.NOT_FOUND
                    or preflight_status_code == HTTPStatus.GONE
                ):
                    # File can't be found at this URL; try refreshing the URL once
                    if preflight_attempt == 0:
                        fresh_url = await trio.to_thread.run_sync(
                            self._refresh_download_url, path, target_url
                        )

                        if fresh_url is not None:
                            log.warning(
                                f"URL refresh after HTTP {preflight_status_code}: path={path}"
                            )
                            target_url = fresh_url
                            await trio.sleep(0.5)  # Brief pause before retry
                            continue
                    # No fresh URL or still erroring after refresh
                    raise pyfuse3.FUSEError(errno.ENOENT)
                else:
                    # Other unexpected status codes
                    log.warning(
                        f"Unexpected preflight HTTP {preflight_status_code}: path={path}"
                    )
                    raise pyfuse3.FUSEError(errno.EIO)
            except (httpx.TimeoutException, httpx.ConnectError, httpx.InvalidURL) as e:
                log.debug(
                    f"HTTP request failed (attempt {preflight_attempt + 1}/{max_preflight_attempts}): path={path} error={type(e).__name__}"
                )

                if preflight_attempt == 0:
                    # On first exception, try refreshing the URL in case it's a connectivity issue
                    fresh_url = await trio.to_thread.run_sync(
                        self._refresh_download_url, path, target_url
                    )

                    if fresh_url is not None:
                        target_url = fresh_url
                        log.warning(f"URL refresh after timeout: path={path}")

                if not is_max_attempt:
                    await trio.sleep(
                        backoffs[min(preflight_attempt, len(backoffs) - 1)]
                    )
                    continue

                raise pyfuse3.FUSEError(errno.EIO) from e
            except Exception as e:
                log.exception(
                    f"Unexpected error during preflight checks for {path}: {e}"
                )
                if not is_max_attempt:
                    await trio.sleep(
                        backoffs[min(preflight_attempt, len(backoffs) - 1)]
                    )
                    continue
                raise
        raise pyfuse3.FUSEError(errno.EIO)

    async def _fetch_data_block(
        self,
        path: str,
        target_url: str,
        start: int,
        end: int,
    ) -> bytes:
        headers = self._get_range_request_headers(start, end)

        try:
            target_url = await self._attempt_range_preflight_checks(
                path,
                target_url,
                headers,
            )
        except Exception as e:
            log.error(f"Preflight checks failed for {path}: {e}")
            raise

        max_attempts = 4
        backoffs = [0.2, 0.5, 1.0]

        for attempt in range(max_attempts):
            is_max_attempt = attempt == (max_attempts - 1)

            try:
                async with self.async_client.stream(
                    "GET",
                    url=target_url,
                    headers=headers,
                ) as stream:
                    stream.raise_for_status()

                    range_bytes = end - start + 1
                    content_length = stream.headers.get("Content-Length")

                    if (
                        stream.status_code == HTTPStatus.OK
                        and content_length is not None
                        and int(content_length) > range_bytes
                    ):
                        # Server appears to be ignoring range request and returning full content
                        # This shouldn't happen due to preflight, treat as error
                        log.warning(
                            f"Server returned full content instead of range: path={path}"
                        )
                        raise pyfuse3.FUSEError(errno.EIO)

                    data = bytearray()

                    # Read chunk from the stream and exit once filled.
                    # This *should* prevent the server from sending the rest of the data
                    async for chunk in stream.aiter_bytes(range_bytes):
                        data.extend(chunk)

                        if len(data) >= range_bytes:
                            break

                    return bytes(data[:range_bytes])

            except httpx.HTTPStatusError as e:
                status_code = e.response.status_code

                if status_code == HTTPStatus.FORBIDDEN:
                    # Forbidden - could be rate limiting or auth issue, don't refresh URL
                    log.debug(f"HTTP 403 Forbidden: path={path} attempt={attempt + 1}")
                    if attempt < max_attempts - 1:
                        await trio.sleep(backoffs[min(attempt, len(backoffs) - 1)])
                        continue
                    raise pyfuse3.FUSEError(errno.EACCES)
                elif (
                    status_code == HTTPStatus.NOT_FOUND
                    or status_code == HTTPStatus.GONE
                ):
                    # Preflight catches initial not found errors and attempts to refresh the URL
                    # if it still happens after a real request, don't refresh again and bail out
                    raise pyfuse3.FUSEError(errno.ENOENT)
                elif status_code == HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE:
                    # Requested range not satisfiable; treat as EOF
                    return b""
                elif status_code == HTTPStatus.TOO_MANY_REQUESTS:
                    # Rate limited - back off exponentially, don't refresh URL
                    log.warning(
                        f"HTTP 429 Rate Limited: path={path} attempt={attempt + 1}"
                    )
                    if not is_max_attempt:
                        backoff_time = min(
                            backoffs[min(attempt, len(backoffs) - 1)] * 2, 5.0
                        )
                        await trio.sleep(backoff_time)
                        continue
                    raise pyfuse3.FUSEError(errno.EAGAIN)
                else:
                    # Other unexpected status codes
                    log.warning(f"Unexpected HTTP {status_code}: path={path}")
                    raise pyfuse3.FUSEError(errno.EIO)
            except (httpx.TimeoutException, httpx.ConnectError, httpx.InvalidURL) as e:
                log.debug(
                    f"HTTP request failed (attempt {attempt + 1}/{max_attempts}): path={path} error={type(e).__name__}"
                )

                if attempt == 0:
                    # On first exception, try refreshing the URL in case it's a connectivity issue
                    fresh_url = await trio.to_thread.run_sync(
                        self._refresh_download_url, path, target_url
                    )

                    if fresh_url is not None:
                        target_url = fresh_url
                        log.warning(f"URL refresh after timeout: path={path}")

                if not is_max_attempt:
                    await trio.sleep(backoffs[min(attempt, len(backoffs) - 1)])
                    continue

                raise pyfuse3.FUSEError(errno.EIO) from e
            except httpx.RemoteProtocolError as e:
                # This can happen if the server closes the connection prematurely
                log.debug(
                    f"HTTP protocol error (attempt {attempt + 1}/{max_attempts}): path={path} error={type(e).__name__}"
                )
                if not is_max_attempt:
                    await trio.sleep(backoffs[min(attempt, len(backoffs) - 1)])
                    continue

                raise pyfuse3.FUSEError(errno.EIO) from e
            except pyfuse3.FUSEError:
                if not is_max_attempt:
                    continue
                raise
            except Exception as e:
                log.error(
                    f"Unexpected error fetching data block for {path} ({type(e).__name__}): {e}"
                )
                if not is_max_attempt:
                    await trio.sleep(backoffs[min(attempt, len(backoffs) - 1)])
                    continue
                raise

        raise pyfuse3.FUSEError(errno.EIO)
