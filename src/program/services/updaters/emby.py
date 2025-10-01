"""Emby Updater module"""
from loguru import logger

from program.services.updaters.base import BaseUpdater
from program.settings.manager import settings_manager
from program.utils.request import SmartSession


class EmbyUpdater(BaseUpdater):
    """Emby media server updater implementation"""

    def __init__(self):
        super().__init__("Emby")
        self.settings = settings_manager.settings.updaters.emby
        self.session = SmartSession(retries=3, backoff_factor=0.3)
        self._initialize()

    def validate(self) -> bool:
        """Validate Emby configuration and connectivity"""
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
                return True
        except Exception as e:
            logger.exception(f"Emby exception thrown: {e}")
        return False

    def refresh_path(self, path: str) -> bool:
        """Refresh a specific path in Emby"""
        try:
            response = self.session.post(
                f"{self.settings.url}/Library/Media/Updated",
                json={"Updates": [{"Path": path, "UpdateType": "Created"}]},
                params={"api_key": self.settings.api_key},
            )
            return response.ok
        except Exception as e:
            logger.error(f"Failed to refresh Emby path {path}: {e}")
            return False
