import threading
import time
from utils.logger import logger
from utils.service_manager import ServiceManager
from .mdblist import Mdblist
from .overseerr import Overseerr
from .plex_watchlist import PlexWatchlist
from .listrr import Listrr


class Content(threading.Thread):
    def __init__(self, media_items):
        super().__init__(name="Content")
        self.initialized = False
        self.key = "content"
        self.running = False
        self.sm = ServiceManager(media_items, False, Overseerr, PlexWatchlist, Listrr, Mdblist)
        if not self.validate():
            logger.error("You have no content services enabled, please enable at least one!")
            return
        self._get_content()
        self.initialized = True

    def validate(self):
        return any(service.initialized for service in self.sm.services)

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
