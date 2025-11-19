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

        # Expand parent items (show/season) to leaf items (episodes/movies)
        items_to_process = get_items_to_update(item)
        if not items_to_process:
            logger.debug(f"No items to process for {item.log_string}")
            yield item
            return

        # Get MediaAnalysisService once before the loop
        from program.program import riven
        from program.services.post_processing import PostProcessing
        from program.services.post_processing.media_analysis import MediaAnalysisService

        post_processing = riven.services.get(PostProcessing)
        media_analysis = post_processing.services.get(MediaAnalysisService) if post_processing else None

        # Identify items that need analysis (avoid duplicate should_submit calls)
        items_needing_analysis_set = set()
        if media_analysis:
            items_needing_analysis_set = {
                i for i in items_to_process
                if media_analysis.should_submit(i)
            }

        if items_needing_analysis_set:
            logger.info(
                f"Starting media analysis for {item.log_string} "
                f"({len(items_needing_analysis_set)} file{'s' if len(items_needing_analysis_set) != 1 else ''})"
            )

        analyzed_count = 0

        # Process each episode/movie
        for episode_or_movie in items_to_process:
            success = self.riven_vfs.add(episode_or_movie)

            if not success:
                logger.error(f"Failed to register {item.log_string} with RivenVFS")
                continue

            logger.debug(f"Registered {item.log_string} with RivenVFS")

            # Run media analysis immediately after VFS registration succeeds
            # This ensures metadata is available BEFORE Plex/Emby/Jellyfin are notified
            if episode_or_movie in items_needing_analysis_set:
                try:
                    media_analysis.run(episode_or_movie)
                    analyzed_count += 1
                    logger.debug(f"Media analysis completed for {episode_or_movie.log_string}")
                except Exception as e:
                    logger.warning(f"Media analysis failed for {episode_or_movie.log_string}: {e}")

                # Check if item was reset due to dead link during media analysis
                # When a dead link is detected, the item's filesystem_entry is cleared
                # and a re-download is triggered. Skip this item and let the new download handle it.
                if not episode_or_movie.filesystem_entry:
                    logger.info(
                        f"Item {episode_or_movie.log_string} was reset during media analysis "
                        "(dead link detected). New download will handle media analysis and notification."
                    )
                    continue

        logger.info(f"Filesystem processing complete for {item.log_string}")

        # Yield the original item for state transition
        yield item

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
