from datetime import datetime
import time
from utils.service_manager import ServiceManager
from utils.logger import logger
from .torrentio import Torrentio
from .orionoid import Orionoid
from .jackett import Jackett


class Scraping:
    def __init__(self):
        self.key = "scrape"
        self.initialized = False
        self.sm = ServiceManager(None, Torrentio, Orionoid, Jackett)
        while not any(service.initialized for service in self.sm.services):
            logger.error(
                "You have no scraping services enabled, please enable at least one!"
            )
            time.sleep(5)
        self.initialized = True

    def run(self, item) -> None:
        if self._can_we_scrape(item):
            for service in self.sm.services:
                if service.initialized:
                    service.run(item)
        item.set("scraped_at", datetime.now().timestamp())

    def _can_we_scrape(self, item) -> bool:
        return self._is_released(item) and self._needs_new_scrape(item)

    def _is_released(self, item) -> bool:
        return item.aired_at is not None and item.aired_at < datetime.now()

    def _needs_new_scrape(self, item) -> bool:
        return (
            datetime.now().timestamp() - item.scraped_at
            > 60 * 30  # 30 minutes between scrapes
            or item.scraped_at == 0
        )
