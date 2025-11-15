from abc import ABC, abstractmethod
from typing import Any, Generic, TypeVar

from program.settings.models import Observable

T = TypeVar("T", bound=Observable)


class Runner(ABC, Generic[T]):
    """Base class for all runners"""

    is_content_service: bool = False
    settings: T

    def __init__(self):
        self.key = self.__class__.__name__.lower()
        self.initialized = False

    def validate(self) -> bool:
        """Validate the runner"""

        return True

    @abstractmethod
    def run(self, *args, **kwargs) -> Any:
        """Run the base runner"""

        raise NotImplementedError
