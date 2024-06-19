from datetime import datetime

from program.media.item import MediaItem
from program.scrapers.annatar import Annatar
from program.scrapers.jackett import Jackett
from program.scrapers.knightcrawler import Knightcrawler
from program.scrapers.mediafusion import Mediafusion
from program.scrapers.orionoid import Orionoid
from program.scrapers.prowlarr import Prowlarr
from program.scrapers.torbox import TorBoxScraper
from program.scrapers.torrentio import Torrentio
from program.settings.manager import settings_manager
from program.media.item import Season, Show
from program.media.state import States
from utils.logger import logger


class Scraping:
    def __init__(self, hash_cache):
        self.key = "scraping"
        self.initialized = False
        self.settings = settings_manager.settings.scraping
        self.hash_cache = hash_cache
        self.services = {
            Annatar: Annatar(self.hash_cache),
            Torrentio: Torrentio(self.hash_cache),
            Knightcrawler: Knightcrawler(self.hash_cache),
            Orionoid: Orionoid(self.hash_cache),
            Jackett: Jackett(self.hash_cache),
            TorBoxScraper: TorBoxScraper(self.hash_cache),
            Mediafusion: Mediafusion(self.hash_cache),
            Prowlarr: Prowlarr(self.hash_cache)
        }
        self.initialized = self.validate()
        if not self.initialized:
            return

    def validate(self):
        return any(service.initialized for service in self.services.values())

    def run(self, item: MediaItem):
        if not self.can_we_scrape(item):
            if isinstance(item, Season):
                res = [e for e in item.episodes if e.state not in [States.Completed]]
                yield res
                return
            if isinstance(item, Show):
                res = [s for s in item.seasons if s.state not in [States.Completed]]
                yield res
                return
            yield None
            return

        for service_name, service in self.services.items():
            if service.initialized:
                try:
                    item = next(service.run(item))
                except StopIteration:
                    logger.debug(f"{service_name} finished scraping for item: {item.log_string}")
                except Exception as e:
                    logger.error(f"{service_name} failed to scrape {item.log_string}: {e}")
        
        item.set("scraped_at", datetime.now())
        item.set("scraped_times", item.scraped_times + 1)
        if not item.get("streams", {}):
            logger.debug(f"{service_name} Scraped zero items for {item.log_string}")
            if isinstance(item, Season):
                res = [e for e in item.episodes if e.state not in [States.Completed]]
                yield res
                return
            if isinstance(item, Show):
                res = [s for s in item.seasons if s.state not in [States.Completed]]
                yield res
                return
            yield None
            return
        yield item

    @classmethod
    def can_we_scrape(cls, item: MediaItem) -> bool:
        """Check if we can scrape an item."""
        return item.is_released and cls.should_submit(item)

    @staticmethod
    def should_submit(item: MediaItem) -> bool:
        """Check if an item should be submitted for scraping."""
        settings = settings_manager.settings.scraping
        scrape_time = 5 * 60  # 5 minutes by default

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
