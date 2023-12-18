import threading
import time

from utils.logger import logger
from .mdblist import Mdblist
from .overseerr import Overseerr
from .plex_watchlist import PlexWatchlist


class Content(threading.Thread):
    def __init__(self, media_items):
        super().__init__(name="Content")
        self.services = [
            Mdblist(media_items),
            Overseerr(media_items),
            PlexWatchlist(media_items),
        ]
        self.valid = False
        self.running = False
        while not self.validate():
            logger.error(
                "You have no content services enabled, please enable at least one!"
            )
            time.sleep(5)

        for service in self.services:
            if service.initialized:
                service.run()

    def validate(self):
        return any(service.initialized for service in self.services)

    def run(self) -> None:
        while self.running:
            for service in self.services:
                if service.initialized:
                    service.run()

    def start(self) -> None:
        self.running = True
        super().start()

    def stop(self) -> None:
        self.running = False
        super().join()
