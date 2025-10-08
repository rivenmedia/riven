"""
Filesystem Service for Riven.

This service provides the interface for filesystem operations using RivenVFS.

Key features:
- Registers downloaded MediaEntry files in RivenVFS
- Manages FUSE mount lifecycle
- Handles VFS path registration and invalidation
- Transitions MediaEntry state to Available when registered

The FilesystemService processes MediaEntry objects (not MediaItem) since each
profile can have different files/paths.
"""
from pathlib import Path
from typing import Generator
from loguru import logger

from program.media.media_entry import MediaEntry
from program.settings.manager import settings_manager
from program.services.downloaders import Downloader
from .vfs import RivenVFS



class FilesystemService:
    """
    Filesystem service for VFS-only mode.

    Manages RivenVFS initialization and file registration. Processes MediaEntry
    objects by registering their files in the FUSE filesystem, making them
    available to media servers.

    Attributes:
        key: Service identifier ("filesystem").
        settings: Filesystem settings from settings_manager.
        riven_vfs: RivenVFS instance for FUSE operations.
    """

    def __init__(self, downloader: Downloader):
        """
        Initialize the FilesystemService.

        Args:
            downloader: Downloader instance for VFS to fetch files.
        """
        # Service key matches settings category name for reinitialization logic
        self.key = "filesystem"
        # Use filesystem settings
        self.settings = settings_manager.settings.filesystem
        self.riven_vfs = None
        self._initialize_rivenvfs(downloader)

    def _initialize_rivenvfs(self, downloader: Downloader):
        """
        Initialize RivenVFS with current settings.

        Args:
            downloader: Downloader instance for VFS to fetch files.
        """
        try:
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
    
    def run(self, entry: MediaEntry) -> Generator[MediaEntry, None, None]:
        """
        Process a MediaEntry by registering it with the configured RivenVFS.

        Registers the entry's file in the VFS and sets available_in_vfs = True,
        which automatically transitions the entry state to Available.

        Parameters:
            entry (MediaEntry): The media entry to register in VFS.

        Returns:
            Generator[MediaEntry, None, None]: Yields the entry once processing completes.
        """
        if not self.riven_vfs:
            logger.error("RivenVFS not initialized")
            yield entry
            return

        if not entry.media_item:
            logger.error(f"MediaEntry {entry.id} has no associated MediaItem")
            yield entry
            return

        # Register the file with FUSE
        if self.riven_vfs.register_existing_file(entry.path):
            # Setting available_in_vfs = True automatically transitions state to Available
            entry.available_in_vfs = True
            logger.info(f"Registered {entry.log_string} in VFS at {entry.path} (state: {entry.state.value})")
        else:
            logger.error(f"Failed to register {entry.log_string} with FUSE")

        # Yield the entry for state transition
        yield entry

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
        """
        Validate service state and configuration.

        Checks that:
        - mount path is set and accessible
        - RivenVFS is initialized and mounted

        Returns:
            bool: True if service is valid, False otherwise.
        """
        try:
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
        """
        Reinitialize the underlying RivenVFS with current settings.

        Closes existing VFS and creates a new one with updated settings.

        Returns:
            bool: True if reinitialization succeeded, False otherwise.
        """
        try:
            self.close()
            self._initialize_rivenvfs()
            return self.validate()
        except Exception as e:
            logger.error(f"FilesystemService: reinitialize failed: {e}")
            return False

    @property
    def initialized(self) -> bool:
        """
        Check if the filesystem service is properly initialized.

        Returns:
            bool: True if service is initialized and valid, False otherwise.
        """
        return self.validate()
