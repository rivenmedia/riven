from abc import ABC, abstractmethod
from typing import Any, Generic, TypeVar

from program.settings.models import Observable

TSettings = TypeVar("TSettings", bound=Observable | None)
TService = TypeVar("TService", bound=Any | None, default=None)


class Runner(ABC, Generic[TSettings, TService]):
    """Base class for all runners"""

    is_content_service: bool = False
    settings: TSettings
    services: list[TService] | None

    def __init__(self):
        self.key = self.__class__.__name__.lower()
        self.initialized = False
        self.services = None

    def validate(self) -> bool:
        """Validate the runner"""

        return True

    @abstractmethod
    def run(self, *args, **kwargs) -> Any:
        """Run the base runner"""

        raise NotImplementedError
