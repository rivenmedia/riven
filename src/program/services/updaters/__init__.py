"""
Updater service for Riven.

This module coordinates media server updaters to refresh library content:
- Plex, Jellyfin, Emby

Key features:
- Multi-server support (can update multiple servers simultaneously)
- MediaEntry-based updates (profile-aware)
- Path-based refresh (triggers server scan of specific directories)
- Automatic marking of entries as updated

The Updater service processes MediaEntry objects (not MediaItem) since each
profile can have different files requiring different server updates.
"""
import os
from typing import Generator

from loguru import logger

from program.media.item import MediaItem
from program.media.media_entry import MediaEntry
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
        """
        Initialize the Updater service.

        Initializes all media server updater implementations and filters to
        only use successfully initialized ones.
        """
        self.key = "updater"
        self.library_path = settings_manager.settings.updaters.library_path
        self.services = {
            PlexUpdater: PlexUpdater(),
            JellyfinUpdater: JellyfinUpdater(),
            EmbyUpdater: EmbyUpdater(),
        }
        self.initialized = self.validate()

    def validate(self) -> bool:
        """
        Validate that at least one updater service is initialized.

        Returns:
            bool: True if at least one media server is configured, False otherwise.
        """
        initialized_services = [service for service in self.services.values() if service.initialized]
        return len(initialized_services) > 0

    def run(self, entry: MediaEntry) -> Generator[MediaEntry, None, None]:
        """
        Update media servers for a specific MediaEntry.

        This is the main entry point for the Updater service in the new MediaEntry-based architecture.
        Checks if the entry needs updating, triggers media server refresh, and marks the entry as updated.

        Args:
            entry: MediaEntry to update

        Yields:
            MediaEntry: The entry after processing
        """
        if not entry.media_item:
            logger.error(f"MediaEntry {entry.id} has no associated MediaItem")
            yield entry
            return

        logger.debug(f"Updating {entry.log_string}")

        # Build absolute path to the file
        abs_path = os.path.join(self.library_path, entry.path.lstrip("/"))
        refresh_path = os.path.dirname(abs_path)

        # Refresh the path in all services
        if self.refresh_path(refresh_path):
            logger.info(f"Refreshed media servers for {entry.log_string}")
        else:
            logger.warning(f"Failed to refresh media servers for {entry.log_string}")

        # Mark entry as updated
        entry.updated = True
        logger.debug(f"Marked {entry.log_string} as updated")

        yield entry

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
    
    def get_items_to_update(self, item: MediaItem) -> list[MediaItem]:
        """
        Get the list of leaf items (movies/episodes) to update for the given item.

        Only includes items that have at least one MediaEntry in Available state.

        Note: In the new architecture, only Movies/Episodes should reach Updater.
        Shows/Seasons are handled here for backwards compatibility but shouldn't occur.
        """
        from program.media.media_entry import MediaEntry
        from program.media.entry_state import EntryState

        def has_available_entries(media_item: MediaItem) -> bool:
            """Check if item has any MediaEntry in Available state."""
            return any(
                isinstance(e, MediaEntry) and e.state == EntryState.Available and e.available_in_vfs
                for e in media_item.filesystem_entries
            )

        if item.type in ["movie", "episode"]:
            return [item] if has_available_entries(item) else []

        # Shows/Seasons should never reach Updater in new architecture, but handle gracefully
        if item.type == "show":
            return [
                e for season in item.seasons
                for e in season.episodes
                if has_available_entries(e)
            ]

        if item.type == "season":
            return [
                e for e in item.episodes
                if has_available_entries(e)
            ]

        return []
