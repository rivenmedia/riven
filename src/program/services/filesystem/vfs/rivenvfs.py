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
import errno
from loguru import logger
import logging
import subprocess
import io
from typing import Dict, Optional

import pyfuse3
import trio
import pycurl
import io

from .db import VFSDatabase
from .providers import ProviderManager

log = logger


class _Pyfuse3InterceptHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        try:
            message = record.getMessage()
        except Exception:
            message = str(record)
        # Route all pyfuse3 logs to our dedicated FUSE level
        logger.opt(depth=6, exception=record.exc_info).log("FUSE", message)


def _setup_pyfuse3_logging(debug: bool) -> None:
    """Bridge standard logging from pyfuse3 to loguru at our FUSE level."""
    py_logger = logging.getLogger("pyfuse3")
    py_logger.setLevel(logging.DEBUG if debug else logging.INFO)
    py_logger.propagate = False
    # Replace existing handlers to avoid duplicate outputs
    py_logger.handlers = [h for h in py_logger.handlers if False]
    py_logger.addHandler(_Pyfuse3InterceptHandler())


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

    enable_writeback_cache = True

    def __init__(self, mountpoint: str, providers: Optional[Dict[str, object]] = None, debug_fuse: bool = False) -> None:
        """
        Initialize the Riven Virtual File System.

        Args:
            mountpoint: Directory where the VFS will be mounted
            providers: Dictionary of provider instances (e.g., Real-Debrid, Premiumize)
            debug_fuse: Enable FUSE debug logging

        Raises:
            OSError: If mountpoint cannot be prepared or FUSE initialization fails
        """
        super().__init__()
        self.providers: Dict[str, object] = providers or {}
        self.provider_manager = ProviderManager(self.providers)
        self.db = VFSDatabase(provider_manager=self.provider_manager)

        # Core path <-> inode mapping for FUSE operations
        self._path_to_inode: Dict[str, int] = {"/": pyfuse3.ROOT_INODE}
        self._inode_to_path: Dict[int, str] = {pyfuse3.ROOT_INODE: "/"}
        self._next_inode = pyfuse3.ROOT_INODE + 1

        # URL cache for provider links with automatic expiration
        self._url_cache: Dict[str, Dict[str, object]] = {}
        self.url_cache_ttl = 15 * 60  # 15 minutes

        # Per-path locks to serialize HTTP requests
        self._request_locks: Dict[str, trio.Lock] = {}
        # Per-path network semaphore to allow limited parallel fetches
        self._request_semaphores: Dict[str, trio.Semaphore] = {}
        # Concurrent fetch limit per file path - increased from 3 to 12 for better streaming performance
        # Higher values allow more simultaneous range requests per file when multiple clients
        # are reading the same file or when aggressive buffering/seeking occurs
        self.max_concurrent_fetches = 12

        # Readahead buffer size for streaming optimization (fixed chunk)
        self.readahead_size = 32 * 1024 * 1024  # 32 MiB

        # Open file handles: fh -> handle info
        self._file_handles: Dict[int, Dict] = {}
        self._next_fh = 1

        # Mount management
        self._mountpoint = os.path.abspath(mountpoint)
        self._thread = None
        self._mounted = False
        self._trio_token = None

        # Prepare mountpoint (unmount, create directory)
        self._prepare_mountpoint(self._mountpoint)


        # Initialize pyfuse3 and start main loop in background thread
        fuse_options = set(pyfuse3.default_options)
        fuse_options.add('fsname=rivenvfs')
        fuse_options.add('allow_other')
        if debug_fuse:
            fuse_options.add('debug')
        # Bridge pyfuse3's Python logger to Riven logger
        _setup_pyfuse3_logging(debug_fuse)

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

        log.info(f"Added virtual file: {path}")
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

        log.info(f"Registered existing file with FUSE: {path}")
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
                log.debug(f"Invalidated directory entry for {file_path} in parent {immediate_parent}")

            # Also invalidate any newly created parent directories
            for ino in parent_inodes:
                try:
                    pyfuse3.invalidate_inode(ino, attr_only=True)
                    log.debug(f"Invalidated inode {ino} for newly created parent directory")
                except OSError as e:
                    # Benign if kernel has not cached the inode yet
                    if getattr(e, 'errno', None) == errno.ENOENT:
                        log.debug(f"Skip invalidating uncached inode {ino} after adding {file_path}: {e}")
                    else:
                        raise
        except OSError as e:
            # Downgrade ENOENT during add: often means kernel never cached the parent dir yet
            if getattr(e, 'errno', None) == errno.ENOENT:
                log.debug(f"Benign ENOENT while invalidating after adding {file_path}: {e}")
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
                log.debug(f"Invalidated directory entry for removed {file_path}")
        except OSError as e:
            if getattr(e, 'errno', None) == errno.ENOENT:
                log.debug(f"Benign ENOENT while invalidating after removing {file_path}: {e}")
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
                    log.debug(f"Invalidated potential removed dir entry '{name}' under {grandparent}")

            # One more level up (e.g., title dir)
            ggparent = self._normalize_path(self._get_parent_path(grandparent))
            gname = os.path.basename(grandparent.rstrip('/'))
            if ggparent in self._path_to_inode and gname:
                pyfuse3.invalidate_entry_async(self._path_to_inode[ggparent], gname.encode('utf-8'), ignore_enoent=True)
                log.debug(f"Invalidated potential removed dir entry '{gname}' under {ggparent}")
        except Exception as e:
            if getattr(e, 'errno', None) == errno.ENOENT:
                log.debug(f"Benign ENOENT while invalidating parent dirs for {file_path}: {e}")
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
                log.debug(f"Invalidated old directory entry for renamed {old_path}")

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
            entry_info = self.db.get_entry(path)
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
            if not self.db.exists(child_path):
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

            entry_info = self.db.get_entry(path)
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
            entries = self.list_directory(path)

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
            file_info = self.db.get_entry(path)
            if file_info is None or file_info["is_directory"]:
                raise pyfuse3.FUSEError(errno.ENOENT)

            # Only allow read access
            if flags & os.O_RDWR or flags & os.O_WRONLY:
                raise pyfuse3.FUSEError(errno.EACCES)

            # Create file handle with readahead buffer
            fh = self._next_fh
            self._next_fh += 1
            self._file_handles[fh] = {
                "path": path,
                "buffer_data": b"",
                "buffer_start": 0,
                "buffer_end": 0,
                "next_buffer_data": b"",
                "next_buffer_start": 0,
                "next_buffer_end": 0,
                "prefetching": False,
                "buffer_lock": trio.Lock(),
                "metrics": {
                    "start_time": None,
                    "total_net_bytes": 0,
                    "total_fetch_time": 0.0,
                    "fetch_count": 0,
                },
            }

            log.debug(f"Opened file {path} with handle {fh}")
            return pyfuse3.FileInfo(fh=fh)
        except pyfuse3.FUSEError:
            raise

    # ----- HTTP helpers (refactored out of read) -----
    def _configure_curl(self, c: pycurl.Curl, http10: bool = False, ignore_content_length: bool = False) -> None:
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
        if ignore_content_length:
            c.setopt(pycurl.IGNORE_CONTENT_LENGTH, 1)

    def _http_range_request(self, target_url: str, start: int, end: int) -> tuple[int, bytes]:
        response_buffer = io.BytesIO()
        header_buffer = io.BytesIO()
        curl_handle = pycurl.Curl()
        try:
            self._configure_curl(curl_handle, http10=False, ignore_content_length=False)
            curl_handle.setopt(pycurl.URL, target_url)
            curl_handle.setopt(pycurl.HTTPHEADER, [
                f'Range: bytes={start}-{end}',
                'Accept-Encoding: identity',
                'Connection: keep-alive',
            ])
            curl_handle.setopt(pycurl.WRITEDATA, response_buffer)
            curl_handle.setopt(pycurl.WRITEHEADER, header_buffer)
            curl_handle.perform()
            status_code = int(curl_handle.getinfo(pycurl.RESPONSE_CODE))
            return status_code, response_buffer.getvalue()
        except pycurl.error as e:
            headers = header_buffer.getvalue().decode('utf-8', errors='replace')
            log.warning(f"pycurl error for {target_url} range {start}-{end}: {e}")
            log.debug(f"Response headers: {headers}")
            # Content-Length workaround
            if e.args and e.args[0] == 8:
                response_buffer2 = io.BytesIO()
                header_buffer2 = io.BytesIO()
                curl_handle2 = pycurl.Curl()
                try:
                    self._configure_curl(curl_handle2, http10=True, ignore_content_length=True)
                    curl_handle2.setopt(pycurl.URL, target_url)
                    curl_handle2.setopt(pycurl.HTTPHEADER, [
                        f'Range: bytes={start}-{end}',
                        'Accept-Encoding: identity',
                        'Connection: close',
                    ])
                    curl_handle2.setopt(pycurl.WRITEDATA, response_buffer2)
                    curl_handle2.setopt(pycurl.WRITEHEADER, header_buffer2)
                    curl_handle2.perform()
                    status_code = int(curl_handle2.getinfo(pycurl.RESPONSE_CODE))
                    log.info(f"Content-Length workaround successful for {target_url}")
                    return status_code, response_buffer2.getvalue()
                finally:
                    try:
                        curl_handle2.close()
                    except Exception:
                        pass
            raise
        finally:
            try:
                curl_handle.close()
            except Exception:
                pass

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
                    return content
                elif status == 200 and start == 0:
                    # Full body returned; slice to requested range length
                    return content[:(end - start + 1)]
                elif status == 416:
                    # Requested range not satisfiable; treat as EOF
                    return b''
                elif status in (403, 404, 410) or (status == 200 and start > 0):
                    # Likely URL expired or server quirk; refresh and retry once
                    if attempt < max_attempts - 1:
                        self._url_cache.pop(path, None)
                        fresh_url = self.db.get_download_url(path, for_http=True, force_resolve=True)
                        if fresh_url:
                            self._url_cache[path] = {'url': fresh_url, 'timestamp': time.time()}
                            target_url = fresh_url
                            # small backoff before retry
                            if attempt < len(backoffs):
                                await trio.sleep(backoffs[attempt])
                            continue
                # Unexpected status
                raise pyfuse3.FUSEError(errno.EIO)
            except pycurl.error as e:
                log.warning(f"HTTP request failed (attempt {attempt + 1}/{max_attempts}) for {path}: {e}")
                # Try refresh URL and backoff before next attempt
                if attempt < max_attempts - 1:
                    self._url_cache.pop(path, None)
                    fresh_url = self.db.get_download_url(path, for_http=True, force_resolve=True)
                    if fresh_url and fresh_url != target_url:
                        self._url_cache[path] = {'url': fresh_url, 'timestamp': time.time()}
                        target_url = fresh_url
                        log.info(f"Retrying with fresh URL for {path}")
                    if attempt < len(backoffs):
                        await trio.sleep(backoffs[attempt])
                    continue
                raise pyfuse3.FUSEError(errno.EIO)
        raise pyfuse3.FUSEError(errno.EIO)

    async def _prefetch_task(self, path: str, url: str, fh: int, start: int, end: int) -> None:
        try:
            data: bytes = await self._fetch_data_block(path, url, start, end)
            handle_info = self._file_handles.get(fh)
            if not handle_info:
                return
            buffer_lock: trio.Lock = handle_info.get("buffer_lock") or trio.Lock()
            async with buffer_lock:
                # If current buffer already advanced past this range, drop it
                if int(handle_info.get("buffer_end", 0)) > start:
                    handle_info["prefetching"] = False
                    self._file_handles[fh] = handle_info
                    return
                handle_info["next_buffer_start"] = start
                handle_info["next_buffer_data"] = data
                handle_info["next_buffer_end"] = start + len(data)
                handle_info["prefetching"] = False
                self._file_handles[fh] = handle_info
        except Exception as e:
            log.debug(f"Prefetch failed for {path} @ {start}-{end}: {e}")
            handle_info = self._file_handles.get(fh)
            if handle_info is not None:
                handle_info["prefetching"] = False
                self._file_handles[fh] = handle_info


    async def read(self, fh: int, off: int, size: int) -> bytes:
        """Read data from a file using HTTP range requests."""
        try:
            # Get file handle info
            handle_info = self._file_handles.get(fh) or {}
            if not handle_info:
                raise pyfuse3.FUSEError(errno.EBADF)

            path = handle_info.get("path") or ""
            if not path:
                raise pyfuse3.FUSEError(errno.EBADF)

            file_info = self.db.get_entry(path)
            if file_info is None or file_info.get("is_directory"):
                raise pyfuse3.FUSEError(errno.ENOENT)

            file_size_raw = file_info.get('size')
            file_size = int(file_size_raw) if file_size_raw is not None else None

            # Guard: pyfuse3 may call read with size=0
            if size == 0:
                return b""


            # Resolve URL with caching
            import time
            now = time.time()
            cached_url_info = self._url_cache.get(path)
            url = None

            if not cached_url_info or (now - float(cached_url_info.get('timestamp', 0))) > self.url_cache_ttl:
                # Get fresh unrestricted URL for HTTP requests
                url = self.db.get_download_url(path, for_http=True, force_resolve=False)
                if not url:
                    raise pyfuse3.FUSEError(errno.ENOENT)
                self._url_cache[path] = {'url': url, 'timestamp': now}
                log.debug(f"Refreshed URL cache for {path}")
            else:
                url = str(cached_url_info.get('url'))

            # Concurrency controls: per-path network semaphore and per-handle buffer lock
            network_sem = self._request_semaphores.setdefault(path, trio.Semaphore(self.max_concurrent_fetches))
            buffer_lock = handle_info.setdefault("buffer_lock", trio.Lock())


            # Readahead buffer logic with limited parallel fetch
            # First, try serving from buffer under buffer_lock
            async with buffer_lock:
                buffer_data: bytes = handle_info.get("buffer_data", b"")
                buffer_start: int = int(handle_info.get("buffer_start", 0))
                buffer_end: int = int(handle_info.get("buffer_end", 0))

                # Calculate request range
                request_start = off
                request_end = off + size - 1 if size > 0 else off
                if file_size is not None:
                    request_end = min(request_end, file_size - 1)

                # Check if request is fully satisfied by current buffer
                if (buffer_data and request_start >= buffer_start and
                    (request_end + 1) <= buffer_end):
                    # Serve from buffer
                    buffer_offset = request_start - buffer_start
                    data_length = request_end - request_start + 1
                    return buffer_data[buffer_offset:buffer_offset + data_length]
                # If request fits entirely in prefetched next buffer, swap and serve
                nb_start: int = int(handle_info.get("next_buffer_start", 0))
                nb_end: int = int(handle_info.get("next_buffer_end", 0))
                if nb_end > nb_start and request_start >= nb_start and (request_end + 1) <= nb_end:
                    nb_data: bytes = handle_info.get("next_buffer_data", b"")
                    handle_info["buffer_start"] = nb_start
                    handle_info["buffer_data"] = nb_data
                    handle_info["buffer_end"] = nb_end
                    handle_info["next_buffer_data"] = b""
                    handle_info["next_buffer_start"] = 0
                    handle_info["next_buffer_end"] = 0
                    self._file_handles[fh] = handle_info
                    buffer_offset = request_start - nb_start
                    data_length = request_end - request_start + 1
                    return nb_data[buffer_offset:buffer_offset + data_length]



                # Need to fetch new data
                chunk = self.readahead_size
                probe_chunk = 2 * 1024 * 1024  # 2 MiB for tiny probe reads
                contiguous = (request_start == buffer_end)
                is_small_probe = (size <= 256 * 1024)
                is_empty_buffer = (buffer_end == 0) and (not buffer_data)

                if contiguous:
                    # Continue from buffer_end to avoid gaps; small first-read stays tiny
                    fetch_start = buffer_end
                    desired_len = probe_chunk if (is_empty_buffer and is_small_probe) else chunk
                else:
                    if is_small_probe:
                        # For random tiny probes, fetch starting exactly at the requested offset
                        fetch_start = request_start
                        desired_len = max(probe_chunk, size)
                    else:
                        # Aligned full-chunk fetch for general random access
                        fetch_start = (request_start // chunk) * chunk
                        desired_len = chunk

                fetch_end = fetch_start + desired_len - 1
                if file_size is not None:
                    fetch_end = min(fetch_end, file_size - 1)

                # In-flight de-duplication per fetch_start
                inflight = handle_info.setdefault("inflight", {})
                wait_event = inflight.get(fetch_start)
                if wait_event is None:
                    wait_event = inflight[fetch_start] = trio.Event()
                    leader = True
                else:
                    leader = False

            # If follower, wait for leader to finish this chunk and serve from buffer
            if not leader:
                await wait_event.wait()
                async with buffer_lock:
                    buffer_data: bytes = handle_info.get("buffer_data", b"")
                    buffer_start: int = int(handle_info.get("buffer_start", 0))
                    buffer_end_local: int = int(handle_info.get("buffer_end", 0))
                    # Verify coverage after leader finished; if covered, serve from buffer
                    if (buffer_data and request_start >= buffer_start and (request_end + 1) <= buffer_end_local):
                        buffer_offset = request_start - buffer_start
                        data_length = request_end - request_start + 1
                        return buffer_data[buffer_offset:buffer_offset + data_length]
                    # Not covered (leader failed or short-read far from our range); compute fallback fetch
                    fallback_fetch_start = buffer_end_local if request_start == buffer_end_local else ((request_start // chunk) * chunk)
                    fallback_fetch_end = fallback_fetch_start + chunk - 1
                    if file_size is not None:
                        fallback_fetch_end = min(fallback_fetch_end, file_size - 1)
                # Fallback fetch (acts independently of inflight to recover)
                fb_fetch_started = time.monotonic()
                async with network_sem:
                    fb_data = await self._fetch_data_block(path, url, fallback_fetch_start, fallback_fetch_end)
                fb_elapsed = max(time.monotonic() - fb_fetch_started, 1e-6)
                # Update buffer and return
                async with buffer_lock:
                    handle_info["buffer_start"] = fallback_fetch_start
                    handle_info["buffer_data"] = fb_data
                    handle_info["buffer_end"] = fallback_fetch_start + len(fb_data)
                    self._file_handles[fh] = handle_info
                    buffer_offset = request_start - fallback_fetch_start
                    data_length = request_end - request_start + 1
                    return fb_data[buffer_offset:buffer_offset + data_length]

            # Leader path: perform network fetch outside buffer lock, with cleanup on error
            evt_signaled = False
            try:
                fetch_started = time.monotonic()
                async with network_sem:
                    fetched_data = await self._fetch_data_block(path, url, fetch_start, fetch_end)
                fetch_elapsed = max(time.monotonic() - fetch_started, 1e-6)
                bytes_fetched = len(fetched_data)

                # Update per-handle throughput metrics and log
                metrics = handle_info.get("metrics") or {"start_time": None, "total_net_bytes": 0, "total_fetch_time": 0.0, "fetch_count": 0}
                if not metrics.get("start_time"):
                    metrics["start_time"] = time.monotonic()
                metrics["total_net_bytes"] += bytes_fetched
                metrics["total_fetch_time"] += fetch_elapsed
                metrics["fetch_count"] = int(metrics.get("fetch_count", 0)) + 1
                inst_mbps = (bytes_fetched * 8.0) / (fetch_elapsed * 1_000_000.0)
                avg_mbps = (metrics["total_net_bytes"] * 8.0) / (max(metrics["total_fetch_time"], 1e-6) * 1_000_000.0)
                if avg_mbps < 50.0 and metrics["fetch_count"] >= 3 and not metrics.get("warned_low", False):
                    log.warning(f"Low throughput for {path}: avg={avg_mbps:.1f} Mbps over {metrics['fetch_count']} fetches")
                    metrics["warned_low"] = True
                log.debug(f"THR path={path} fetched={bytes_fetched/1048576.0:.2f} MiB in {fetch_elapsed:.2f}s => {inst_mbps:.1f} Mbps avg={avg_mbps:.1f} Mbps off={fetch_start}-{fetch_end}")
                handle_info["metrics"] = metrics

                # Update buffer in handle and signal followers
                async with buffer_lock:
                    handle_info["buffer_start"] = fetch_start
                    handle_info["buffer_data"] = fetched_data
                    handle_info["buffer_end"] = fetch_start + len(fetched_data)
                    self._file_handles[fh] = handle_info
                    inflight = handle_info.setdefault("inflight", {})
                    evt = inflight.pop(fetch_start, None)
                    if evt:
                        evt.set()
                        evt_signaled = True

                    buffer_offset = request_start - fetch_start
                    data_length = request_end - request_start + 1
                    result = fetched_data[buffer_offset:buffer_offset + data_length]
                # Consider background prefetch (fire-and-forget)
                try:
                    async with buffer_lock:
                        prefetch_start = int(handle_info.get("buffer_end", 0))
                        nb_have = int(handle_info.get("next_buffer_end", 0)) > int(handle_info.get("next_buffer_start", 0))
                        # Skip prefetch if recent seek far away (heuristic): if request was not at buffer_end
                        seek_far = (request_start != fetch_start) and (abs(request_start - fetch_start) > (2 * chunk))
                        can_prefetch = ((file_size is None) or (prefetch_start < file_size)) and not handle_info.get("prefetching", False) and not nb_have and not seek_far
                        if can_prefetch:
                            prefetch_end = prefetch_start + self.readahead_size - 1
                            if file_size is not None:
                                prefetch_end = min(prefetch_end, file_size - 1)
                            handle_info["prefetching"] = True
                            self._file_handles[fh] = handle_info
                            trio.lowlevel.spawn_system_task(self._prefetch_task, path, url, fh, prefetch_start, prefetch_end)
                except Exception:
                    pass

                log.debug(f"Read {len(result)} bytes from {path} at offset {off}")
                return result
            finally:
                if not evt_signaled:
                    # Ensure we never leave followers waiting indefinitely
                    try:
                        async with buffer_lock:
                            inflight = handle_info.setdefault("inflight", {})
                            evt = inflight.pop(fetch_start, None)
                            if evt:
                                evt.set()
                    except Exception:
                        pass

        except pyfuse3.FUSEError:
            raise
        except Exception as ex:
            log.exception("read error fh=%s: %s", fh, ex)
            raise pyfuse3.FUSEError(errno.EIO)

    async def release(self, fh: int):
        """Release/close a file handle."""
        try:
            handle_info = self._file_handles.pop(fh, None)
            if handle_info:
                # Clean up curl handle if it exists
                curl_handle = handle_info.get('curl_handle')
                if curl_handle:
                    try:
                        curl_handle.close()
                        log.debug(f"Closed curl handle for fh={fh}")
                    except Exception as e:
                        log.warning(f"Error closing curl handle for fh={fh}: {e}")

                log.debug(f"Released file handle {fh}")
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
        """Check file access permissions."""
        try:
            import os
            # Read-only filesystem: allow read/execute, deny write
            if mode & os.W_OK:
                raise pyfuse3.FUSEError(errno.EACCES)

            # Check if file/directory exists
            path = self._get_path_from_inode(inode)
            if not self.db.exists(path):
                raise pyfuse3.FUSEError(errno.ENOENT)

            return None
        except pyfuse3.FUSEError:
            raise
        except Exception as ex:
            log.exception("access error inode=%s mode=%s: %s", inode, mode, ex)
            raise pyfuse3.FUSEError(errno.EIO)

    # Mutating operations (unlink, rmdir, rename)
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
