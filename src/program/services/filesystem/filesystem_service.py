"""Filesystem Service for Riven

This service provides a interface for filesystem operations
using the RivenVFS implementation.
"""

from typing import TYPE_CHECKING
from kink import di
from loguru import logger

from program.services.filesystem.common_utils import get_items_to_update
from program.services.downloaders import Downloader
from program.core.runner import MediaItemGenerator, Runner, RunnerResult
from program.settings.models import FilesystemModel
from program.utils.nursery import Nursery

if TYPE_CHECKING:
    from program.media.item import MediaItem


class FilesystemService(Runner[FilesystemModel]):
    """Filesystem service for VFS-only mode"""

    def __init__(self, downloader: Downloader):
        super().__init__()

        from program.settings import settings_manager

        # Use filesystem settings
        self.settings = settings_manager.settings.filesystem
        self.riven_vfs = None
        self.downloader = downloader  # Store for potential reinit

        di[Nursery].nursery.start_soon(
            lambda: self._initialize_rivenvfs(
                downloader,
            ),
        )

    @classmethod
    def get_key(cls) -> str:
        return "filesystem"

    async def _initialize_rivenvfs(self, downloader: Downloader):
        """Initialize or synchronize RivenVFS"""

        try:
            from .vfs import RivenVFS

            # If VFS already exists and is mounted, synchronize it with current settings
            if self.riven_vfs and self.riven_vfs.mounted:
                logger.info("Synchronizing existing RivenVFS with library profiles")
                self.riven_vfs.sync()
                return

            # Create new VFS instance
            logger.info("Initializing RivenVFS")

            self.riven_vfs = RivenVFS(
                mountpoint=str(self.settings.mount_path),
                downloader=downloader,
            )

            await self.riven_vfs.run()

        except ImportError as e:
            logger.error(f"Failed to import RivenVFS: {e}")
            logger.warning("RivenVFS initialization failed")
        except Exception as e:
            logger.error(f"Failed to initialize RivenVFS: {e}")
            logger.warning("RivenVFS initialization failed")

    def run(self, item: "MediaItem") -> MediaItemGenerator:
        if not self.riven_vfs:
            logger.error("RivenVFS not initialized")
            yield RunnerResult(media_items=[item])
            return

        # Expand parent items (show/season) to leaf items (episodes/movies)
        items_to_process = get_items_to_update(item)
        if not items_to_process:
            logger.debug(f"No items to process for {item.log_string}")
            yield RunnerResult(media_items=[item])
            return

        # Process each episode/movie
        for episode_or_movie in items_to_process:
            success = self.riven_vfs.add(episode_or_movie)

            if not success:
                logger.error(f"Failed to register {item.log_string} with RivenVFS")
                continue

            logger.debug(f"Registered {item.log_string} with RivenVFS")

        logger.info(f"Filesystem processing complete for {item.log_string}")

        # Yield the original item for state transition
        yield RunnerResult(media_items=[item])

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
        if not self.riven_vfs.mounted:
            logger.error("FilesystemService: RivenVFS not mounted")
            return False

        return True

    @property
    def initialized(self) -> bool:
        """Check if the filesystem service is properly initialized"""
        return self.validate()

    @initialized.setter
    def initialized(self, value: bool) -> None:
        # Setting initialized is a no-op
        pass
