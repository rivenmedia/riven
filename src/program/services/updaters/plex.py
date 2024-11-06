"""Plex Updater module"""
import os
from typing import Dict, Generator, List, Union

from kink import di
from loguru import logger
from plexapi.exceptions import BadRequest, Unauthorized
from plexapi.library import LibrarySection
from requests.exceptions import ConnectionError as RequestsConnectionError
from urllib3.exceptions import MaxRetryError, NewConnectionError, RequestError

from program.apis.plex_api import PlexAPI
from program.media.item import Episode, Movie, Season, Show
from program.settings.manager import settings_manager


class PlexUpdater:
    def __init__(self):
        self.key = "plexupdater"
        self.initialized = False
        self.library_path = os.path.abspath(
            os.path.dirname(settings_manager.settings.symlink.library_path)
        )
        self.settings = settings_manager.settings.updaters.plex
        self.api = None
        self.sections: Dict[LibrarySection, List[str]] = {}
        self.initialized = self.validate()
        if not self.initialized:
            return
        logger.success("Plex Updater initialized!")

    def validate(self) -> bool:  # noqa: C901
        """Validate Plex library"""
        if not self.settings.enabled:
            return False
        if not self.settings.token:
            logger.error("Plex token is not set!")
            return False
        if not self.settings.url:
            logger.error("Plex URL is not set!")
            return False
        if not self.library_path or not os.path.exists(self.library_path):
            logger.error("Library path is not set or does not exist!")
            return False

        try:
            self.api = di[PlexAPI]
            self.api.validate_server()
            self.sections = self.api.map_sections_with_paths()
            self.initialized = True
            return True
        except Unauthorized as e:
            logger.error(f"Plex is not authorized!: {e}")
        except TimeoutError as e:
            logger.exception(f"Plex timeout error: {e}")
        except BadRequest as e:
            logger.exception(f"Plex is not configured correctly!: {e}")
        except MaxRetryError as e:
            logger.exception(f"Plex max retries exceeded: {e}")
        except NewConnectionError as e:
            logger.exception(f"Plex new connection error: {e}")
        except RequestsConnectionError as e:
            logger.exception(f"Plex requests connection error: {e}")
        except RequestError as e:
            logger.exception(f"Plex request error: {e}")
        except Exception as e:
            logger.exception(f"Plex exception thrown: {e}")
        return False

    def run(self, item: Union[Movie, Show, Season, Episode]) -> Generator[Union[Movie, Show, Season, Episode], None, None]:
        """Update Plex library section for a single item or a season with its episodes"""

        item_type = "movie" if isinstance(item, Movie) else "show"
        updated = False
        updated_episodes = []
        items_to_update = []

        if isinstance(item, (Movie, Episode)):
            items_to_update = [item]
        elif isinstance(item, Show):
            for season in item.seasons:
                items_to_update += [e for e in season.episodes if e.symlinked and e.get("update_folder") != "updated" ]
        elif isinstance(item, Season):
            items_to_update = [e for e in item.episodes if e.symlinked and e.update_folder != "updated"]

        if not items_to_update:
            logger.debug(f"No items to update for {item.log_string}")
            return

        section_name = None
        # any failures are usually because we are updating Plex too fast
        for section, paths in self.sections.items():
            if section.type == item_type:
                for path in paths:
                    if isinstance(item, (Show, Season)):
                        for episode in items_to_update:
                            if episode.update_folder and str(path) in str(episode.update_folder):
                                if self.api.update_section(section, episode):
                                    updated_episodes.append(episode)
                                    section_name = section.title
                                    updated = True
                    elif isinstance(item, (Movie, Episode)):
                        if item.update_folder and str(path) in str(item.update_folder):
                            if self.api.update_section(section, item):
                                section_name = section.title
                                updated = True

        if updated:
            if isinstance(item, (Show, Season)):
                if len(updated_episodes) == len(items_to_update):
                    logger.log("PLEX", f"Updated section {section_name} with all episodes for {item.log_string}")
                else:
                    updated_episodes_log = ", ".join([str(ep.number) for ep in updated_episodes])
                    logger.log("PLEX", f"Updated section {section_name} for episodes {updated_episodes_log} in {item.log_string}")
            else:
                logger.log("PLEX", f"Updated section {section_name} for {item.log_string}")

        yield item
