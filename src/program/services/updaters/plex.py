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
        """Refresh a specific path in Plex by finding the matching section

        Handles centralized VFS paths (e.g., /mount/library/shows/...) by mapping them
        to profile-specific paths (e.g., /mount/library/regular/shows/...) based on
        configured library profiles.
        """
        logger.debug(f"PlexUpdater.refresh_path({path})")

        # Try direct matching first
        for section, section_paths in self.sections.items():
            logger.debug(
                f"  Checking section '{section.title}' with paths: {section_paths}"
            )
            for section_path in section_paths:
                if path.startswith(section_path):
                    logger.info(
                        f"  ✓ Path matches section '{section.title}', calling update_section"
                    )
                    result = self.api.update_section(section, path)
                    logger.debug(f"  update_section returned: {result}")
                    return result

        # If no direct match, try mapping centralized paths through library profiles
        # This handles cases where VFS has centralized /shows /movies but Plex has profile-specific paths
        library_profiles = settings_manager.settings.filesystem.library_profiles
        if library_profiles:
            for profile_name, profile_config in library_profiles.items():
                profile_path = profile_config.library_path  # e.g., "/regular", "/anime"
                # Check if this profile should handle the centralized path
                # by looking for matches in the configured section paths
                for section, section_paths in self.sections.items():
                    for section_path in section_paths:
                        # section_path might be /mount/library/regular/shows or /mnt/riven/mount/regular/shows
                        if profile_path in section_path:
                            # This section is for this profile
                            # Try to map the centralized path to this profile's path
                            # e.g., /mount/library/shows/Show Name -> /mount/library/regular/shows/Show Name
                            mapped_path = path.replace(
                                f"{self.library_path}/shows",
                                f"{self.library_path}{profile_path}/shows",
                            ).replace(
                                f"{self.library_path}/movies",
                                f"{self.library_path}{profile_path}/movies",
                            )

                            if mapped_path != path and mapped_path.startswith(
                                section_path
                            ):
                                logger.info(
                                    f"  ✓ Mapped centralized path {path} to {mapped_path} for section '{section.title}'"
                                )
                                result = self.api.update_section(section, mapped_path)
                                logger.debug(f"  update_section returned: {result}")
                                if result:
                                    return result

        logger.warning(f"  ✗ No matching section found for path: {path}")
        return False
