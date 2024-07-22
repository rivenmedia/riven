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
        if not settings_manager.settings.updaters.local.enabled:
            logger.warning("Local Updater is set to disabled.")
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
            if items_to_update:
                logger.log("LOCAL", f"Updated {item.log_string}")
        elif isinstance(item, Show):
            items_to_update = [e for season in item.seasons for e in season.episodes if update_item(e)]
            if items_to_update:
                if all(e.symlinked for season in item.seasons for e in season.episodes):
                    logger.log("LOCAL", f"Updated {item.log_string}")
                else:
                    for updated_item in items_to_update:
                        logger.log("LOCAL", f"Updated {updated_item.log_string}")
        elif isinstance(item, Season):
            items_to_update = [e for e in item.episodes if update_item(e)]
            if items_to_update:
                if all(e.symlinked for e in item.episodes):
                    logger.log("LOCAL", f"Updated {item.log_string}")
                else:
                    for updated_item in items_to_update:
                        logger.log("LOCAL", f"Updated {updated_item.log_string}")

        if not items_to_update:
            logger.log("LOCAL", f"No items to update for {item.log_string}")

        yield item
