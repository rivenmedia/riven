from datetime import datetime
from pydantic import BaseModel
from utils.service_manager import ServiceManager
from utils.settings import settings_manager as settings
from utils.logger import logger
from utils.parser import parser
from .torrentio import Torrentio
from .orionoid import Orionoid
from .jackett import Jackett


class ScrapingConfig(BaseModel):
    after_2: float
    after_5: float
    after_10: float

class Scraping:
    def __init__(self, _):
        self.key = "scraping"
        self.initialized = False
        self.settings = ScrapingConfig(**settings.get(self.key))
        self.sm = ServiceManager(None, False, Torrentio, Orionoid, Jackett)
        if not any(service.initialized for service in self.sm.services):
            logger.error(
                "You have no scraping services enabled, please enable at least one!"
            )
            return
        self.initialized = True

    def run(self, item) -> None:
        if self._can_we_scrape(item):
            for service in self.sm.services:
                if service.initialized:
                    service.run(item)
            item.set("scraped_at", datetime.now())
            item.set("scraped_times", item.scraped_times + 1)

    def _can_we_scrape(self, item) -> bool:
        return self._is_released(item) and self._needs_new_scrape(item)

    def _is_released(self, item) -> bool:
        return item.aired_at is not None and item.aired_at < datetime.now()

    def _needs_new_scrape(self, item) -> bool:
        scrape_time = 5 # 5 seconds by default

        if item.scraped_times >= 2 and item.scraped_times <= 5:
            scrape_time = self.settings.after_2 * 60 * 60
        elif item.scraped_times > 5 and item.scraped_times <= 10:
            scrape_time = self.settings.after_5 * 60 * 60
        elif item.scraped_times > 10:
            scrape_time = self.settings.after_10 * 60 * 60

        return (
            (datetime.now() - item.scraped_at).total_seconds()
            > scrape_time
            or item.scraped_times == 0
        )
