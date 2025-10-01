"""Updater module"""
import os
from typing import Generator

from loguru import logger

from program.media.item import MediaItem
from program.services.updaters.emby import EmbyUpdater
from program.services.updaters.jellyfin import JellyfinUpdater
from program.services.updaters.plex import PlexUpdater
from program.settings.manager import settings_manager


class Updater:
    """
    Main updater service that coordinates multiple media server updaters.

    This service manages multiple updater implementations (Plex, Emby, Jellyfin)
    and triggers media server refreshes for items.
    """

    def __init__(self):
        self.key = "updater"
        self.library_path = settings_manager.settings.updaters.library_path
        self.services = {
            PlexUpdater: PlexUpdater(),
            JellyfinUpdater: JellyfinUpdater(),
            EmbyUpdater: EmbyUpdater(),
        }
        self.initialized = self.validate()

    def validate(self) -> bool:
        """Validate that at least one updater service is initialized."""
        initialized_services = [service for service in self.services.values() if service.initialized]
        return len(initialized_services) > 0

    def run(self, item: MediaItem) -> Generator[MediaItem, None, None]:
        """
        Update media servers for the given item.

        Extracts the filesystem path from the item and triggers a refresh
        in all initialized media servers.

        For movies: refreshes parent directory (e.g., /movies/Movie Name (2020)/)
        For shows: refreshes parent's parent directory (e.g., /shows/Show Name/)

        Args:
            item: MediaItem to update

        Yields:
            MediaItem: The item after processing
        """
        if not self.initialized:
            logger.debug("Updater is not initialized, skipping")
            yield item
            return

        # Get the filesystem path from the item
        fe_path = item.filesystem_entry.path if item.filesystem_entry else None
        if not fe_path:
            logger.debug(f"No filesystem path for {item.log_string}, skipping update")
            yield item
            return

        # Build absolute path to the file
        abs_path = os.path.join(self.library_path, fe_path.lstrip("/"))

        # For movies: parent directory (movie folder)
        # For shows: parent's parent directory (show folder, not season folder)
        if item.type == "movie":
            refresh_path = os.path.dirname(abs_path)
        else:  # show, season, episode
            refresh_path = os.path.dirname(os.path.dirname(abs_path))

        # Refresh the path in all services
        self.refresh_path(refresh_path)

        item.updated = True

        yield item

    def refresh_path(self, path: str) -> bool:
        """
        Refresh a specific path in all initialized media servers.

        This triggers each media server to scan/refresh the given path,
        which will add/remove/update items as needed.

        Args:
            path: Absolute path to refresh in the media servers

        Returns:
            bool: True if at least one service refreshed successfully, False otherwise
        """
        success = False
        for service in self.services.values():
            if service.initialized:
                try:
                    if service.refresh_path(path):
                        logger.debug(f"Refreshed path: {path}")
                        success = True
                except Exception as e:
                    logger.error(f"Failed to refresh path {path}: {e}")

        if not success:
            logger.debug(f"No updater service successfully refreshed path {path}")

        return success