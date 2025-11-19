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
                self.riven_vfs.sync()
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

        Expands parent items (shows/seasons) into leaf items (episodes/movies), processes each leaf entry via add(), and yields the original input item for downstream state transitions. If RivenVFS is not available or there are no leaf items to process, the original item is yielded unchanged.

        Parameters:
            item (MediaItem): The media item (episode, movie, season, or show) to process.

        Returns:
            Generator[MediaItem, None, None]: Yields the original `item` once processing completes (or immediately if processing cannot proceed).
        """
        if not self.riven_vfs:
            logger.error("RivenVFS not initialized")
            yield item
            return

        # Check if VFS is mounted before processing
        if not getattr(self.riven_vfs, "_mounted", False):
            logger.error(
                f"Cannot process {item.log_string}: VFS not mounted. "
                "Skipping to prevent incomplete processing."
            )
            # Don't yield - this prevents notification of unprocessed items
            return

        # Expand parent items (show/season) to leaf items (episodes/movies)
        items_to_process = get_items_to_update(item)
        if not items_to_process:
            logger.debug(f"No items to process for {item.log_string}")
            yield item
            return

        # Get FileWarmupService for validating accessibility
        from program.services.filesystem.file_warmup import FileWarmupService

        warmup_service = FileWarmupService()

        # Identify items that need warmup (avoid duplicate should_submit calls)
        items_needing_warmup = [
            i for i in items_to_process
            if warmup_service.should_submit(i)
        ]

        if items_needing_warmup:
            logger.info(
                f"Starting file warmup for {item.log_string} "
                f"({len(items_needing_warmup)} file{'s' if len(items_needing_warmup) != 1 else ''})"
            )

        # Process each episode/movie
        for episode_or_movie in items_to_process:
            success = self.riven_vfs.add(episode_or_movie)

            if not success:
                logger.error(f"Failed to register {item.log_string} with RivenVFS")
                continue

            logger.debug(f"Registered {item.log_string} with RivenVFS")

            # Run file warmup immediately after VFS registration succeeds
            # This validates link accessibility BEFORE media servers are notified
            if episode_or_movie in items_needing_warmup:
                try:
                    success = warmup_service.run(episode_or_movie)
                    if not success:
                        logger.error(
                            f"File warmup failed for {episode_or_movie.log_string}. "
                            "Link may be dead. Item will be reset for re-download."
                        )
                        # Reset item to trigger re-download
                        self._reset_item_for_dead_link(episode_or_movie)
                        continue

                    logger.debug(f"File warmup completed for {episode_or_movie.log_string}")
                except Exception as e:
                    logger.error(f"File warmup error for {episode_or_movie.log_string}: {e}")
                    # Reset item and skip notification
                    self._reset_item_for_dead_link(episode_or_movie)
                    continue

                # Check if item was reset due to dead link during warmup
                # When a dead link is detected, the item's filesystem_entry is cleared
                # and a re-download is triggered. Skip this item and let the new download handle it.
                if not episode_or_movie.filesystem_entry:
                    logger.info(
                        f"Item {episode_or_movie.log_string} was reset during file warmup "
                        "(dead link detected). New download will handle notification."
                    )
                    continue

        logger.info(f"Filesystem processing complete for {item.log_string}")

        # Yield the original item for state transition
        yield item

    def _reset_item_for_dead_link(self, item: MediaItem):
        """
        Reset item when a dead link is detected.

        Blacklists the current stream and resets the item to trigger re-download.

        Args:
            item: MediaItem with dead link
        """
        try:
            from program.db.db_functions import apply_item_mutation
            from program.program import riven

            def mutation(i: MediaItem, s):
                i.blacklist_active_stream()
                i.reset()

            apply_item_mutation(
                program=riven,
                item=item,
                mutation_fn=mutation,
            )

            logger.info(
                f"Reset {item.log_string} due to dead link. "
                "Item will be re-downloaded with different stream."
            )
        except Exception as e:
            logger.error(f"Failed to reset {item.log_string}: {e}")

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
