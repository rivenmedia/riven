from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Generic, TypeVar


from program.settings.models import Observable
from program.media.item import MediaItem

TSettings = TypeVar(
    "TSettings",
    bound=Observable | None,
    default=Observable,
    covariant=True,
)

TService = TypeVar("TService", bound=Any | None, default="Runner")

TItemType = TypeVar("TItemType", bound=MediaItem, default=MediaItem, covariant=True)


@dataclass
class RunnerResult(Generic[TItemType]):
    media_items: list[TItemType]
    error: Exception | None = None
    run_at: datetime | None = None


TRunnerReturnType = TypeVar(
    "TRunnerReturnType",
    bound=RunnerResult | dict[str, str] | bool | None,
    default=RunnerResult,
)


class Runner(ABC, Generic[TSettings, TService, TRunnerReturnType]):
    """Base class for all runners"""

    is_content_service: bool = False
    settings: TSettings
    services: dict[type[TService], TService]

    def __init__(self):
        super().__init__()

        self.initialized = False
        self.key = self.get_key()

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
    async def run(self, item: MediaItem) -> TRunnerReturnType:
        """Run the base runner"""

        raise NotImplementedError

    def should_submit(self, item: MediaItem) -> bool:
        """Determine if the runner should submit an item for processing."""

        return True
