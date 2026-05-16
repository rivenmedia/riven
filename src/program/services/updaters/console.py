"""Console updater: no-op stand-in when no media server updater is configured."""

from loguru import logger

from program.services.updaters.base import BaseUpdater


class ConsoleUpdater(BaseUpdater):
    """
    Logs library refresh requests instead of calling Plex/Jellyfin/Emby.

    Used when no real updater is configured so the pipeline can stay valid.
    """

    def __init__(self) -> None:
        super().__init__("console")
        self._initialize()

    def validate(self) -> bool:
        return True

    def refresh_path(self, path: str) -> bool:
        logger.info(f"[ConsoleUpdater] would refresh library path: {path}")
        return True
