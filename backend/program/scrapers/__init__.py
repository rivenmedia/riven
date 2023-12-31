from datetime import datetime
import time
from utils.logger import logger
from .torrentio import Torrentio
from .orionoid import Orionoid
from .jackett import Jackett


class Scraping():
    def __init__(self):
        # self.services = [Torrentio(), Orionoid(), Jackett()]
        self.services = [Jackett()]  # TODO: Remove this line. Its just for testing
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
        item.set("scraped_at", datetime.now().timestamp())


scraper = Scraping()