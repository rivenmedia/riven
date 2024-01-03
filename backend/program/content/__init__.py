import threading
import time
from utils.logger import logger
from .mdblist import Mdblist
from .overseerr import Overseerr
from .plex_watchlist import PlexWatchlist
from utils.service_manager import ServiceManager


class Content(threading.Thread):
    def __init__(self, media_items):
        super().__init__(name="Content")
        self.initialized = False
        self.key = "content"
        self.running = False
        self.sm = ServiceManager(media_items, Mdblist, Overseerr, PlexWatchlist)
        while not any(service.initialized for service in self.sm.services):
            logger.error(
                "You have no content services enabled, please enable at least one!"
            )
            time.sleep(2)

        self._get_content()
        self.initialized = True

    def validate(self):
        return any(service.initialized for service in self.services)

    def run(self) -> None:
        while self.running:
            self._get_content()
            time.sleep(1)

    def _get_content(self) -> None:
        for service in self.sm.services:
            if service.initialized:
                service.run()

    def start(self) -> None:
        self.running = True
        super().start()

    def stop(self) -> None:
        self.running = False
