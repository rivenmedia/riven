"""Local Updater module"""
from typing import Generator, Union

from program.media.item import Episode, Movie, Season, Show
from program.settings.manager import settings_manager
from utils.logger import logger


class LocalUpdater:
    def __init__(self):
        self.key = "localupdater"
        self.initialized = self.validate()
        if not self.initialized:
            return
        logger.success("Local Updater initialized!")

    def validate(self) -> bool:
        """Validate Local Updater"""
        if not settings_manager.settings.local_only:
            logger.warning("Local Updater is set to disabled.")
            return False
        if settings_manager.settings.plex.token:
            logger.error("Local Updater cannot be enabled if Plex is enabled!")
            return False
        return True

    def run(self, item: Union[Movie, Show, Season, Episode]) -> Generator[Union[Movie, Show, Season, Episode], None, None]:
        """Bypasses updating a media server application and uses a local directory instead."""
        # This is for users that don't want to use Plex, but still want to use the app.

        if not item:
            logger.error(f"Item type not supported, skipping {item}")
            yield item
            return

        def update_item(item):
            if not item.symlinked or item.get("update_folder") == "updated":
                return False
            item.set("update_folder", "updated")
            return True

        items_to_update = []

        if isinstance(item, (Movie, Episode)):
            items_to_update = [item] if update_item(item) else []
        elif isinstance(item, Show):
            for season in item.seasons:
                items_to_update += [e for e in season.episodes if update_item(e)]
        elif isinstance(item, Season):
            items_to_update = [e for e in item.episodes if update_item(e)]

        for updated_item in items_to_update:
            yield updated_item

        if not items_to_update:
            yield item
