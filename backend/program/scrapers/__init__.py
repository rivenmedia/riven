import time
from utils.logger import logger
from .torrentio import Torrentio


class Scraping():
    def __init__(self):
        self.services = [Torrentio()]
        while not self.validate():
            logger.error(
                "You have no scraping services enabled, please enable at least one!"
            )
            time.sleep(5)

    def validate(self):
        return any(service.initialized for service in self.services)

    def run(self, item) -> None:
        for service in self.services:
            if service.initialized:
                service.run(item)

scraper = Scraping()