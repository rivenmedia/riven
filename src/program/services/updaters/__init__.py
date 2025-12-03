"""Updater module"""

from collections.abc import AsyncGenerator
import os

from loguru import logger

from program.media.item import Episode, MediaItem, Movie, Season, Show
from program.services.updaters.emby import EmbyUpdater
from program.services.updaters.jellyfin import JellyfinUpdater
from program.services.updaters.plex import PlexUpdater
from program.settings import settings_manager
from program.core.runner import Runner, RunnerResult
from program.services.updaters.base import BaseUpdater


class Updater(Runner[None, BaseUpdater]):
    """
    Main updater service that coordinates multiple media server updaters.

    This service manages multiple updater implementations (Plex, Emby, Jellyfin)
    and triggers media server refreshes for items.
    """

    def __init__(self):
        self.library_path = settings_manager.settings.updaters.library_path
        self.services = {
            PlexUpdater: PlexUpdater(),
            JellyfinUpdater: JellyfinUpdater(),
            EmbyUpdater: EmbyUpdater(),
        }
        self.initialized = self.validate()

    def validate(self) -> bool:
        """Validate that at least one updater service is initialized."""

        initialized_services = [
            service for service in self.services.values() if service.initialized
        ]

        return len(initialized_services) > 0

    async def run(self, item: MediaItem) -> AsyncGenerator[RunnerResult[MediaItem]]:
        """
        Update media servers for the given item.

        Extracts all filesystem paths (base + library profiles) from the item
        and triggers a refresh in all initialized media servers.

        For movies: refreshes parent directory (e.g., /movies/Movie Name (2020)/)
        For shows: refreshes parent's parent directory (e.g., /shows/Show Name/)

        Library profiles: Also refreshes profile paths (e.g., /kids/movies/Movie Name/)

        Args:
            item: MediaItem to update

        Yields:
            MediaItem: The item after processing
        """

        logger.debug(f"Starting update process for {item.log_string}")
        items = self.get_items_to_update(item)
        refreshed_paths = set[str]()  # Track refreshed paths to avoid duplicates

        for _item in items:
            # Get all VFS paths from the entry's helper method
            media_entry = _item.media_entry

            if not media_entry:
                logger.debug(
                    f"No filesystem entry for {_item.log_string}; skipping updater"
                )
                continue

            try:
                all_vfs_paths = media_entry.get_all_vfs_paths()
            except Exception as e:
                logger.error(f"Failed to get VFS paths for {_item.log_string}: {e}")
                continue

            if not all_vfs_paths:
                logger.debug(f"No VFS paths for {_item.log_string}; skipping updater")
                continue

            logger.debug(f"Updating {_item.log_string} at {len(all_vfs_paths)} path(s)")

            for vfs_path in all_vfs_paths:
                # Build absolute path to the file
                abs_path = os.path.join(self.library_path, vfs_path.lstrip("/"))
                refresh_path = os.path.dirname(abs_path)

                # Refresh the path in all services (skip if already refreshed)
                if refresh_path not in refreshed_paths:
                    if self.refresh_path(refresh_path):
                        refreshed_paths.add(refresh_path)

            _item.updated = True
            logger.debug(f"Updated {_item.log_string}")

        logger.info(
            f"Updated {item.log_string} ({len(refreshed_paths)} unique paths refreshed)"
        )

        yield RunnerResult(media_items=[item])

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

        return success

    def get_items_to_update(self, item: MediaItem) -> list[MediaItem]:
        """Get the list of files to update for the given item."""

        if isinstance(item, (Movie, Episode)):
            return [item]

        if isinstance(item, Show):
            return [
                e
                for season in item.seasons
                for e in season.episodes
                if e.available_in_vfs
            ]

        if isinstance(item, Season):
            return [e for e in item.episodes if e.available_in_vfs]

        return []
