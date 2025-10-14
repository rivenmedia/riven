"""Base Updater class for media server updaters"""

from abc import ABC, abstractmethod

from loguru import logger


class BaseUpdater(ABC):
    """
    Abstract base class for media server updaters.

    Provides a simple interface for media server updaters.
    Each updater only needs to implement:
    - validate(): Check configuration and connectivity
    - refresh_path(): Refresh a specific path in the media server
    """

    def __init__(self, service_name: str):
        """
        Initialize the base updater.

        Args:
            service_name: Name of the service (e.g., "Plex", "Emby", "Jellyfin")
        """
        self.key = service_name
        self.initialized = False

    def _initialize(self):
        """Initialize the updater by validating configuration."""
        if self.validate():
            self.initialized = True
            logger.success(f"{self.__class__.__name__} updater initialized")

    @abstractmethod
    def validate(self) -> bool:
        """
        Validate the updater configuration and connectivity.

        Returns:
            bool: True if validation successful, False otherwise
        """
        pass

    @abstractmethod
    def refresh_path(self, path: str) -> bool:
        """
        Refresh a specific path in the media server.

        This triggers the media server to scan/refresh the given path,
        which will add/remove/update items as needed.

        Args:
            path: Absolute path to refresh in the media server

        Returns:
            bool: True if refresh was triggered successfully, False otherwise
        """
        pass
