"""Plex Updater module"""
import os

from plexapi.exceptions import BadRequest, Unauthorized
from plexapi.server import PlexServer
from program.media.item import Episode
from program.settings.manager import settings_manager
from requests.exceptions import ConnectionError as RequestsConnectionError
from urllib3.exceptions import MaxRetryError, NewConnectionError, RequestError
from utils.logger import logger


class PlexUpdater:
    def __init__(self):
        self.key = "plexupdater"
        self.initialized = False
        self.library_path = os.path.abspath(
            os.path.dirname(settings_manager.settings.symlink.library_path)
        )
        self.settings = settings_manager.settings.plex
        self.plex = None
        self.initialized = self.validate()
        if not self.initialized:
            return
        logger.info("Plex Updater initialized!")

    def validate(self):  # noqa: C901
        """Validate Plex library"""
        if not self.settings.token:
            logger.error("Plex token is not set!")
            return False
        if not self.settings.url:
            logger.error("Plex URL is not set!")
            return False
        if not self.library_path:
            logger.error("Library path is not set!")
            return False
        if not os.path.exists(self.library_path):
            logger.error("Library path does not exist!")
            return False

        try:
            self.plex = PlexServer(self.settings.url, self.settings.token, timeout=60)
            self.initialized = True
            return True
        except Unauthorized:
            logger.error("Plex is not authorized!")
        except BadRequest as e:
            logger.error("Plex is not configured correctly: %s", str(e))
        except MaxRetryError as e:
            logger.error("Plex max retries exceeded: %s", str(e))
        except NewConnectionError as e:
            logger.error("Plex new connection error: %s", str(e))
        except RequestsConnectionError as e:
            logger.error("Plex requests connection error: %s", str(e))
        except RequestError as e:
            logger.error("Plex request error: %s", str(e))
        except Exception as e:
            logger.error("Plex exception thrown: %s", str(e))
        return False

    def run(self, item):
        """Update plex library section for a single item"""
        item_type = "show" if isinstance(item, Episode) else "movie"
        for section in self.plex.library.sections():
            if section.type != item_type:
                continue

            if self._update_section(section, item):
                logger.info(
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
