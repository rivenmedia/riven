from datetime import datetime
from utils.logger import logger
from utils.service_manager import ServiceManager
from program.settings.manager import settings_manager
from program.scrapers.torrentio import Torrentio
from program.scrapers.orionoid import Orionoid
from program.scrapers.jackett import Jackett
from program.media.item import MediaItem


class Scraping:
    def __init__(self):
        self.key = "scraping"
        self.initialized = False
        self.settings = settings_manager.settings.scraping
        self.services = (Orionoid(), Torrentio(), Jackett())
        self.initialized = self.validate()

    def run(self, item: MediaItem) -> MediaItem | None:
        if not self._can_we_scrape(item):
            return None
        for service in self.services:
            if service.initialized:
                item = service.run(item)
        item.set("scraped_at", datetime.now())
        item.set("scraped_times", item.scraped_times + 1)
        yield item

    
    def validate(self):
        if not (validated := any(service.initialized for service in self.services)):
            logger.error("You have no scraping services enabled," 
                " please enable at least one!"
            )
        return validated
    
    def _can_we_scrape(self, item: MediaItem) -> bool:
        return self._is_released(item) and self._needs_new_scrape(item)

    def _is_released(self, item: MediaItem) -> bool:
        return item.aired_at is not None and item.aired_at < datetime.now()

    def _needs_new_scrape(self, item: MediaItem) -> bool:
        scrape_time = 5  # 5 seconds by default

        if item.scraped_times >= 2 and item.scraped_times <= 5:
            scrape_time = self.settings.after_2 * 60 * 60
        elif item.scraped_times > 5 and item.scraped_times <= 10:
            scrape_time = self.settings.after_5 * 60 * 60
        elif item.scraped_times > 10:
            scrape_time = self.settings.after_10 * 60 * 60

        return (
            datetime.now() - item.scraped_at
        ).total_seconds() > scrape_time or item.scraped_times == 0
