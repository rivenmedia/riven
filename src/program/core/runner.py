from abc import ABC, abstractmethod
from typing import Any, Generic, TypeVar

from program.settings.models import Observable

TSettings = TypeVar("TSettings", bound=Observable | None)
TService = TypeVar("TService", bound=Any | None, default="Runner")


class Runner(ABC, Generic[TSettings, TService]):
    """Base class for all runners"""

    is_content_service: bool = False
    settings: TSettings
    services: list[TService] | dict[type[TService], TService]

    def __init__(self):
        super().__init__()

        self.key = self.get_key()
        self.initialized = False

    @classmethod
    def get_key(cls) -> str:
        """Get the key for the runner"""

        return cls.__name__.lower()

    @property
    def enabled(self) -> bool:
        """
        Check if the runner is enabled.

        Returns True for core runners without settings, else returns the `enabled` attribute from the runner's settings.
        """

        if not hasattr(self, "settings") or not hasattr(self.settings, "enabled"):
            return True

        return getattr(self.settings, "enabled", True)

    def validate(self) -> bool:
        """Validate the runner"""

        return True

    @abstractmethod
    def run(self, *args, **kwargs) -> Any:
        """Run the base runner"""

        raise NotImplementedError
