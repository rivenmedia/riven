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
        self._initialize_rivenvfs(downloader)

    def _initialize_rivenvfs(self, downloader: Downloader):
        """Initialize RivenVFS"""
        try:
            from .vfs import RivenVFS

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
        """Process a MediaItem using RivenVFS"""
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

        # Yield the original item for state transition
        yield item

    def _process_single_item(self, item: MediaItem) -> None:
        """Process a single episode or movie item by registering it with FUSE"""
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

            # Register the file with FUSE
            if self.riven_vfs.register_existing_file(filesystem_entry.path):
                filesystem_entry.available_in_vfs = True
                logger.info(f"Added {item.log_string} to RivenVFS at {filesystem_entry.path}")
            else:
                logger.error(f"Failed to register {item.log_string} with FUSE")

        except Exception as e:
            logger.error(f"Failed to process {item.log_string} with RivenVFS: {e}")

    def close(self):
        """Clean up filesystem resources"""
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
        - mount path is set and accessible
        - RivenVFS is initialized and mounted
        """
        try:
            from pathlib import Path
            mount = Path(str(self.settings.mount_path))
            if not str(mount):
                logger.error("FilesystemService: mount_path is empty")
                return False
            # Ensure mount path directory exists
            mount.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            logger.error(f"FilesystemService: invalid mount_path '{self.settings.mount_path}': {e}")
            return False

        if not self.riven_vfs:
            logger.error("FilesystemService: RivenVFS not initialized")
            return False

        # RivenVFS maintains an internal mounted flag
        if not getattr(self.riven_vfs, "_mounted", False):
            logger.error("FilesystemService: RivenVFS not mounted")
            return False

        return True

    def reinitialize(self) -> bool:
        """Reinitialize the underlying RivenVFS with current settings."""
        try:
            self.close()
            self._initialize_rivenvfs()
            return self.validate()
        except Exception as e:
            logger.error(f"FilesystemService: reinitialize failed: {e}")
            return False

    @property
    def initialized(self) -> bool:
        """Check if the filesystem service is properly initialized"""
        return self.validate()
