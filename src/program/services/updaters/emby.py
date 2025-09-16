"""Emby Updater module"""
import os
from types import SimpleNamespace
from typing import Generator

from loguru import logger

from program.media.item import MediaItem
from program.settings.manager import settings_manager
from program.utils.request import SmartSession


class EmbyUpdater:
    def __init__(self):
        self.key = "emby"
        self.initialized = False
        self.settings = settings_manager.settings.updaters.emby
        self.session = SmartSession(retries=3, backoff_factor=0.3)
        # Use same library path logic as PlexUpdater
        self.library_path = os.path.abspath(
            os.path.dirname(settings_manager.settings.updaters.library_path)
        )
        self.initialized = self.validate()
        if not self.initialized:
            return
        logger.success("Emby Updater initialized!")

    def validate(self) -> bool:
        """Validate Emby library"""
        if not self.settings.enabled:
            return False
        if not self.settings.api_key:
            logger.error("Emby API key is not set!")
            return False
        if not self.settings.url:
            logger.error("Emby URL is not set!")
            return False
        try:
            response = self.session.get(f"{self.settings.url}/Users?api_key={self.settings.api_key}")
            if response.ok:
                self.initialized = True
                return True
        except Exception as e:
            logger.exception(f"Emby exception thrown: {e}")
        return False

    def run(self, item: MediaItem) -> Generator[MediaItem, None, None]:
        """Update Emby library for a single item or a season with its episodes"""
        items_to_update = []

        if item.type in ["movie", "episode"]:
            items_to_update = [item]
        elif item.type == "show":
            for season in item.seasons:
                items_to_update += [
                    e for e in season.episodes
                    if e.available_in_vfs
                ]
        elif item.type == "season":
            items_to_update = [
                e for e in item.episodes
                if e.available_in_vfs
            ]

        if not items_to_update:
            logger.debug(f"No items to update for {item.log_string}")
            return

        updated = False
        updated_episodes = []

        for item_to_update in items_to_update:
            if self.update_item(item_to_update):
                updated_episodes.append(item_to_update)
                updated = True

        if updated:
            if item.type in ["show", "season"]:
                if len(updated_episodes) == len(items_to_update):
                    logger.log("EMBY", f"Updated all episodes for {item.log_string}")
                else:
                    updated_episodes_log = ", ".join([str(ep.number) for ep in updated_episodes])
                    logger.log("EMBY", f"Updated episodes {updated_episodes_log} in {item.log_string}")
            else:
                logger.log("EMBY", f"Updated {item.log_string}")

        yield item


    def update_item(self, item: MediaItem) -> bool:
        """Update the Emby item"""
        # Build absolute path inside the server's library using the VFS path
        vfs_path = item.filesystem_entry.path if item.filesystem_entry else None
        if item.available_in_vfs and vfs_path and not vfs_path.startswith("/__incoming__/"):
            abs_path = os.path.join(self.library_path, vfs_path.lstrip("/"))
            try:
                response = self.session.post(
                    f"{self.settings.url}/Library/Media/Updated",
                    json={"Updates": [{"Path": abs_path, "UpdateType": "Created"}]},
                    params={"api_key": self.settings.api_key},
                )
                if response.ok:
                    return True
            except Exception as e:
                logger.error(f"Failed to update Emby item: {e}")
        return False

    # not needed to update, but maybe useful in the future?
    def get_libraries(self) -> list[SimpleNamespace]:
        """Get the libraries from Emby"""
        try:
            response = self.session.get(
                f"{self.settings.url}/Library/VirtualFolders",
                params={"api_key": self.settings.api_key},
            )
            if response.ok and response.data:
                return response.data
        except Exception as e:
            logger.error(f"Failed to get Emby libraries: {e}")
        return []
