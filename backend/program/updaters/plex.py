"""Plex Updater module"""
import os
from plexapi.server import PlexServer
from plexapi.exceptions import BadRequest, Unauthorized
from utils.logger import logger
from program.settings.manager import settings_manager
from program.media.item import Episode


class PlexUpdater:
    def __init__(self):
        self.key = "plexupdater"
        self.initialized = False
        self.library_path = os.path.abspath(
            os.path.dirname(settings_manager.settings.symlink.library_path)
        )
        try:
            self.settings = settings_manager.settings.plex
            self.plex = PlexServer(self.settings.url, self.settings.token, timeout=60)
        except Unauthorized:
            logger.error("Plex is not authorized!")
            return
        except BadRequest as e:
            logger.error("Plex is not configured correctly: %s", e)
            return
        except Exception as e:
            logger.error("Plex exception thrown: %s", e)
            return
        self.initialized = True

    def run(self, item):
        """Update plex library section for a single item"""
        item_type = "show" if isinstance(item, Episode) else "movie"
        for section in self.plex.library.sections():
            if section.type != item_type:
                continue

            if self._update_section(section, item):
                logger.debug(
                    "Updated section %s for %s", section.title, item.log_string
                )
        yield item

    def _update_section(self, section, item):
        if item.symlinked and item.get("update_folder") != "updated":
            update_folder = item.update_folder
            section.update(str(update_folder))
            item.set("update_folder", "updated")
            return True
        return False