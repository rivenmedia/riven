from abc import ABC, abstractmethod
from collections.abc import Generator
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

type MediaItemGenerator[T: MediaItem = MediaItem] = Generator[
    RunnerResult[T], None, RunnerResult[T] | None
]

TRunnerReturnType = TypeVar(
    "TRunnerReturnType",
    bound=MediaItemGenerator | dict[str, str] | bool | None,
    default=MediaItemGenerator,
)


@dataclass
class RunnerResult(Generic[TItemType]):
    media_items: list[TItemType]
    run_at: datetime | None = None


class Runner(ABC, Generic[TSettings, TService, TRunnerReturnType]):
    """Base class for all runners"""

    is_content_service: bool = False
    settings: TSettings
    services: dict[type[TService], TService]

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
    def run(self, item: MediaItem) -> TRunnerReturnType:
        """Run the base runner"""

        raise NotImplementedError

    def should_submit(self, item: MediaItem) -> bool:
        """Determine if the runner should submit an item for processing."""

        return True
