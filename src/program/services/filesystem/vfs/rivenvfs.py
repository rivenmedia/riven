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

import pyfuse3
import trio
import os
import shutil
import errno
import subprocess
from typing import (
    TYPE_CHECKING,
    Literal,
    TypedDict,
)
import threading

from kink import di

from program.services.downloaders import Downloader

from program.services.filesystem.vfs.vfs_node import (
    VFSDirectory,
    VFSFile,
    VFSNode,
    VFSRoot,
)

from program.utils.logging import logger
from program.settings.manager import settings_manager
from src.program.services.filesystem.vfs.db import VFSDatabase
from src.program.services.streaming.exceptions import (
    MediaStreamDataException,
    FatalMediaStreamException,
)


from ...streaming import (
    Cache,
    CacheConfig,
    MediaStream,
    ChunksTooSlowException,
    MediaStreamException,
    ChunkCacheNotifier,
)

if TYPE_CHECKING:
    from program.media.item import MediaItem
    from program.media.filesystem_entry import FilesystemEntry


class FileHandle(TypedDict):
    inode: pyfuse3.InodeT
    last_read_end: int
    subtitle_content: bytes | None
    has_stream_error: bool


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
        self.fs = settings_manager.settings.filesystem

        cache_dir = self.fs.cache_dir
        size_mb = self.fs.cache_max_size_mb

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

        di[Cache] = Cache(
            cfg=CacheConfig(
                cache_dir=cache_dir,
                max_size_bytes=effective_max_bytes,
                ttl_seconds=int(getattr(self.fs, "cache_ttl_seconds", 2 * 60 * 60)),
                eviction=(getattr(self.fs, "cache_eviction", "LRU") or "LRU"),
                metrics_enabled=bool(getattr(self.fs, "cache_metrics", True)),
            )
        )

        di[VFSDatabase] = self.vfs_db = VFSDatabase(downloader=downloader)

        di[ChunkCacheNotifier] = ChunkCacheNotifier()

        # VFS Tree: In-memory tree structure for O(1) path lookups
        # This replaces _path_to_inode, _path_aliases, and _dir_tree
        self._root = VFSRoot()
        self._inode_to_node: dict[int, VFSNode] = {pyfuse3.ROOT_INODE: self._root}
        self._next_inode = pyfuse3.InodeT(pyfuse3.ROOT_INODE + 1)

        # Tree lock to prevent race conditions between FUSE operations and tree rebuilds
        # pyfuse3 runs FUSE operations in threads, so we use threading.RLock()
        self._tree_lock = threading.RLock()

        # Pending invalidations for batching (optimization: collect during sync, invalidate at end)
        self._pending_invalidations: set[pyfuse3.InodeT] = set()

        # Profile hash for detecting changes (optimization: skip re-matching if unchanged)
        self._last_profile_hash: int | None = None

        # Set of paths currently being streamed
        self._active_streams: dict[str, MediaStream] = {}

        # Lock for managing active streams dict
        self._active_streams_lock = trio.Lock()

        # Open file handles: fh -> handle info
        self._file_handles: dict[pyfuse3.FileHandleT, FileHandle] = {}
        self._next_fh = pyfuse3.FileHandleT(1)

        # Opener statistics
        self._opener_stats: dict[str, dict] = {}

        # Mount management
        self._mountpoint = os.path.abspath(mountpoint)
        self._thread = None
        self._mounted = False
        self._is_unmounting = False
        self.stream_nursery: trio.Nursery
        self._trio_token: trio.lowlevel.TrioToken | None = None

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

                async with trio.open_nursery() as daemon_nursery:
                    daemon_nursery.start_soon(pyfuse3.main)

                    try:
                        # Open stream nursery for handling streaming operations.
                        # This is separate from the main FUSE loop,
                        # to prevent stream errors from crashing the entire filesystem.
                        async with trio.open_nursery() as stream_nursery:
                            self.stream_nursery = stream_nursery

                            logger.trace(f"Stream nursery ready and waiting for tasks")

                            # Keep the stream nursery alive and ready to spawn tasks
                            await trio.sleep_forever()
                    except* Exception:
                        logger.exception("FUSE main loop nursery error")
                    finally:
                        daemon_nursery.cancel_scope.cancel()

            while not self._is_unmounting:
                logger.trace("Starting FUSE main loop")

                try:
                    # pyfuse3.main is a coroutine that needs to run in its own trio event loop
                    trio.run(_async_main)
                except* Exception:
                    logger.exception("FUSE main loop error, restarting")

            logger.trace(f"FUSE main loop exited")

        self._thread = threading.Thread(target=_fuse_runner, daemon=True)
        self._thread.start()

        logger.log("VFS", f"RivenVFS mounted at {self._mountpoint}")

        # Synchronize library profiles with VFS structure
        self.sync()

    def _stream_key(self, path: str, fh: int) -> str:
        """Generate unique key for stream tracking."""
        return f"{path}:{fh}"

    # ========== VFS Tree Helper Methods ==========

    def _get_node_by_path(self, path: str) -> VFSNode | None:
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
            if isinstance(current, VFSDirectory):
                current = current.get_child(part)

            if current is None:
                return None

        return current

    def _get_or_create_node(
        self,
        path: str,
        is_directory: bool,
        original_filename: str | None = None,
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
            if isinstance(current, VFSDirectory):
                child = current.get_child(part)

                if child is None:
                    # Create the node
                    is_last = i == len(parts) - 1

                    if is_last and not is_directory:
                        if not original_filename:
                            raise ValueError(
                                "original_filename must be provided for file nodes"
                            )

                        child = VFSFile(
                            name=part,
                            original_filename=original_filename,
                            inode=self._assign_inode(),
                            parent=current,
                        )
                    else:
                        child = VFSDirectory(
                            name=part,
                            inode=self._assign_inode(),
                            parent=current,
                        )

                    current.add_child(child)

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

        if not node:
            return False

        # Remove from parent
        if isinstance(node.parent, VFSDirectory):
            node.parent.remove_child(node.name)

        # Remove from inode map
        if node.inode:
            self._inode_to_node.pop(node.inode, None)

        # Recursively remove all children from inode map
        if isinstance(node, VFSDirectory):
            self._remove_node_recursive(node)

        return True

    def _remove_node_recursive(self, node: VFSDirectory) -> None:
        """Recursively remove all children from inode map."""
        for child in list(node.children.values()):
            if child.inode:
                self._inode_to_node.pop(child.inode, None)

            if isinstance(child, VFSDirectory):
                self._remove_node_recursive(child)

    def _assign_inode(self) -> pyfuse3.InodeT:
        """Assign a new inode number."""
        inode = self._next_inode
        self._next_inode = pyfuse3.InodeT(inode + 1)
        return inode

    def _get_parent_inodes(self, node: VFSNode) -> list[pyfuse3.InodeT]:
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
            logger.debug(f"Item {item.id} has no filesystem_entry, skipping VFS add")
            return False

        entry = item.filesystem_entry
        if not isinstance(entry, MediaEntry):
            logger.debug(f"Item {item.id} filesystem_entry is not a MediaEntry")
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

        if item.type == "show":
            for season in item.seasons:
                self.remove(season)
        if item.type == "season":
            for episode in item.episodes:
                self.remove(episode)

        # Only process if this item has a filesystem entry
        if not item.filesystem_entry:
            logger.debug(f"Item {item.id} has no filesystem_entry, skipping VFS remove")
            return False

        entry = item.filesystem_entry
        if not isinstance(entry, MediaEntry):
            logger.debug(f"Item {item.id} filesystem_entry is not a MediaEntry")
            return False

        logger.debug(f"Removing VFS nodes for item {item.id}")

        # Unregister the MediaEntry (video file)
        video_paths = self._unregister_filesystem_entry(entry)

        # Mark as not available in VFS
        entry.available_in_vfs = False

        # Unregister all subtitles for this video
        for subtitle in item.subtitles:
            self._unregister_filesystem_entry(subtitle, video_paths=video_paths)
            subtitle.available_in_vfs = False

        if video_paths:
            logger.debug(
                f"Removed item {item.id} from VFS ({len(video_paths)} path(s))"
            )
            return True

        return False

    def close(self) -> None:
        """Clean up and unmount the filesystem."""
        if self._mounted:
            self._is_unmounting = True
            logger.log("VFS", f"Unmounting RivenVFS from {self._mountpoint}")
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
                except Exception:
                    logger.exception(f"Error requesting FUSE termination")
            else:
                logger.warning("No Trio token available; skipping graceful terminate")

            if self._thread and self._thread.is_alive():
                self._thread.join(timeout=5)
        except Exception:
            logger.exception("Error terminating FUSE")

        try:
            # Close FUSE session after main loop has exited
            pyfuse3.close(unmount=True)
        except Exception:
            logger.exception("Error closing FUSE session")

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
            logger.exception("pyfuse3.terminate() failed")

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

        logger.log("VFS", "Full sync: re-matching library profiles")

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
            logger.debug("Library profiles unchanged, skipping re-matching")
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
                    logger.warning(
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
            logger.debug(f"Re-matched {rematched_count} entries with updated profiles")

        # Step 2: Clear VFS tree and rebuild from scratch
        logger.debug("Clearing VFS tree for rebuild")
        with self._tree_lock:
            # Create new root node
            self._root = VFSRoot()
            self._inode_to_node = {pyfuse3.ROOT_INODE: self._root}
            # Keep inode counter to avoid reusing inodes
            # self._next_inode is preserved

        # Clear pending invalidations for this sync
        self._pending_invalidations.clear()

        # Step 3: Re-register all items
        logger.debug(f"Re-registering {len(item_ids)} items")
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
                    logger.error(f"Failed to register item {item_id}: {e}")
            if registered_count > 0:
                session.commit()

        logger.log("VFS", f"Full sync complete: re-registered {registered_count} items")

        # Step 4: Ensure persistent library profile directories exist
        # This creates /movies, /shows, and /{profile}/movies, /{profile}/shows
        # These directories are never pruned, even when empty
        self._ensure_library_profile_directories()

        # Step 5: Batch invalidate all collected inodes
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
                            logger.trace(f"Could not invalidate inode {inode}: {e}")
                if invalidated_count > 0:
                    logger.trace(
                        f"Batch invalidated {invalidated_count}/{len(self._pending_invalidations)} inodes"
                    )
            finally:
                self._pending_invalidations.clear()

        # Invalidate root directory
        if registered_count > 0:
            try:
                pyfuse3.invalidate_inode(pyfuse3.ROOT_INODE, attr_only=False)
                logger.debug(f"Invalidated root directory cache after sync")
            except Exception as e:
                logger.trace(f"Could not invalidate root directory: {e}")

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

        logger.debug(f"Individual sync: re-registering item {item.id}")

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
                    logger.warning(f"Item {item.id} not found in database, cannot sync")
                    return

                # Step 1: Remove existing VFS nodes for this item
                self.remove(fresh_item)

                # Step 2: Re-add the item with current state (including new subtitles)
                self.add(fresh_item)
                session.commit()

        logger.debug(f"Individual sync complete for item {item.id}")

    def _ensure_library_profile_directories(self) -> None:
        """
        Ensure persistent /movies and /shows directories exist for each library profile.

        This creates the base directory structure that should always be present,
        even when no media files are registered. This provides a consistent
        structure for media players and users.

        Directory structure created:
        - /movies (always present)
        - /shows (always present)
        - /{profile}/movies (for each enabled library profile)
        - /{profile}/shows (for each enabled library profile)

        These directories are never pruned, even when empty.
        """
        with self._tree_lock:
            # Always create base /movies and /shows directories
            for base_dir in ["/movies", "/shows"]:
                node = self._get_node_by_path(base_dir)
                if node is None:
                    # Create the directory node
                    self._get_or_create_node(path=base_dir, is_directory=True)
                    logger.debug(f"Created persistent directory: {base_dir}")

            # Create /movies and /shows for each enabled library profile
            try:
                profiles = settings_manager.settings.filesystem.library_profiles or {}
            except Exception:
                profiles = {}

            for profile in profiles.values():
                if not profile.enabled:
                    continue

                # Create profile root directory
                profile_root = profile.library_path
                if not profile_root.startswith("/"):
                    profile_root = f"/{profile_root}"

                # Create /profile/movies and /profile/shows
                for content_type in ["movies", "shows"]:
                    profile_dir = f"{profile_root}/{content_type}"
                    node = self._get_node_by_path(profile_dir)
                    if node is None:
                        # Create the directory node
                        self._get_or_create_node(path=profile_dir, is_directory=True)
                        logger.debug(f"Created persistent directory: {profile_dir}")

    def _register_filesystem_entry(
        self,
        entry: FilesystemEntry,
        video_paths: list[str] | None = None,
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
                    created_at=(entry.created_at.isoformat()),
                    updated_at=(entry.updated_at.isoformat()),
                    entry_type="media",
                ):
                    registered_paths.append(path)

            return registered_paths

        elif isinstance(entry, SubtitleEntry):
            # Register SubtitleEntry (subtitle file)
            if not video_paths:
                logger.warning(
                    f"Cannot register subtitle {entry.id} without video_paths"
                )
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
                    created_at=(entry.created_at.isoformat()),
                    updated_at=(entry.updated_at.isoformat()),
                    entry_type="subtitle",
                ):
                    registered_paths.append(subtitle_path)

            return registered_paths

        else:
            logger.warning(f"Unknown FilesystemEntry type: {type(entry)}")
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
                logger.warning(
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
            logger.warning(f"Unknown FilesystemEntry type: {type(entry)}")
            return []

    def _register_clean_path(
        self,
        clean_path: str,
        original_filename: str,
        file_size: int,
        created_at: str,
        updated_at: str,
        entry_type: Literal["media", "subtitle"] = "media",
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
                logger.debug(f"Path already registered: {clean_path}")
                return True

            # Create node in tree
            node = self._get_or_create_node(
                path=clean_path,
                is_directory=False,
                original_filename=original_filename,
            )

            if isinstance(node, VFSFile):
                # Populate metadata in node
                node.file_size = file_size
                node.created_at = created_at
                node.updated_at = updated_at
                node.entry_type = entry_type

            # Get parent inodes for invalidation (collect for batching)
            parent_inodes = self._get_parent_inodes(node)

            # Collect invalidations for batching instead of invalidating immediately
            # This is a critical optimization: reduces syscalls from O(n) to O(1)
            self._pending_invalidations.update(parent_inodes)

        return True

    def _is_persistent_directory(self, path: str) -> bool:
        """
        Check if a directory is a persistent library profile directory.

        Persistent directories are never pruned, even when empty:
        - /movies
        - /shows
        - /{profile}/movies
        - /{profile}/shows

        Args:
            path: NORMALIZED VFS path to check

        Returns:
            True if this is a persistent directory that should never be removed
        """
        # Base directories are always persistent
        if path in ["/movies", "/shows"]:
            return True

        # Check if this is a library profile directory
        # Format: /{profile}/movies or /{profile}/shows
        parts = [p for p in path.split("/") if p]

        if len(parts) == 2:
            # Could be /{profile}/movies or /{profile}/shows
            profile_name = parts[0]
            content_type = parts[1]

            if content_type in ["movies", "shows"]:
                # Check if this profile exists and is enabled
                try:
                    profiles = (
                        settings_manager.settings.filesystem.library_profiles or {}
                    )
                    for profile in profiles.values():
                        if (
                            profile.enabled
                            and profile.library_path.strip("/") == profile_name
                        ):
                            return True
                except Exception:
                    pass

        return False

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

            if not parent or not isinstance(parent, VFSDirectory):
                return False

            parent.remove_child(node.name)

            if node.inode in self._inode_to_node:
                del self._inode_to_node[node.inode]

            # Walk up and remove empty parent directories
            # Skip persistent library profile directories (/movies, /shows, /{profile}/movies, /{profile}/shows)
            current = parent
            while current and current.parent:  # Don't remove root
                # Get the full path for this directory
                current_path = current.path

                # Check if this is a persistent directory that should never be removed
                if self._is_persistent_directory(current_path):
                    # This is a persistent directory - don't remove it, but invalidate cache
                    inodes_to_invalidate.add(current.inode)
                    break

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

    def _list_directory_cached(self, path: str) -> list[dict]:
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
            if node is None or not isinstance(node, VFSDirectory):
                return []

            # Build result list from node's children - no database queries!
            children = []
            for name, child in node.children.items():
                children.append(
                    {
                        "name": name,
                        "is_directory": isinstance(child, VFSDirectory),
                    }
                )

            return children

    def _get_path_from_inode(self, inode: int) -> str:
        """Get path from inode number using the VFS tree."""
        with self._tree_lock:
            node = self._inode_to_node.get(inode)

            if node is None:
                raise pyfuse3.FUSEError(errno.ENOENT)

            return node.path

    @staticmethod
    def _current_time_ns() -> int:
        """Get current time in nanoseconds."""
        import time

        return int(time.time() * 1e9)

    def _invalidate_entry(
        self,
        parent_path: str,
        entry_name: str,
        deleted_inode: pyfuse3.InodeT | None = None,
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
                logger.warning(
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
                    logger.warning(f"Failed to invalidate inode {ino}: {e}")

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
            immediate_parent,
            os.path.basename(file_path),
            operation="add",
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
            # Hint larger block size to kernel
            attrs.st_blksize = 128 * 1024
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
            if isinstance(node, VFSDirectory):
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

            if not isinstance(node, VFSFile):
                logger.error(
                    f"Node type mismatch for inode={inode} path={path}. Expected VFSFile, got {type(node).__name__}"
                )
                raise pyfuse3.FUSEError(errno.ENOENT)

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

            # We already know it's a file from the VFSDirectory check above
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
            logger.exception(f"getattr error for inode={inode}")
            raise pyfuse3.FUSEError(errno.EIO)

    async def lookup(
        self,
        parent_inode: pyfuse3.InodeT,
        name: bytes,
        ctx=None,
    ) -> pyfuse3.EntryAttributes:
        """Look up a directory entry using VFS tree."""
        try:
            with self._tree_lock:
                # Get parent node from tree
                parent_node = self._inode_to_node.get(parent_inode)
                if parent_node is None:
                    raise pyfuse3.FUSEError(errno.ENOENT)

                if not isinstance(parent_node, VFSDirectory):
                    raise pyfuse3.FUSEError(errno.ENOTDIR)

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
            logger.exception(f"lookup error: parent={parent_inode} name={name}")
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
                if not isinstance(node, VFSDirectory):
                    raise pyfuse3.FUSEError(errno.ENOTDIR)

            # Return the inode as file handle for directories
            return pyfuse3.FileHandleT(inode)
        except pyfuse3.FUSEError:
            raise
        except Exception:
            logger.exception(f"opendir error for inode={inode}")
            raise pyfuse3.FUSEError(errno.EIO)

    async def readdir(
        self,
        fh: pyfuse3.FileHandleT,
        start_id: int,
        token: pyfuse3.ReaddirToken,
    ):
        """Read directory entries."""
        try:
            path = self._get_path_from_inode(fh)
            entries = self._list_directory_cached(path)

            # Build directory listing
            with self._tree_lock:
                node = self._inode_to_node.get(fh)
                parent_inode = (
                    node.parent.inode if node and node.parent else pyfuse3.ROOT_INODE
                )

                items = [(b".", pyfuse3.InodeT(fh)), (b"..", parent_inode)]

                for entry in entries:
                    name_bytes = entry["name"].encode("utf-8")

                    # Get child node from tree
                    if isinstance(node, VFSDirectory):
                        child_node = node.get_child(entry["name"])

                        if child_node and child_node.inode:
                            items.append((name_bytes, child_node.inode))

            # Send directory entries starting from offset
            for idx in range(start_id, len(items)):
                name_bytes, child_ino = items[idx]

                if child_ino:
                    attrs = await self.getattr(child_ino)
                else:
                    attrs = pyfuse3.EntryAttributes()

                if not pyfuse3.readdir_reply(
                    token, pyfuse3.FileNameT(name_bytes), attrs, idx + 1
                ):
                    break
        except pyfuse3.FUSEError:
            raise
        except Exception:
            logger.exception(f"readdir error for inode={fh}")
            raise pyfuse3.FUSEError(errno.EIO)

    async def open(self, inode: pyfuse3.InodeT, flags: int, ctx) -> pyfuse3.FileInfo:
        """Open a file for reading."""
        try:
            with self._tree_lock:
                # Get node from tree and verify it's a file
                node = self._inode_to_node.get(inode)

                if node is None:
                    raise pyfuse3.FUSEError(errno.ENOENT)

                if not isinstance(node, VFSFile):
                    raise pyfuse3.FUSEError(errno.EISDIR)

                path = node.path

            logger.trace(f"open: path={path} inode={inode} fh_pending flags={flags}")

            # Only allow read access
            if flags & os.O_RDWR or flags & os.O_WRONLY:
                raise pyfuse3.FUSEError(errno.EACCES)

            # Create file handle with minimal metadata
            # Everything else will be resolved from the inode when needed
            fh = self._next_fh
            self._next_fh = pyfuse3.FileHandleT(self._next_fh + 1)
            self._file_handles[fh] = {
                "inode": inode,  # Store inode to resolve node/metadata later
                "last_read_end": 0,
                "subtitle_content": None,
                "has_stream_error": False,
            }

            logger.trace(f"open: path={path} fh={fh}")
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

        stream = None

        try:
            # Log cache stats asynchronously (don't block on trim/I/O)
            try:
                await di[Cache].maybe_log_stats()
            except Exception:
                pass

            handle_info = self._file_handles.get(fh)

            if not handle_info:
                raise pyfuse3.FUSEError(errno.EBADF)

            if handle_info["has_stream_error"]:
                raise pyfuse3.FUSEError(errno.ECONNABORTED)

            # Resolve node from inode to get current metadata
            inode = handle_info.get("inode")

            if not inode:
                raise pyfuse3.FUSEError(errno.EBADF)

            with self._tree_lock:
                node = self._inode_to_node.get(inode)

                if not node:
                    raise pyfuse3.FUSEError(errno.ENOENT)

                if not isinstance(node, VFSFile):
                    raise pyfuse3.FUSEError(errno.EISDIR)

                file_size = node.file_size

                if file_size is None:
                    raise pyfuse3.FUSEError(errno.EIO)

                path = node.path
                entry_type = node.entry_type
                original_filename = node.original_filename

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
                    logger.error(f"Invalid subtitle identifier: {original_filename}")
                    raise pyfuse3.FUSEError(errno.ENOENT)

                parts = original_filename.split(":", 2)

                if len(parts) != 3:
                    logger.error(f"Malformed subtitle identifier: {original_filename}")
                    raise pyfuse3.FUSEError(errno.ENOENT)

                _, parent_original_filename, language = parts

                # Fetch subtitle content from database (subtitles are small, read once)
                subtitle_content = await trio.to_thread.run_sync(
                    lambda: self.vfs_db.get_subtitle_content(
                        parent_original_filename,
                        language,
                    )
                )

                if subtitle_content is None:
                    logger.error(
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
                logger.error(f"No original_filename for {path}")
                raise pyfuse3.FUSEError(errno.ENOENT)

            # Calculate request range
            request_range = (off, min(off + size - 1, file_size - 1))

            request_start, request_end = request_range
            request_size = request_end - request_start + 1

            if request_end < request_start:
                return b""

            stream = await self._get_stream(
                path=path,
                fh=fh,
                file_size=file_size,
                original_filename=original_filename,
            )

            return await stream.read(
                request_start=request_start,
                request_end=request_end,
                request_size=request_size,
            )
        except ChunksTooSlowException as e:
            if stream:
                logger.error(
                    f"Timeout reading {stream.file_metadata['path']} fh={fh} off={off} size={size}: {e}"
                )

            raise pyfuse3.FUSEError(errno.ETIMEDOUT) from e
        except MediaStreamDataException as e:
            if stream:
                logger.error(
                    f"{e.__class__.__name__} "
                    f"data error reading {stream.file_metadata['path']} "
                    f"fh={fh} "
                    f"off={off} "
                    f"size={size}"
                    f": {e}"
                )

            handle_info = self._file_handles.get(fh)

            if handle_info:
                # On media stream errors, something extremely bad happened during the streaming process
                # which broke the integrity of the bytes being served to the client.
                # This usually leads to playback issues, player hangs, and overall glitchiness.
                #
                # Mark that this handle has encountered a fatal stream error so that it can be killed.
                handle_info["has_stream_error"] = True

            raise pyfuse3.FUSEError(errno.EIO) from e
        except FatalMediaStreamException as e:
            if stream:
                logger.error(
                    f"{e.__class__.__name__} "
                    f"error reading {stream.file_metadata['path']} "
                    f"fh={fh} "
                    f"off={off} "
                    f"size={size}"
                    f": {e}"
                )

            return b""
        except pyfuse3.FUSEError:
            logger.debug(f"FUSE error occurred")
            return b""
        except ExceptionGroup:
            logger.exception(f"read(group) error fh={fh}")
            raise pyfuse3.FUSEError(errno.EIO)
        except Exception:
            logger.exception(f"read(simple) error fh={fh}")
            raise pyfuse3.FUSEError(errno.EIO)

    async def release(self, fh: pyfuse3.FileHandleT) -> None:
        """Release/close a file handle."""

        try:
            handle_info = self._file_handles.pop(fh, None)
            path = None

            if handle_info:
                # Resolve path from inode
                inode = handle_info.get("inode")
                if inode:
                    with self._tree_lock:
                        node = self._inode_to_node.get(inode)
                        if node:
                            path = node.path

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
                            await active_stream.kill()

            logger.trace(f"release: fh={fh} path={path}")
        except pyfuse3.FUSEError:
            raise
        except Exception:
            logger.exception(f"release error fh={fh}")
            raise pyfuse3.FUSEError(errno.EIO)

    async def flush(self, fh: int) -> None:
        """Flush file data (no-op for read-only filesystem)."""
        return None

    async def fsync(self, fh: int, datasync: bool) -> None:
        """Sync file data (no-op for read-only filesystem)."""
        return None

    async def access(self, inode: pyfuse3.InodeT, mode: int, ctx=None) -> bool:
        """Check file access permissions.
        Be permissive for write checks to avoid client false negatives; actual writes still fail with EROFS.
        """
        try:
            with self._tree_lock:
                # Check existence in tree (no database query needed!)
                node = self._inode_to_node.get(inode)
                if node is None:
                    raise pyfuse3.FUSEError(errno.ENOENT)

            return False
        except pyfuse3.FUSEError:
            raise
        except Exception:
            logger.exception(f"access error inode={inode} mode={mode}")
            raise pyfuse3.FUSEError(errno.EIO)

    async def unlink(self, parent_inode: int, name: bytes, ctx):
        """Remove a file."""
        try:
            # Deny user-initiated deletes; managed via provider interfaces only
            logger.debug(
                f"Denied unlink via FUSE: parent_inode={parent_inode}, name={name!r}"
            )
            raise pyfuse3.FUSEError(errno.EROFS)
        except pyfuse3.FUSEError:
            raise
        except Exception:
            logger.exception(f"unlink error: parent={parent_inode} name={name}")
            raise pyfuse3.FUSEError(errno.EIO)

    async def rmdir(self, parent_inode: int, name: bytes, ctx):
        """Remove a directory."""
        try:
            # Deny user-initiated directory deletes; managed via provider interfaces only
            logger.debug(
                f"Denied rmdir via FUSE: parent_inode={parent_inode}, name={name!r}"
            )
            raise pyfuse3.FUSEError(errno.EROFS)
        except pyfuse3.FUSEError:
            raise
        except Exception:
            logger.exception(f"rmdir error: parent={parent_inode} name={name}")
            raise pyfuse3.FUSEError(errno.EIO)

    async def rename(
        self,
        parent_inode_old: int,
        name_old: str,
        parent_inode_new: int,
        name_new: str,
        flags: int,
        ctx,
    ):
        """Rename/move a file or directory."""
        try:
            # Allow only internal/provider-driven renames; deny user-initiated via FUSE
            logger.debug(
                f"Denied rename via FUSE: old_parent={parent_inode_old}, new_parent={parent_inode_new}, "
                f"name_old={name_old!r}, name_new={name_new!r}, flags={flags}"
            )
            raise pyfuse3.FUSEError(errno.EROFS)
        except pyfuse3.FUSEError:
            raise
        except Exception:
            logger.exception(
                f"rename error: old_parent={parent_inode_old} new_parent={parent_inode_new} name_old={name_old} name_new={name_new}"
            )
            raise pyfuse3.FUSEError(errno.EIO)

    async def _get_stream(
        self,
        path: str,
        fh: pyfuse3.FileHandleT,
        file_size: int,
        original_filename: str,
    ) -> MediaStream:
        """
        Get the file handle's stream. If no stream exists, initialise it.

        Args:
            path: The path to stream.
            fh: The file handle associated with the stream.
            file_size: The size of the file to stream.
            original_filename: The original filename in the backend.
        Returns:
            The MediaStream for the specified path and file handle.
        """

        stream_key = self._stream_key(path, fh)

        if stream_key not in self._active_streams:
            async with self._active_streams_lock:
                stream = MediaStream(
                    fh=fh,
                    file_size=file_size,
                    path=path,
                    original_filename=original_filename,
                )

                self._active_streams[stream_key] = stream

                # Start the main stream loop in the background,
                # dormant until the stream_start_event is set.
                self.stream_nursery.start_soon(stream.run)

        return self._active_streams[stream_key]
