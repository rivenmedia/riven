"""Jellyfin Updater module"""
from loguru import logger

from program.services.updaters.base import BaseUpdater
from program.settings.manager import settings_manager
from program.utils.request import SmartSession


class JellyfinUpdater(BaseUpdater):
    """Jellyfin media server updater implementation"""

    def __init__(self):
        super().__init__("jellyfin")
        self.settings = settings_manager.settings.updaters.jellyfin
        self.session = SmartSession(retries=3, backoff_factor=0.3)
        self._initialize()

    def validate(self) -> bool:
        """Validate Jellyfin configuration and connectivity"""
        if not self.settings.enabled:
            return False
        if not self.settings.api_key:
            logger.error("Jellyfin API key is not set!")
            return False
        if not self.settings.url:
            logger.error("Jellyfin URL is not set!")
            return False

        try:
            response = self.session.get(f"{self.settings.url}/Users", params={"api_key": self.settings.api_key})
            if response.ok:
                return True
        except Exception as e:
            logger.exception(f"Jellyfin exception thrown: {e}")
        return False

    def refresh_path(self, _path: str) -> bool:
        """
        Refresh Jellyfin library.

        Note: Jellyfin's API refreshes the entire library, not individual paths.
        The path parameter is ignored.
        """
        try:
            response = self.session.post(
                f"{self.settings.url}/Library/Refresh",
                params={"api_key": self.settings.api_key},
            )
            return response.ok
        except Exception as e:
            logger.error(f"Failed to refresh Jellyfin library: {e}")
            return False
