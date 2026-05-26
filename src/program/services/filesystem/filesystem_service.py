"""Filesystem Service for Riven

This service provides a interface for filesystem operations
using the RivenVFS implementation.
"""

import time
from typing import TYPE_CHECKING, Any
from loguru import logger

from program.services.filesystem.fuse_available import is_fuse_available
from program.services.filesystem.common_utils import get_items_to_update
from program.services.downloaders import Downloader
from program.core.runner import MediaItemGenerator, Runner, RunnerResult
from program.settings.models import FilesystemModel

if TYPE_CHECKING:
    from program.media.item import MediaItem


class FilesystemService(Runner[FilesystemModel]):
    """Filesystem service for VFS-only mode"""

    # Class-level singleton that survives across service reinits triggered by settings changes.
    #
    # Every call to Program.initialize_services() (which happens on every settings save)
    # creates a new FilesystemService instance but never calls close() on the old one,
    # so the underlying FUSE/mock VFS stays alive and mounted. By restoring the existing
    # VFS instance here we skip the expensive remount + full-DB sync and instead just
    # call sync(), which is a no-op when library profiles are unchanged.
    _shared_vfs: Any = None

    def __init__(self, downloader: Downloader):
        super().__init__()

        from program.settings import settings_manager

        self.settings = settings_manager.settings.filesystem
        # Restore the shared VFS — avoids full remount on each settings-triggered reinit
        self.riven_vfs = FilesystemService._shared_vfs
        self.downloader = downloader
        self._initialize_rivenvfs(downloader)

    @classmethod
    def get_key(cls) -> str:
        return "filesystem"

    @property
    def uses_mock_vfs(self) -> bool:
        """True when pyfuse3 is unavailable and the in-memory inventory backend is active."""

        if self.riven_vfs is None:
            return False
        from program.services.filesystem.vfs.mock_rivenvfs import MockRivenVFS

        return isinstance(self.riven_vfs, MockRivenVFS)

    @property
    def enabled(self) -> bool:
        if not is_fuse_available():
            return False
        return super().enabled

    @property
    def initialized(self) -> bool:
        if not is_fuse_available():
            return True
        return self.validate()

    @initialized.setter
    def initialized(self, value: bool) -> None:
        pass

    def _initialize_rivenvfs(self, downloader: Downloader):
        """Initialize or reuse RivenVFS.

        On first call: mounts FUSE and runs a full VFS sync (~seconds to minutes for
        large libraries).

        On subsequent calls (settings change reinit): if the existing VFS is already
        mounted (restored from _shared_vfs), we skip the full mount and only run
        sync(), which is itself a no-op when library profiles are unchanged.
        """
        t0 = time.monotonic()

        if not is_fuse_available():
            from .vfs.mock_rivenvfs import MockRivenVFS

            if self.riven_vfs and self.riven_vfs.mounted:
                logger.info("FilesystemService: reusing existing MockRivenVFS, syncing")
                t_sync = time.monotonic()
                self.riven_vfs.sync()
                logger.info(
                    "FilesystemService: MockRivenVFS sync took {:.2f}s",
                    time.monotonic() - t_sync,
                )
                FilesystemService._shared_vfs = self.riven_vfs
                return

            logger.info(
                "pyfuse3 is not installed; VFS (FUSE) is disabled. "
                "Using in-memory mount inventory only (install the `fuse` extra for FUSE).",
            )
            self.riven_vfs = MockRivenVFS(
                mountpoint=str(self.settings.mount_path),
                downloader=downloader,
            )
            FilesystemService._shared_vfs = self.riven_vfs
            logger.info(
                "FilesystemService: MockRivenVFS ready in {:.2f}s", time.monotonic() - t0
            )
            return

        try:
            from .vfs import RivenVFS

            if self.riven_vfs and self.riven_vfs.mounted:
                logger.info(
                    "FilesystemService: reusing mounted RivenVFS (skipping remount), syncing"
                )
                t_sync = time.monotonic()
                self.riven_vfs.sync()
                logger.info(
                    "FilesystemService: RivenVFS sync took {:.2f}s (total {:.2f}s)",
                    time.monotonic() - t_sync, time.monotonic() - t0,
                )
                FilesystemService._shared_vfs = self.riven_vfs
                return

            logger.info("FilesystemService: mounting new RivenVFS")
            self.riven_vfs = RivenVFS(
                mountpoint=str(self.settings.mount_path),
                downloader=downloader,
            )
            FilesystemService._shared_vfs = self.riven_vfs
            logger.info(
                "FilesystemService: RivenVFS mounted and synced in {:.2f}s",
                time.monotonic() - t0,
            )

        except ImportError as e:
            logger.error(f"Failed to import RivenVFS: {e}")
            logger.warning("RivenVFS initialization failed")
        except Exception as e:
            logger.error(f"Failed to initialize RivenVFS: {e}")
            logger.warning("RivenVFS initialization failed")

    def run(self, item: "MediaItem") -> MediaItemGenerator:
        from program.managers.pipeline_activity import report_pipeline_activity_for_item

        report_pipeline_activity_for_item(item, "Creating library symlinks")

        if not self.riven_vfs:
            logger.warning(
                "RivenVFS not initialized (FUSE unavailable and mock VFS failed to attach); "
                "skipping filesystem step for this item.",
            )
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

        Clears the class-level _shared_vfs singleton so the next FilesystemService
        instance performs a full fresh mount rather than trying to reuse a closed VFS.
        """
        try:
            if self.riven_vfs:
                self.riven_vfs.close()
        except Exception as e:
            logger.error(f"Error closing RivenVFS: {e}")
        finally:
            self.riven_vfs = None
            FilesystemService._shared_vfs = None

        from program.utils.streaming_http import close_streaming_http_sync

        close_streaming_http_sync()

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
