from typing import TypeVar

from program.settings.models import Observable
from program.core.runner import Runner


T = TypeVar("T", bound=Observable, default=Observable)


class ContentService(Runner[T]):
    """Base class for all content services"""

    is_content_service: bool = True
