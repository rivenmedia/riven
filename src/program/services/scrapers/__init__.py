from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
from datetime import datetime
from typing import Dict, Generator, List

from loguru import logger

from program.media.item import MediaItem
from program.media.stream import Stream
from program.media.state import States
from program.services.scrapers.comet import Comet
from program.services.scrapers.jackett import Jackett
from program.services.scrapers.knightcrawler import Knightcrawler
from program.services.scrapers.mediafusion import Mediafusion
from program.services.scrapers.orionoid import Orionoid
from program.services.scrapers.prowlarr import Prowlarr
from program.services.scrapers.rarbg import Rarbg
from program.services.scrapers.shared import _parse_results
from program.services.scrapers.torrentio import Torrentio
from program.services.scrapers.zilean import Zilean
from program.settings.manager import settings_manager


class Scraping:
    def __init__(self):
        self.key = "scraping"
        self.initialized = False
        self.settings = settings_manager.settings.scraping
        self.max_failed_attempts = settings_manager.settings.scraping.max_failed_attempts
        self.imdb_services = {  # If we are missing imdb_id then we cant scrape here
            Torrentio: Torrentio(),
            Knightcrawler: Knightcrawler(),
            Orionoid: Orionoid(),
            Mediafusion: Mediafusion(),
            Comet: Comet()
        }
        self.keyword_services = {
            Jackett: Jackett(),
            Prowlarr: Prowlarr(),
            Zilean: Zilean(),
            # Rarbg: Rarbg()
        }
        self.services = {
            **self.imdb_services,
            **self.keyword_services
        }
        self.initialized = self.validate()
        if not self.initialized:
            return

    def validate(self):
        return any(service.initialized for service in self.services.values())

    def run(self, item: MediaItem) -> Generator[MediaItem, None, None]:
        """Scrape an item."""
        if item.state == States.Paused:
            logger.debug(f"Skipping scrape for {item.log_string}: Item is paused")
            yield item

        logger.debug(f"Starting scrape process for {item.log_string} ({item.id}). Current failed attempts: {item.failed_attempts}/{self.max_failed_attempts}. Current scraped times: {item.scraped_times}")

        if self.can_we_scrape(item):
            sorted_streams = self.scrape(item)
            new_streams = [
                stream for stream in sorted_streams.values()
                if stream not in item.streams
                and stream not in item.blacklisted_streams
            ]

            if new_streams:
                item.streams.extend(new_streams)
                item.failed_attempts = 0  # Reset failed attempts on success
                logger.log("SCRAPER", f"Added {len(new_streams)} new streams to {item.log_string}")
            else:
                logger.log("SCRAPER", f"No new streams added for {item.log_string}")

                item.failed_attempts = getattr(item, 'failed_attempts', 0) + 1
                if self.max_failed_attempts > 0 and item.failed_attempts >= self.max_failed_attempts:
                    item.store_state(States.Failed)
                    logger.debug(f"Failed scraping after {item.failed_attempts}/{self.max_failed_attempts} tries. Marking as failed: {item.log_string}")
                else:
                    logger.debug(f"Failed scraping after {item.failed_attempts}/{self.max_failed_attempts} tries: {item.log_string}")

            item.set("scraped_at", datetime.now())
            item.set("scraped_times", item.scraped_times + 1)

        yield item

    def scrape(self, item: MediaItem, verbose_logging = True) -> Dict[str, Stream]:
        """Scrape an item."""
        results: Dict[str, str] = {}
        results_lock = threading.RLock()

        imdb_id = item.get_top_imdb_id()
        available_services = self.services if imdb_id else self.keyword_services

        def run_service(service, item):
            service_results = service.run(item)
            if not isinstance(service_results, dict):
                logger.error(f"Service {service.__class__.__name__} returned invalid results: {service_results}")
                return

            with results_lock:
                try:
                    results.update(service_results)
                except Exception as e:
                    logger.exception(f"Error updating results for {service.__class__.__name__}: {e}")

        with ThreadPoolExecutor() as executor:
            futures = {executor.submit(run_service, service, item): service_name for service_name, service in available_services.items() if service.initialized}
            for future in as_completed(futures):
                try:
                    future.result()
                except Exception as e:
                    logger.error(f"Exception occurred while running service {futures[future]}: {e}")

        if not results:
            logger.log("NOT_FOUND", f"No streams to process for {item.log_string}")
            return {}

        sorted_streams: Dict[str, Stream] = _parse_results(item, results, verbose_logging)
        if sorted_streams and (verbose_logging and settings_manager.settings.debug):
            top_results: List[Stream] = list(sorted_streams.values())[:10]
            logger.debug(f"Displaying top {len(top_results)} results for {item.log_string}")
            for stream in top_results:
                logger.debug(f"[Rank: {stream.rank}][Res: {stream.parsed_data.resolution}] {stream.raw_title} ({stream.infohash})")

        return sorted_streams

    @classmethod
    def can_we_scrape(cls, item: MediaItem) -> bool:
        """Check if we can scrape an item."""
        if not item.is_released:
            logger.debug(f"Cannot scrape {item.log_string}: Item is not released")
            return False
        if item.active_stream:
            logger.debug(f"Cannot scrape {item.log_string}: Item was already downloaded by another session")
            return False    
        if not cls.should_submit(item):
            return False
        return True

    @staticmethod
    def should_submit(item: MediaItem) -> bool:
        """Check if an item should be submitted for scraping."""
        settings = settings_manager.settings.scraping
        scrape_time = 30 * 60  # 30 minutes by default

        if item.scraped_times >= 2 and item.scraped_times <= 5:
            scrape_time = settings.after_2 * 60 * 60
        elif item.scraped_times > 5 and item.scraped_times <= 10:
            scrape_time = settings.after_5 * 60 * 60
        elif item.scraped_times > 10:
            scrape_time = settings.after_10 * 60 * 60

        is_scrapeable = not item.scraped_at or (datetime.now() - item.scraped_at).total_seconds() > scrape_time
        if not is_scrapeable:
            return False

        if settings.max_failed_attempts > 0 and item.failed_attempts >= settings.max_failed_attempts:
            return False

        return True
