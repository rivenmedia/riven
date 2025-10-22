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
from dataclasses import dataclass
import subprocess
from typing import (
    TYPE_CHECKING,
    Dict,
    List,
    Optional,
    TypedDict,
)

import threading

from program.services.downloaders import Downloader

import pyfuse3
import trio

from program.settings.models import FilesystemModel
from src.program.services.streaming.exceptions import MediaStreamException
from src.program.services.streaming.media_stream import MediaStream
from .db import VFSDatabase

from program.utils.logging import logger as log
from program.settings.manager import settings_manager
from .cache import Cache, CacheConfig

if TYPE_CHECKING:
    from program.media.item import MediaItem
    from program.media.filesystem_entry import FilesystemEntry


@dataclass
class VFSNode:
    """
    Represents a node (file or directory) in the VFS tree.

    This is the core data structure for the in-memory VFS tree, providing
    O(1) lookups and eliminating the need for path resolution.

    Attributes:
        name: Name of this node (e.g., "Frozen.mkv" or "movies")
        is_directory: True if this is a directory, False if it's a file
        original_filename: Original filename from debrid provider (for files only)
                          This is used to look up the MediaEntry in the database.
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
    original_filename: str | None = None
    inode: pyfuse3.InodeT | None = None
    parent: "VFSNode | None" = None

    # Cached metadata for files (eliminates database queries)
    file_size: int | None = None
    created_at: str | None = None
    updated_at: str | None = None
    entry_type: str | None = None
    probed_data: dict | None = None
    parsed_data: dict | None = None
    bitrate: int | None = None
    duration: int | None = None

    def __post_init__(self):
        """Initialize children dict after dataclass init."""
        if not hasattr(self, "_children"):
            self._children: dict[str, VFSNode] = {}

    @property
    def children(self) -> dict[str, "VFSNode"]:
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

    def remove_child(self, name: str) -> "VFSNode | None":
        """Remove and return a child node by name."""
        child = self.children.pop(name, None)
        if child:
            child.parent = None
        return child

    def get_child(self, name: str) -> "VFSNode | None":
        """Get a child node by name."""
        return self.children.get(name)

    def __repr__(self) -> str:
        return f"VFSNode(name={self.name!r}, is_dir={self.is_directory}, inode={self.inode}, children={len(self.children)})"


class FileHandle(TypedDict):
    inode: pyfuse3.InodeT
    sequential_reads: int
    last_read_start: int
    last_read_end: int
    bitrate: int | None
    duration: int | None
    subtitle_content: bytes | None


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
            log.bind(component="RivenVFS").warning(
                f"cache_max_size_mb clamped to available space: {effective_max_bytes // (1024*1024)} MB"
            )

        self.cache = Cache(
            cfg=CacheConfig(
                cache_dir=cache_dir,
                max_size_bytes=effective_max_bytes,
                ttl_seconds=int(getattr(fs, "cache_ttl_seconds", 2 * 60 * 60)),
                eviction=(getattr(fs, "cache_eviction", "LRU") or "LRU"),
                metrics_enabled=bool(getattr(fs, "cache_metrics", True)),
            )
        )

        self.downloader = downloader
        self.db = VFSDatabase(downloader=downloader)

        # VFS Tree: In-memory tree structure for O(1) path lookups
        # This replaces _path_to_inode, _path_aliases, and _dir_tree
        self._root = VFSNode(name="", is_directory=True, inode=pyfuse3.ROOT_INODE)
        self._inode_to_node: dict[int, VFSNode] = {pyfuse3.ROOT_INODE: self._root}
        self._next_inode = pyfuse3.InodeT(pyfuse3.ROOT_INODE + 1)

        # Tree lock to prevent race conditions between FUSE operations and tree rebuilds
        # pyfuse3 runs FUSE operations in threads, so we use threading.RLock()
        self._tree_lock = threading.RLock()

        # Pending invalidations for batching (optimization: collect during sync, invalidate at end)
        self._pending_invalidations: set[pyfuse3.InodeT] = set()

        # Profile hash for detecting changes (optimization: skip re-matching if unchanged)
        self._last_profile_hash: int | None = None

        # Prefetch window size (number of chunks to prefetch ahead of current read position)
        # This determines how many chunks ahead we prefetch for smooth streaming
        # Will be wired to FilesystemModel configuration separately
        self.fetch_ahead_chunks = fs.fetch_ahead_chunks

        # Validate cache size vs chunk size + prefetch
        # Cache needs to hold: current chunk + prefetch chunks + buffer for concurrent reads
        # Minimum: chunk_size * (fetch_ahead_chunks + 4 for concurrent reads)
        min_cache_mb = fs.chunk_size_mb * (self.fetch_ahead_chunks + 4)
        if size_mb < min_cache_mb:
            log.bind(component="RivenVFS").warning(
                f"Cache size ({size_mb}MB) is too small for chunk_size ({fs.chunk_size_mb}MB) "
                f"and fetch_ahead_chunks ({self.fetch_ahead_chunks}). "
                f"Minimum recommended: {min_cache_mb}MB. "
                f"Cache thrashing may occur with concurrent reads, causing poor performance."
            )

        # Set of paths currently being streamed
        self._active_streams: dict[str, MediaStream] = {}
        self._active_streams_lock = trio.Lock()  # Lock for managing active streams dict

        # Open file handles: fh -> handle info
        self._file_handles: dict[pyfuse3.FileHandleT, FileHandle] = {}
        self._next_fh = pyfuse3.FileHandleT(1)

        # Opener statistics
        self._opener_stats: dict[str, dict] = {}

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
            except Exception:
                log.exception("FUSE main loop error")

        self._thread = threading.Thread(target=_fuse_runner, daemon=True)
        self._thread.start()

        log.log("VFS", f"RivenVFS mounted at {self._mountpoint}")

        # Synchronize library profiles with VFS structure
        self.sync()

    def _stream_key(self, path: str, fh: int) -> str:
        """Generate unique key for stream tracking."""
        return f"{path}:{fh}"

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
        self, path: str, is_directory: bool, original_filename: Optional[str] = None
    ) -> VFSNode:
        """
        Get or create a node at the given path, creating parent directories as needed.

        Args:
            path: NORMALIZED VFS path (caller must normalize)
            is_directory: Whether this is a directory
            original_filename: Original filename from debrid provider (for files)

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
                        original_filename=original_filename,
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

    # Public API methods

    def sync(self, item: MediaItem | None = None) -> None:
        """
        Synchronize VFS with database state.

        Two modes:
        1. Full sync (item=None): Re-match all entries and rebuild entire VFS tree
        2. Individual sync (item provided): Re-register this specific item (unregister + register)

        Args:
            item: If provided, only sync this item. If None, full sync.

        Called:
        - During RivenVFS initialization (full sync)
        - When settings change (full sync)
        - After adding subtitles to an item (individual sync)
        - After item metadata changes (individual sync)
        """
        if item is None:
            self._sync_full()
        else:
            self._sync_individual(item)

    def add(self, item: "MediaItem") -> bool:
        """
        Add a MediaItem to the VFS.

        Registers the item's MediaEntry (video file) and all associated SubtitleEntry
        objects in the VFS tree.

        Args:
            item: MediaItem to add to VFS

        Returns:
            True if successfully added, False otherwise
        """
        from program.media.media_entry import MediaEntry

        # Only process if this item has a filesystem entry
        if not item.filesystem_entry:
            log.debug(f"Item {item.id} has no filesystem_entry, skipping VFS add")
            return False

        entry = item.filesystem_entry
        if not isinstance(entry, MediaEntry):
            log.warning(f"Item {item.id} filesystem_entry is not a MediaEntry")
            return False

        # Register the MediaEntry (video file)
        video_paths = self._register_filesystem_entry(entry)

        if not video_paths:
            return False

        # Mark as available in VFS
        entry.available_in_vfs = True

        # Register all subtitles for this video
        for subtitle in item.subtitles:
            self._register_filesystem_entry(subtitle, video_paths=video_paths)
            subtitle.available_in_vfs = True

        return True

    def remove(self, item: "MediaItem") -> bool:
        """
        Remove a MediaItem from the VFS.

        Removes the item's MediaEntry (video file) and all associated SubtitleEntry
        objects from the VFS tree, and prunes empty parent directories.

        Args:
            item: MediaItem to remove from VFS

        Returns:
            True if successfully removed, False otherwise
        """
        from program.media.media_entry import MediaEntry

        # Only process if this item has a filesystem entry
        if not item.filesystem_entry:
            log.debug(f"Item {item.id} has no filesystem_entry, skipping VFS remove")
            return False

        entry = item.filesystem_entry
        if not isinstance(entry, MediaEntry):
            log.warning(f"Item {item.id} filesystem_entry is not a MediaEntry")
            return False

        log.debug(f"Removing VFS nodes for item {item.id}")

        # Unregister the MediaEntry (video file)
        video_paths = self._unregister_filesystem_entry(entry)

        # Mark as not available in VFS
        entry.available_in_vfs = False

        # Unregister all subtitles for this video
        for subtitle in item.subtitles:
            self._unregister_filesystem_entry(subtitle, video_paths=video_paths)
            subtitle.available_in_vfs = False

        if video_paths:
            log.debug(f"Removed item {item.id} from VFS ({len(video_paths)} path(s))")
            return True

        return False

    def close(self) -> None:
        """Clean up and unmount the filesystem."""
        if self._mounted:
            log.log("VFS", f"Unmounting RivenVFS from {self._mountpoint}")
            self._cleanup_mountpoint(self._mountpoint)
            self._mounted = False

    # Helper methods

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
                    log.exception(f"Error requesting FUSE termination")
            else:
                log.warning("No Trio token available; skipping graceful terminate")

            if self._thread and self._thread.is_alive():
                self._thread.join(timeout=5)
        except Exception:
            log.exception("Error terminating FUSE")

        try:
            # Close FUSE session after main loop has exited
            pyfuse3.close(unmount=True)
        except Exception:
            log.exception("Error closing FUSE session")

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
        except Exception:
            log.exception("pyfuse3.terminate() failed")

    def _sync_full(self) -> None:
        """
        Full VFS sync: Re-match all entries and rebuild entire VFS tree.

        Steps:
        1. Check if profiles changed (skip if not)
        2. Re-match all entries against current library profiles
        3. Clear VFS tree
        4. Re-register all entries using add()
        5. Batch invalidate all collected inodes
        """
        from program.media.media_entry import MediaEntry
        from program.services.library_profile_matcher import LibraryProfileMatcher

        log.log("VFS", "Full sync: re-matching library profiles")

        try:
            profiles = settings_manager.settings.filesystem.library_profiles or {}
            current_profile_hash = hash(
                frozenset(
                    (k, hash(frozenset(v.filter_rules.model_dump().items())))
                    for k, v in profiles.items()
                )
            )
        except Exception:
            current_profile_hash = None

        # Skip re-matching if profiles haven't changed
        if (
            current_profile_hash is not None
            and current_profile_hash == self._last_profile_hash
        ):
            log.debug("Library profiles unchanged, skipping re-matching")
            return

        self._last_profile_hash = current_profile_hash

        matcher = LibraryProfileMatcher()

        # Step 1: Re-match all entries against current library profiles and collect item IDs
        from program.db.db import db as db_module

        item_ids = []
        rematched_count = 0

        with db_module.Session() as session:
            entries = (
                session.query(MediaEntry).filter(MediaEntry.is_directory == False).all()
            )

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

                # Store item ID for later registration (avoid duplicates)
                if item.id not in item_ids:
                    item_ids.append(item.id)

            session.commit()
            log.debug(f"Re-matched {rematched_count} entries with updated profiles")

        # Step 2: Clear VFS tree and rebuild from scratch
        log.debug("Clearing VFS tree for rebuild")
        with self._tree_lock:
            # Create new root node
            self._root = VFSNode(name="", is_directory=True, inode=pyfuse3.ROOT_INODE)
            self._inode_to_node = {pyfuse3.ROOT_INODE: self._root}
            # Keep inode counter to avoid reusing inodes
            # self._next_inode is preserved

        # Clear pending invalidations for this sync
        self._pending_invalidations.clear()

        # Step 3: Re-register all items
        log.debug(f"Re-registering {len(item_ids)} items")
        registered_count = 0

        with db_module.Session() as session:
            from program.media.item import MediaItem

            items = session.query(MediaItem).filter(MediaItem.id.in_(item_ids)).all()
            item_map = {item.id: item for item in items}

            for item_id in item_ids:
                try:
                    item = item_map.get(item_id)
                    if not item:
                        continue

                    # Use add() to register the item (handles both media and subtitles)
                    if self.add(item):
                        registered_count += 1
                except Exception as e:
                    log.error(f"Failed to register item {item_id}: {e}")
            if registered_count > 0:
                session.commit()

        log.log("VFS", f"Full sync complete: re-registered {registered_count} items")

        # Step 4: Batch invalidate all collected inodes
        # This is critical: reduces syscalls from O(n) to O(1)
        if self._pending_invalidations:
            invalidated_count = 0
            try:
                for inode in self._pending_invalidations:
                    try:
                        pyfuse3.invalidate_inode(inode, attr_only=False)
                        invalidated_count += 1
                    except OSError as e:
                        # Expected: some inodes may not be in kernel cache
                        # This is not an error, just means kernel already evicted them
                        if getattr(e, "errno", None) != errno.ENOENT:
                            log.trace(f"Could not invalidate inode {inode}: {e}")
                if invalidated_count > 0:
                    log.trace(
                        f"Batch invalidated {invalidated_count}/{len(self._pending_invalidations)} inodes"
                    )
            finally:
                self._pending_invalidations.clear()

        # Invalidate root directory
        if registered_count > 0:
            try:
                pyfuse3.invalidate_inode(pyfuse3.ROOT_INODE, attr_only=False)
                log.debug(f"Invalidated root directory cache after sync")
            except Exception as e:
                log.trace(f"Could not invalidate root directory: {e}")

    def _sync_individual(self, item: "MediaItem") -> None:
        """
        Individual sync: Re-register a specific item (unregister + register).

        This is used when an item's VFS representation needs to be updated without
        doing a full rebuild. For example:
        - After adding subtitles to an existing item
        - After metadata changes that affect paths

        Args:
            item: MediaItem to re-sync
        """
        from sqlalchemy.orm import object_session
        from program.db.db import db as db_module

        log.debug(f"Individual sync: re-registering item {item.id}")

        # Check if item is already in a session
        existing_session = object_session(item)

        if existing_session:
            # Item is in an active session - refresh relationships to get latest data
            # This is crucial when subtitles were just added in the same session
            existing_session.refresh(item, attribute_names=["subtitles"])

            # Step 1: Remove existing VFS nodes for this item
            self.remove(item)

            # Step 2: Re-add the item with current state (including new subtitles)
            self.add(item)
        else:
            # Item is detached - fetch it in a new session
            with db_module.Session() as session:
                from program.media.item import MediaItem

                fresh_item = (
                    session.query(MediaItem).filter(MediaItem.id == item.id).first()
                )
                if not fresh_item:
                    log.warning(f"Item {item.id} not found in database, cannot sync")
                    return

                # Step 1: Remove existing VFS nodes for this item
                self.remove(fresh_item)

                # Step 2: Re-add the item with current state (including new subtitles)
                self.add(fresh_item)
                session.commit()

        log.debug(f"Individual sync complete for item {item.id}")

    def _register_filesystem_entry(
        self, entry: FilesystemEntry, video_paths: Optional[list[str]] = None
    ) -> list[str]:
        """
        Register a FilesystemEntry (MediaEntry or SubtitleEntry) in the VFS.

        Args:
            entry: FilesystemEntry to register (MediaEntry or SubtitleEntry)
            video_paths: For SubtitleEntry, the video paths to register subtitles alongside

        Returns:
            List of registered VFS paths
        """
        from program.media.media_entry import MediaEntry
        from program.media.subtitle_entry import SubtitleEntry
        import os

        if isinstance(entry, MediaEntry):
            # Register MediaEntry (video file)
            all_paths = entry.get_all_vfs_paths()
            registered_paths = []

            for path in all_paths:
                if self._register_clean_path(
                    clean_path=path,
                    original_filename=entry.original_filename,
                    file_size=entry.file_size,
                    created_at=(
                        entry.created_at.isoformat() if entry.created_at else None
                    ),
                    updated_at=(
                        entry.updated_at.isoformat() if entry.updated_at else None
                    ),
                    bitrate=entry.probed_data["bitrate"] if entry.probed_data else None,
                    duration=(
                        entry.probed_data["duration"] if entry.probed_data else None
                    ),
                    entry_type="media",
                ):
                    registered_paths.append(path)

            return registered_paths

        elif isinstance(entry, SubtitleEntry):
            # Register SubtitleEntry (subtitle file)
            if not video_paths:
                log.warning(f"Cannot register subtitle {entry.id} without video_paths")
                return []

            registered_paths = []
            language = entry.language

            for video_path in video_paths:
                # Generate subtitle path alongside video
                directory = os.path.dirname(video_path)
                filename = os.path.basename(video_path)
                name_without_ext = os.path.splitext(filename)[0]
                subtitle_path = os.path.join(
                    directory, f"{name_without_ext}.{language}.srt"
                )

                if self._register_clean_path(
                    clean_path=subtitle_path,
                    original_filename=f"subtitle:{entry.parent_original_filename}:{language}",
                    file_size=entry.file_size,
                    created_at=(
                        entry.created_at.isoformat() if entry.created_at else None
                    ),
                    updated_at=(
                        entry.updated_at.isoformat() if entry.updated_at else None
                    ),
                    bitrate=entry.bitrate,
                    duration=entry.duration,
                    entry_type="subtitle",
                ):
                    registered_paths.append(subtitle_path)

            return registered_paths

        else:
            log.warning(f"Unknown FilesystemEntry type: {type(entry)}")
            return []

    def _unregister_filesystem_entry(
        self,
        entry: FilesystemEntry,
        video_paths: list[str] | None = None,
    ) -> list[str]:
        """
        Unregister a FilesystemEntry (MediaEntry or SubtitleEntry) from the VFS.

        Args:
            entry: FilesystemEntry to unregister (MediaEntry or SubtitleEntry)
            item: Associated MediaItem
            video_paths: For SubtitleEntry, the video paths to unregister subtitles from

        Returns:
            List of unregistered VFS paths
        """
        from program.media.media_entry import MediaEntry
        from program.media.subtitle_entry import SubtitleEntry
        import os

        if isinstance(entry, MediaEntry):
            # Unregister MediaEntry (video file)
            all_paths = entry.get_all_vfs_paths()
            unregistered_paths = []

            for path in all_paths:
                if self._unregister_clean_path(path):
                    unregistered_paths.append(path)

            return unregistered_paths

        elif isinstance(entry, SubtitleEntry):
            # Unregister SubtitleEntry (subtitle file)
            if not video_paths:
                log.warning(
                    f"Cannot unregister subtitle {entry.id} without video_paths"
                )
                return []

            unregistered_paths = []
            language = entry.language

            for video_path in video_paths:
                # Generate subtitle path alongside video
                directory = os.path.dirname(video_path)
                filename = os.path.basename(video_path)
                name_without_ext = os.path.splitext(filename)[0]
                subtitle_path = os.path.join(
                    directory, f"{name_without_ext}.{language}.srt"
                )

                if self._unregister_clean_path(subtitle_path):
                    unregistered_paths.append(subtitle_path)

            return unregistered_paths

        else:
            log.warning(f"Unknown FilesystemEntry type: {type(entry)}")
            return []

    def _register_clean_path(
        self,
        clean_path: str,
        original_filename: str,
        file_size: int,
        created_at: str | None,
        updated_at: str | None,
        bitrate: int | None = None,
        duration: int | None = None,
        entry_type: str = "media",
    ) -> bool:
        """
        Register a clean VFS path with original_filename mapping.

        Creates VFSNode with original_filename reference for later resolution.

        Note: Invalidations are collected in _pending_invalidations and batched
        at the end of _sync_full() for better performance with large libraries.
        """
        clean_path = self._normalize_path(clean_path)

        with self._tree_lock:
            # Check if already registered
            existing_node = self._get_node_by_path(clean_path)
            if existing_node:
                log.debug(f"Path already registered: {clean_path}")
                return True

            # Create node in tree
            node = self._get_or_create_node(
                path=clean_path, is_directory=False, original_filename=original_filename
            )

            # Populate metadata in node
            node.file_size = file_size
            node.created_at = created_at
            node.updated_at = updated_at
            node.entry_type = entry_type
            node.bitrate = bitrate
            node.duration = duration

            # Get parent inodes for invalidation (collect for batching)
            parent_inodes = self._get_parent_inodes(node)

            # Collect invalidations for batching instead of invalidating immediately
            # This is a critical optimization: reduces syscalls from O(n) to O(1)
            self._pending_invalidations.update(parent_inodes)

        return True

    def _unregister_clean_path(self, path: str) -> bool:
        """
        Unregister a VFS path and prune empty parent directories.

        Args:
            path: VFS path to unregister

        Returns:
            True if successfully unregistered
        """
        normalized_path = self._normalize_path(path)
        inodes_to_invalidate = set()

        with self._tree_lock:
            node = self._get_node_by_path(normalized_path)

            if not node:
                return False

            # Remove the file node
            parent = node.parent
            if not parent:
                return False

            parent.remove_child(node.name)
            if node.inode in self._inode_to_node:
                del self._inode_to_node[node.inode]

            # Walk up and remove empty parent directories
            current = parent
            while current and current.parent:  # Don't remove root
                # Check if directory is now empty
                if len(current.children) == 0:
                    # Remove empty directory
                    grandparent = current.parent
                    inodes_to_invalidate.add(current.inode)
                    grandparent.remove_child(current.name)
                    if current.inode in self._inode_to_node:
                        del self._inode_to_node[current.inode]

                    # Move up to check grandparent
                    current = grandparent
                else:
                    # Directory not empty, stop walking up
                    # But still invalidate this directory's cache
                    inodes_to_invalidate.add(current.inode)
                    break

        # Invalidate directory caches
        for inode in inodes_to_invalidate:
            try:
                pyfuse3.invalidate_inode(inode, attr_only=False)
            except Exception:
                pass

        return True

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

    def _list_directory_cached(self, path: str) -> list[Dict]:
        """
        List directory contents using VFS tree for O(1) lookups.

        The VFS tree is built during sync() and provides
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
                    pyfuse3.InodeT(parent_node.inode),
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
            # Metadata was populated during sync()

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
        except Exception:
            log.exception(f"getattr error for inode={inode}")
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
        except Exception:
            log.exception(f"lookup error: parent={parent_inode} name={name}")
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
        except Exception:
            log.exception(f"opendir error for inode={inode}")
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
                if child_ino:
                    attrs = await self.getattr(child_ino)
                if not pyfuse3.readdir_reply(
                    token, pyfuse3.FileNameT(name_bytes), attrs, idx + 1
                ):
                    break
        except pyfuse3.FUSEError:
            raise
        except Exception:
            log.exception(f"readdir error for inode={inode}")
            raise pyfuse3.FUSEError(errno.EIO)

    async def open(self, inode: pyfuse3.InodeT, flags: int, ctx) -> pyfuse3.FileInfo:
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

            log.trace(f"open: path={path} inode={inode} fh_pending flags={flags}")

            # Only allow read access
            if flags & os.O_RDWR or flags & os.O_WRONLY:
                raise pyfuse3.FUSEError(errno.EACCES)

            # Create file handle with minimal metadata
            # Everything else will be resolved from the inode when needed
            fh = self._next_fh
            self._next_fh = pyfuse3.FileHandleT(self._next_fh + 1)
            self._file_handles[fh] = {
                "inode": inode,  # Store inode to resolve node/metadata later
                "sequential_reads": 0,
                "last_read_start": 0,
                "last_read_end": 0,
                "subtitle_content": None,
                "bitrate": node.bitrate,
                "duration": node.duration,
            }

            log.trace(f"open: path={path} fh={fh}")
            return pyfuse3.FileInfo(fh=pyfuse3.FileHandleT(fh))
        except pyfuse3.FUSEError:
            raise

    async def read(self, fh: pyfuse3.FileHandleT, off: int, size: int) -> bytes:
        """
        Read data from file at offset.

        Implements efficient streaming with:
        - Fixed-size chunk fetching (32MB default)
        - Concurrent chunk fetching for cache misses
        - Sequential read detection and prefetching
        - Per-chunk locking to prevent duplicate fetches

        Args:
            fh: File handle from open()
            off: Byte offset to start reading from
            size: Number of bytes to read

        Returns:
            Bytes read from file (may be less than size at EOF)
        """

        try:
            # Log cache stats asynchronously (don't block on trim/I/O)
            try:
                await trio.to_thread.run_sync(self.cache.maybe_log_stats)
            except Exception:
                pass

            handle_info = self._file_handles.get(fh)
            if not handle_info:
                raise pyfuse3.FUSEError(errno.EBADF)

            # Resolve node from inode to get current metadata
            inode = handle_info.get("inode")

            if not inode:
                raise pyfuse3.FUSEError(errno.EBADF)

            with self._tree_lock:
                node = self._inode_to_node.get(inode)
                if not node or node.is_directory:
                    raise pyfuse3.FUSEError(
                        errno.EISDIR if node and node.is_directory else errno.ENOENT
                    )

                path = node.get_full_path()
                file_size = node.file_size
                entry_type = node.entry_type
                original_filename = node.original_filename

                if file_size is None:
                    raise pyfuse3.FUSEError(errno.EIO)

            if size == 0:
                return b""

            # Check if this is a subtitle entry - if so, read from database instead of HTTP
            if entry_type == "subtitle":
                # Subtitles are stored in the database, not fetched via HTTP
                # Parse subtitle identifier from original_filename (resolved from node above)
                # Format: "subtitle:{parent_original_filename}:{language}"
                if not original_filename or not original_filename.startswith(
                    "subtitle:"
                ):
                    log.error(f"Invalid subtitle identifier: {original_filename}")
                    raise pyfuse3.FUSEError(errno.ENOENT)

                parts = original_filename.split(":", 2)
                if len(parts) != 3:
                    log.error(f"Malformed subtitle identifier: {original_filename}")
                    raise pyfuse3.FUSEError(errno.ENOENT)

                parent_original_filename = parts[1]
                language = parts[2]

                # Fetch subtitle content from database (subtitles are small, read once)
                subtitle_content = await trio.to_thread.run_sync(
                    lambda: self.db.get_subtitle_content(
                        parent_original_filename, language
                    )
                )
                if subtitle_content is None:
                    log.error(
                        f"Subtitle content not found for {parent_original_filename} ({language})"
                    )
                    raise pyfuse3.FUSEError(errno.ENOENT)

                # Slice subtitle content in thread (could be large)
                def slice_subtitle():
                    end_offset = min(off + size, len(subtitle_content))
                    return subtitle_content[off:end_offset]

                return await trio.to_thread.run_sync(slice_subtitle)

            # For media entries, continue with normal HTTP streaming logic

            # Fetch URL from database using original_filename from node
            if not original_filename:
                log.error(f"No original_filename for {path}")
                raise pyfuse3.FUSEError(errno.ENOENT)

            # Calculate request and aligned chunk boundaries (use inclusive end)
            request_start = off
            request_end = min(off + size - 1, file_size - 1)
            request_size = request_end - request_start + 1

            if request_end < request_start:
                return b""

            stream = await self._get_stream(
                path=path,
                fh=fh,
                file_size=file_size,
                original_filename=original_filename,
                bitrate=handle_info["bitrate"],
                duration=handle_info["duration"],
            )

            async with stream.lock:
                log.debug(
                    f"Read request: path={path} fh={fh} request_start={request_start} request_end={request_end} size={request_size}"
                )

                # Try cache first for the exact request (cache handles chunk lookup and slicing)
                # Use cache_key to share cache between all paths pointing to same file
                cached_bytes = await trio.to_thread.run_sync(
                    lambda: self.cache.get(
                        cache_key=stream.cache_key,
                        start=request_start,
                        end=request_end,
                    )
                )

                if cached_bytes:
                    returned_data = cached_bytes
                else:
                    is_header_scan = (
                        handle_info["last_read_end"] == 0
                        and 0 <= request_start <= stream.header_size
                    )

                    is_footer_scan = (
                        (
                            handle_info["last_read_end"]
                            < request_start - stream.sequential_read_tolerance
                        )
                        and file_size - stream.footer_size <= request_start <= file_size
                    )

                    if is_header_scan:
                        returned_data = await stream.fetch_header(
                            read_position=request_start,
                            size=request_size,
                        )
                    elif is_footer_scan:
                        returned_data = await stream.fetch_footer(
                            read_position=request_start,
                            size=request_size,
                        )
                    else:
                        if not stream.response:
                            await stream.connect(request_start)

                        returned_data = await stream.read_bytes(
                            start=request_start,
                            end=request_end,
                        )

                is_sequential_read = (
                    off > 0
                    and handle_info["last_read_end"] - stream.sequential_read_tolerance
                    <= off
                    <= handle_info["last_read_end"] + stream.sequential_read_tolerance
                )

                handle_info["sequential_reads"] = (
                    handle_info["sequential_reads"] + 1 if is_sequential_read else 0
                )
                handle_info["last_read_start"] = off
                handle_info["last_read_end"] = off + len(returned_data)

                return returned_data
        except MediaStreamException as e:
            log.error(
                f"{e.__class__.__name__} error reading {stream.path} fh={fh} off={off} size={size}: {e}"
            )
            return b""
        except pyfuse3.FUSEError:
            raise
        except Exception:
            log.exception(f"read(simple) error fh={fh}")
            raise pyfuse3.FUSEError(errno.EIO)

    async def release(self, fh: pyfuse3.FileHandleT) -> None:
        """Release/close a file handle."""

        try:
            handle_info = self._file_handles.pop(fh, None)
            if handle_info:
                # Resolve path from inode
                inode = handle_info.get("inode")
                path = None
                if inode:
                    with self._tree_lock:
                        node = self._inode_to_node.get(inode)
                        if node:
                            path = node.get_full_path()

                # Clean up per-path state if no other handles are using this path
                if path:
                    # Check if any other handles reference the same inode
                    remaining_handles = [
                        h
                        for h in self._file_handles.values()
                        if h.get("inode") == inode
                    ]
                    if not remaining_handles:
                        stream_key = self._stream_key(path, fh)

                        # No other handles for this inode, clean up shared path state
                        active_stream = self._active_streams.pop(stream_key, None)
                        if active_stream:
                            await active_stream.close()
            log.trace(f"release: fh={fh} path={path}")
        except Exception:
            log.error(f"release error fh={fh}")
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
        except Exception:
            log.exception(f"access error inode={inode} mode={mode}")
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
        except Exception:
            log.exception(f"unlink error: parent={parent_inode} name={name}")
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
        except Exception:
            log.exception(f"rmdir error: parent={parent_inode} name={name}")
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
        except Exception:
            log.exception(
                f"rename error: old_parent={parent_inode_old} new_parent={parent_inode_new} name_old={name_old} name_new={name_new}"
            )
            raise pyfuse3.FUSEError(errno.EIO)

    async def _get_stream(
        self,
        path: str,
        fh: pyfuse3.FileHandleT,
        file_size: int,
        original_filename: str,
        bitrate: int | None = None,
        duration: int | None = None,
    ) -> MediaStream:
        """
        Get the file handle's stream. If no stream exists, create and connect it.

        Args:
            path: The path to stream.
            target_url: The URL to stream from.
            start: The starting byte offset for the stream.
            fh: The file handle associated with the stream.

        Returns:
            The MediaStream for the specified path and file handle.
        """
        stream_key = self._stream_key(path, fh)

        if stream_key not in self._active_streams:
            async with self._active_streams_lock:
                # If it's a new stream, set and connect
                stream = MediaStream(
                    vfs=self,
                    fh=fh,
                    file_size=file_size,
                    path=path,
                    original_filename=original_filename,
                    bitrate=bitrate,
                    duration=duration,
                )

                self._active_streams[stream_key] = stream

        return self._active_streams[stream_key]
