import threading
from datetime import datetime
from typing import Dict, Generator, List

from loguru import logger

from program.media.item import MediaItem
from program.media.stream import Stream
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
        if self.can_we_scrape(item):
            sorted_streams = self.scrape(item)
            for stream in sorted_streams.values():
                if stream not in item.streams:
                    item.streams.append(stream)
            item.set("scraped_at", datetime.now())
            item.set("scraped_times", item.scraped_times + 1)

        if not item.get("streams", []):
            logger.log("NOT_FOUND", f"Scraping returned no good results for {item.log_string}")

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
            item_type = item.type.title()
            top_results = list(sorted_streams.values())[:10]
            for sorted_tor in top_results:
                item_info = f"[{item_type}]"
                if item.type == "season":
                    item_info = f"[{item_type} {item.number}]"
                elif item.type == "episode":
                    item_info = f"[{item_type} {item.parent.number}:{item.number}]"
                logger.debug(f"{item_info} Parsed '{sorted_tor.parsed_title}' with rank {sorted_tor.rank} ({sorted_tor.infohash}): '{sorted_tor.raw_title}'")
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
            logger.debug(f"Cannot scrape {item.log_string}: Item has been scraped recently, backing off")
            return False
        return True

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