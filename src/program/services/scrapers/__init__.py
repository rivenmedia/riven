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
            Zilean: Zilean()
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
                logger.debug(f"Added {len(new_streams)} new streams to {item.log_string}")
            else:
                logger.debug(f"No new streams added for {item.log_string}")

                item.failed_attempts = getattr(item, 'failed_attempts', 0) + 1
                if item.failed_attempts >= self.max_failed_attempts:
                    item.store_state(States.Failed)
                    logger.warning(f"Failed scraping after {item.failed_attempts}/{self.max_failed_attempts} tries. Marking as failed: {item.log_string}")
                else:
                    logger.debug(f"Failed scraping after {item.failed_attempts}/{self.max_failed_attempts} tries: {item.log_string}")

                logger.log("NOT_FOUND", f"Scraping returned no good results for {item.log_string}")

            item.set("scraped_at", datetime.now())
            item.set("scraped_times", item.scraped_times + 1)

        yield item

    def scrape(self, item: MediaItem, log = True) -> Dict[str, Stream]:
        """Scrape an item."""
        threads: List[threading.Thread] = []
        results: Dict[str, str] = {}
        total_results = 0
        results_lock = threading.RLock()

        imdb_id = item.get_top_imdb_id()
        available_services = self.services if imdb_id else self.keyword_services

        def run_service(service, item,):
            nonlocal total_results
            service_results = service.run(item)

            if not isinstance(service_results, dict):
                logger.error(f"Service {service.__class__.__name__} returned invalid results: {service_results}")
                return

            # ensure that info hash is lower case in each result
            if isinstance(service_results, dict):
                for infohash in list(service_results.keys()):
                    if infohash.lower() != infohash:
                        service_results[infohash.lower()] = service_results.pop(infohash)

            with results_lock:
                results.update(service_results)
                total_results += len(service_results)

        for service_name, service in available_services.items():
            if service.initialized:
                thread = threading.Thread(target=run_service, args=(service, item), name=service_name.__name__)
                threads.append(thread)
                thread.start()

        for thread in threads:
            thread.join()

        if total_results != len(results):
            logger.debug(f"Scraped {item.log_string} with {total_results} results, removed {total_results - len(results)} duplicate hashes")

        sorted_streams: Dict[str, Stream] = {}

        if results:
            sorted_streams = _parse_results(item, results, log)

        if sorted_streams and (log and settings_manager.settings.debug):
            top_results: List[Stream] = list(sorted_streams.values())[:10]
            logger.debug(f"Displaying top {len(top_results)} results for {item.log_string}")
            for stream in top_results:
                logger.debug(f"[Rank: {stream.rank}][Res: {stream.parsed_data.resolution}] {stream.raw_title} ({stream.infohash})")
        else:
            logger.log("NOT_FOUND", f"No streams to process for {item.log_string}")

        return sorted_streams

    @classmethod
    def can_we_scrape(cls, item: MediaItem) -> bool:
        """Check if we can scrape an item."""
        if not item.is_released:
            logger.debug(f"Cannot scrape {item.log_string}: Item is not released")
            return False
        if not cls.should_submit(item):
            return False
        return True

    @staticmethod
    def should_submit(item: MediaItem) -> bool:
        """Check if an item should be submitted for scraping."""
        settings = settings_manager.settings.scraping
        scrape_time = 30 * 60  # 30 minutes by default

        if not item.is_released:
            logger.debug(f"Cannot scrape {item.log_string}: Item is not released")
            return False
        if item.active_stream:
            logger.debug(f"Cannot scrape {item.log_string}: Item was already downloaded by another session")
            return False
        if item.is_parent_blocked():
            logger.debug(f"Cannot scrape {item.log_string}: Item is blocked or blocked by a parent item")
            return False

        if item.scraped_times >= 2 and item.scraped_times <= 5:
            scrape_time = settings.after_2 * 60 * 60
        elif item.scraped_times > 5 and item.scraped_times <= 10:
            scrape_time = settings.after_5 * 60 * 60
        elif item.scraped_times > 10:
            scrape_time = settings.after_10 * 60 * 60

        is_scrapeable = not item.scraped_at or (datetime.now() - item.scraped_at).total_seconds() > scrape_time
        if not is_scrapeable:
            logger.debug(f"Cannot scrape {item.log_string}: Item has been scraped recently, backing off")
            return False

        if settings.max_failed_attempts > 0 and item.failed_attempts >= settings.max_failed_attempts:
            logger.debug(f"Cannot scrape {item.log_string}: Item has failed too many times. Failed attempts: {item.failed_attempts}/{settings.max_failed_attempts}")
            return False

        return True
