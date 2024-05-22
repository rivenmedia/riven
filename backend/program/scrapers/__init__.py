from datetime import datetime, timedelta

from program.media.item import MediaItem
from program.scrapers.annatar import Annatar
from program.scrapers.jackett import Jackett
from program.scrapers.orionoid import Orionoid
from program.scrapers.torrentio import Torrentio
from program.settings.manager import settings_manager
from utils.logger import logger


class Scraping:
    def __init__(self):
        self.key = "scraping"
        self.initialized = False
        self.settings = settings_manager.settings.scraping
        self.services = {
            Annatar: Annatar(),
            Torrentio: Torrentio(),
            Orionoid: Orionoid(),
            Jackett: Jackett(),
        }
        self.initialized = self.validate()

    def validate(self):
        if not (validated := any(service.initialized for service in self.services.values())):
            logger.error("You have no scraping services enabled, please enable at least one!")
        return validated

    def run(self, item: MediaItem):
        if not self._can_we_scrape(item):
            yield None

        for service in self.services.values():
            if service.initialized and self.should_submit(item):
                try:
                    updated_item = next(service.run(item))
                    if updated_item:
                        item = updated_item
                except StopIteration:
                    break
        item.set("scraped_at", datetime.now())
        item.set("scraped_times", item.scraped_times + 1)
        yield item

    def _can_we_scrape(self, item: MediaItem) -> bool:
        # return True if the item is released and atleast 4 hours have passed since it was released
        # also check if we should submit the item for scraping based on the number of times it has been scraped
        return self.is_released(item) and self.should_submit(item)

    @staticmethod
    def is_released(item: MediaItem) -> bool:
        if not item or not item.aired_at:
            return False
        # return True if the item is released and atleast 4 hours have passed since it was released
        return (item.aired_at + timedelta(hours=4)) < datetime.now()

    @staticmethod
    def should_submit(item: MediaItem) -> bool:
        settings = settings_manager.settings.scraping
        scrape_time = 5  # 5 seconds by default

        if item.scraped_times >= 2 and item.scraped_times <= 5:
            scrape_time = settings.after_2 * 60 * 60
        elif item.scraped_times > 5 and item.scraped_times <= 10:
            scrape_time = settings.after_5 * 60 * 60
        elif item.scraped_times > 10:
            scrape_time = settings.after_10 * 60 * 60

        return (
            not item.scraped_at
            or (datetime.now() - item.scraped_at).total_seconds() > scrape_time
        )
