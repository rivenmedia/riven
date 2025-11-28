from typing import TypeVar

from program.settings.models import Observable
from program.core.runner import Runner


T = TypeVar("T", bound=Observable, default=Observable)


class AnalysisService(Runner[T, None, bool]):
    """Base class for all analysis services"""
