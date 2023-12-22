import threading
import time

from utils.logger import logger
from .torrentio import Torrentio


class Scraping(threading.Thread):
    def __init__(self, media_items):
        super().__init__(name="Scraping")
        self.media_items = media_items
        self.services = [Torrentio(self.media_items)]
        self.running = False
        self.valid = False
        while not self.validate():
            logger.error(
                "You have no scraping services enabled, please enable at least one!"
            )
            time.sleep(5)

    def validate(self):
        return any(service.initialized for service in self.services)

    def run(self) -> None:
        while self.running:
            for service in self.services:
                if service.initialized:
                    service.run()
                    time.sleep(1)


    def start(self) -> None:
        self.running = True
        super().start()

    def stop(self) -> None:
        self.running = False
        super().join()
