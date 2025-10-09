"""Filesystem Service for Riven

This service provides a interface for filesystem operations
using the RivenVFS implementation.
"""
from typing import Generator
from loguru import logger

from program.media.item import MediaItem
from program.settings.manager import settings_manager
from program.services.filesystem.common_utils import get_items_to_update
from program.services.downloaders import Downloader



class FilesystemService:
    """Filesystem service for VFS-only mode"""

    def __init__(self, downloader: Downloader):
        # Service key matches settings category name for reinitialization logic
        self.key = "filesystem"
        # Use filesystem settings
        self.settings = settings_manager.settings.filesystem
        self.riven_vfs = None
        self.downloader = downloader  # Store for potential reinit
        self._initialize_rivenvfs(downloader)

    def _initialize_rivenvfs(self, downloader: Downloader):
        """Initialize or synchronize RivenVFS"""
        try:
            from .vfs import RivenVFS

            # If VFS already exists and is mounted, synchronize it with current settings
            if self.riven_vfs and getattr(self.riven_vfs, "_mounted", False):
                logger.info("Synchronizing existing RivenVFS with library profiles")
                self.riven_vfs.sync_library_profiles()
                return

            # Create new VFS instance
            logger.info("Initializing RivenVFS")
            self.riven_vfs = RivenVFS(
                mountpoint=str(self.settings.mount_path),
                downloader=downloader,
            )

        except ImportError as e:
            logger.error(f"Failed to import RivenVFS: {e}")
            logger.warning("RivenVFS initialization failed")
        except Exception as e:
            logger.error(f"Failed to initialize RivenVFS: {e}")
            logger.warning("RivenVFS initialization failed")
    
    def run(self, item: MediaItem) -> Generator[MediaItem, None, None]:
        """
        Process a MediaItem by registering its leaf media entries with the configured RivenVFS.
        
        Expands parent items (shows/seasons) into leaf items (episodes/movies), processes each leaf entry via _process_single_item, and yields the original input item for downstream state transitions. If RivenVFS is not available or there are no leaf items to process, the original item is yielded unchanged.
        
        Parameters:
            item (MediaItem): The media item (episode, movie, season, or show) to process.
        
        Returns:
            Generator[MediaItem, None, None]: Yields the original `item` once processing completes (or immediately if processing cannot proceed).
        """
        if not self.riven_vfs:
            logger.error("RivenVFS not initialized")
            yield item
            return

        # Expand parent items (show/season) to leaf items (episodes/movies)
        items_to_process = get_items_to_update(item)
        if not items_to_process:
            logger.debug(f"No items to process for {item.log_string}")
            yield item
            return

        # Process each episode/movie
        for episode_or_movie in items_to_process:
            self._process_single_item(episode_or_movie)
        
        logger.info(f"Filesystem processing complete for {item.log_string}")

        # Yield the original item for state transition
        yield item

    def _process_single_item(self, item: MediaItem) -> None:
        """
        Register a single media item's existing file with the RivenVFS so it becomes available in the VFS.
        
        If the item has no filesystem entry, the function does nothing. On successful registration the function sets
        `filesystem_entry.available_in_vfs = True`; on failure it leaves the entry unchanged and logs an error. Any
        exceptions raised during processing are caught and logged.
        Parameters:
            item (MediaItem): The media item whose filesystem_entry.path will be registered with RivenVFS.
        """
        try:
            # Check if item has filesystem entry
            if not item.filesystem_entry:
                logger.debug(f"No filesystem entry found for {item.log_string}")
                return

            filesystem_entry = item.filesystem_entry

            # Check if already processed (available in VFS)
            if getattr(filesystem_entry, 'available_in_vfs', False):
                logger.debug(f"Item {item.log_string} already available in VFS")
                return

            # Get all VFS paths for this entry (base path + library profile paths)
            all_paths = filesystem_entry.get_library_paths()

            # Register all paths with FUSE
            success = True
            for path in all_paths:
                if not self.riven_vfs.register_existing_file(path):
                    logger.error(f"Failed to register {item.log_string} at {path}")
                    success = False

            if success:
                filesystem_entry.available_in_vfs = True
                if len(all_paths) > 1:
                    logger.debug(f"Added {item.log_string} to RivenVFS at {len(all_paths)} paths: {all_paths}")
                else:
                    logger.debug(f"Added {item.log_string} to RivenVFS at {filesystem_entry.path}")

        except Exception as e:
            logger.error(f"Failed to process {item.log_string} with RivenVFS: {e}")

    def close(self):
        """
        Close the underlying RivenVFS and release associated resources.
        
        If a RivenVFS instance is present, attempts to close it and always sets self.riven_vfs to None. Exceptions raised while closing are logged and not propagated.
        """
        try:
            if self.riven_vfs:
                self.riven_vfs.close()
        except Exception as e:
            logger.error(f"Error closing RivenVFS: {e}")
        finally:
            self.riven_vfs = None

    def validate(self) -> bool:
        """Validate service state and configuration.
        Checks that:
        - mount path is set
        - RivenVFS is initialized and mounted

        Note: Mount directory creation is handled by RivenVFS._prepare_mountpoint()
        """
        # Check mount path is set
        if not str(self.settings.mount_path):
            logger.error("FilesystemService: mount_path is empty")
            return False

        # Check RivenVFS is initialized
        if not self.riven_vfs:
            logger.error("FilesystemService: RivenVFS not initialized")
            return False

        # Check RivenVFS is mounted
        if not getattr(self.riven_vfs, "_mounted", False):
            logger.error("FilesystemService: RivenVFS not mounted")
            return False

        return True

    @property
    def initialized(self) -> bool:
        """Check if the filesystem service is properly initialized"""
        return self.validate()
