"""Plex Updater module"""

from typing import Dict, List

from kink import di
from loguru import logger
from plexapi.exceptions import BadRequest, Unauthorized
from plexapi.library import LibrarySection
from requests.exceptions import ConnectionError as RequestsConnectionError
from urllib3.exceptions import MaxRetryError, NewConnectionError, RequestError

from program.apis.plex_api import PlexAPI
from program.services.updaters.base import BaseUpdater
from program.settings.manager import settings_manager


class PlexUpdater(BaseUpdater):
    def __init__(self):
        super().__init__("plexupdater")
        self.library_path = settings_manager.settings.updaters.library_path
        self.settings = settings_manager.settings.updaters.plex
        self.api = None
        self.sections: Dict[LibrarySection, List[str]] = {}
        self._initialize()

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
        if not self.library_path:
            logger.error("Library path is not set!")
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

    def refresh_path(self, path: str) -> bool:
        """Refresh a specific path in Plex by finding the matching section"""
        for section, section_paths in self.sections.items():
            for section_path in section_paths:
                if path.startswith(section_path):
                    return self.api.update_section(section, path)
        return False
