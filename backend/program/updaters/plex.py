"""Plex Updater module"""
import os
from typing import Generator, Union

from plexapi.exceptions import BadRequest, Unauthorized
from plexapi.server import PlexServer
from program.media.item import Episode, Movie
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
        self.sections = None
        self.initialized = self.validate()
        if not self.initialized:
            return
        logger.success("Plex Updater initialized!")

    def validate(self):  # noqa: C901
        """Validate Plex library"""
        if not self.settings.token:
            logger.error("Plex Updater token is not set, this is required!")
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
            self.sections = self.map_sections_with_paths()
            self.initialized = True
            return True
        except Unauthorized:
            logger.error("Plex is not authorized!")
        except BadRequest:
            logger.error("Plex is not configured correctly!")
        except MaxRetryError:
            logger.error("Plex max retries exceeded")
        except NewConnectionError:
            logger.error("Plex new connection error")
        except RequestsConnectionError:
            logger.error("Plex requests connection error")
        except RequestError as e:
            logger.error(f"Plex request error: {e}")
        except Exception as e:
            logger.exception(f"Plex exception thrown: {e}")
        return False

    def run(self, item: Union[Movie, Episode]) -> Generator[Union[Movie, Episode], None, None]:
        """Update Plex library section for a single item"""
        if not item or not item.update_folder:
            logger.error(f"Item {item.log_string} is missing update folder: {item.update_folder}")
            yield item
            return
        
        item_type = "show" if isinstance(item, Episode) else "movie"
        for section, paths in self.sections.items():
            if section.type == item_type:
                for path in paths:
                    if path in item.update_folder and self._update_section(section, item):
                        logger.log("PLEX", f"Updated section {section.title} for {item.log_string}")
        yield item

    def _update_section(self, section, item) :
        """Update the Plex section for the given item"""
        if item.symlinked and item.get("update_folder") != "updated":
            update_folder = item.update_folder
            section.update(str(update_folder))
            item.set("update_folder", "updated")
            return True
        logger.error(f"Failed to update section {section.title} for {item.log_string}")
        return False

    def map_sections_with_paths(self):
        """Map Plex sections with their paths"""
        # Skip sections without locations and non-movie/show sections
        sections = [section for section in self.plex.library.sections() if section.type in ["show", "movie"] and section.locations]
        # Map sections with their locations with the section obj as key and the location strings as values
        return {section: section.locations for section in sections}
