"""
Scraping service for Riven.

This module coordinates multiple torrent scraper services to find streams:
- Comet, Jackett, Mediafusion, Orionoid, Prowlarr, Rarbg, Torrentio, Zilean

Key features:
- Multi-scraper support with concurrent execution
- Stream validation and deduplication
- Failed attempt tracking with automatic failure marking
- Backoff logic (30min, 2h, 5h, 10h based on attempt count)
- Profile-agnostic stream storage (ranking happens in Downloader)

Scrapers discover ALL valid streams without ranking. The Downloader service
handles profile-specific ranking and selection.
"""
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Dict, Generator, List

from loguru import logger

from program.media.item import MediaItem
from program.media.state import States
from program.media.stream import Stream
from program.services.scrapers.shared import validate_and_store_streams
from program.settings.manager import settings_manager

from program.services.scrapers.comet import Comet
from program.services.scrapers.jackett import Jackett
from program.services.scrapers.mediafusion import Mediafusion
from program.services.scrapers.orionoid import Orionoid
from program.services.scrapers.prowlarr import Prowlarr
from program.services.scrapers.rarbg import Rarbg
from program.services.scrapers.torrentio import Torrentio
from program.services.scrapers.zilean import Zilean


class Scraping:
    """
    Main scraping service that coordinates multiple torrent scrapers.

    Manages multiple scraper implementations and discovers streams for MediaItems.
    Streams are validated but NOT ranked - ranking happens per scraping profile
    in the Downloader service.

    Features:
    - Concurrent scraping across all initialized scrapers
    - Stream validation and deduplication
    - Failed attempt tracking with configurable max attempts
    - Backoff logic based on scrape count
    - Profile-agnostic stream storage

    Attributes:
        key: Service identifier ("scraping").
        initialized: True if at least one scraper is initialized.
        settings: Scraping settings from settings_manager.
        max_failed_attempts: Maximum scraping attempts before marking as failed.
        services: List of all scraper service instances.
        initialized_services: List of successfully initialized scrapers.
        imdb_services: List of scrapers that don't require IMDB ID.
    """
    def __init__(self):
        """
        Initialize the Scraping service.

        Initializes all scraper services and filters to only use successfully
        initialized ones.
        """
        self.key = "scraping"
        self.initialized = False
        self.settings = settings_manager.settings.scraping
        self.max_failed_attempts = settings_manager.settings.scraping.max_failed_attempts
        self.services = [
            Comet(),
            Jackett(),
            Mediafusion(),
            Orionoid(),
            Prowlarr(),
            Rarbg(),
            Torrentio(),
            Zilean(),
        ]
        self.initialized_services = [service for service in self.services if service.initialized]
        self.imdb_services = [service for service in self.initialized_services if not service.requires_imdb_id]
        self.initialized = self.validate()
        if not self.initialized:
            return

    def validate(self) -> bool:
        """
        Validate that at least one scraper service is initialized.

        Returns:
            bool: True if at least one scraper is available, False otherwise.
        """
        return len(self.initialized_services) > 0

    def run(self, item: MediaItem) -> Generator[MediaItem, None, None]:
        """
        Scrape an item and store ALL discovered streams without ranking.

        Streams are validated but not ranked - ranking happens per scraping profile
        in the downloader service.
        """

        discovered_streams = self.scrape(item)
        new_streams = [
            stream for stream in discovered_streams.values()
            if stream not in item.streams
            and stream not in item.blacklisted_streams
        ]

        if new_streams:
            item.streams.extend(new_streams)
            if item.failed_attempts > 0:
                item.failed_attempts = 0  # Reset failed attempts on success
            logger.log("SCRAPER", f"Added {len(new_streams)} new unranked streams to {item.log_string}")
        else:
            logger.log("SCRAPER", f"No new streams added for {item.log_string}")

            item.failed_attempts = getattr(item, "failed_attempts", 0) + 1
            if self.max_failed_attempts > 0 and item.failed_attempts >= self.max_failed_attempts:
                item.store_state(States.Failed)
                logger.debug(f"Failed scraping after {item.failed_attempts}/{self.max_failed_attempts} tries. Marking as failed: {item.log_string}")
            else:
                logger.debug(f"Failed scraping after {item.failed_attempts}/{self.max_failed_attempts} tries with no new streams: {item.log_string}")

        item.set("scraped_at", datetime.now())
        item.set("scraped_times", item.scraped_times + 1)

        yield item

    def scrape(self, item: MediaItem, verbose_logging = True) -> Dict[str, Stream]:
        """
        Scrape an item using all available scrapers concurrently.

        Runs all initialized scrapers in parallel and aggregates results.
        Results are validated and deduplicated but NOT ranked.

        Args:
            item: MediaItem to scrape for.
            verbose_logging: Whether to log trace messages for validation.

        Returns:
            Dict[str, Stream]: Dictionary of infohash -> Stream (unranked).
        """

        results: Dict[str, str] = {}
        results_lock = threading.RLock()

        imdb_id = item.get_top_imdb_id()
        if imdb_id:
            available_services = self.imdb_services
        else:
            available_services = self.services

        def run_service(svc, it) -> None:
            """Run a single service and update the results."""
            service_results = svc.run(it)
            if not isinstance(service_results, dict):
                logger.error(f"Service {svc.__class__.__name__} returned invalid results: {service_results}")
                return

            with results_lock:
                try:
                    results.update(service_results)
                except Exception as e:
                    logger.exception(f"Error updating results for {svc.__class__.__name__}: {e}")

        with ThreadPoolExecutor(thread_name_prefix="ScraperService_", max_workers=max(1, len(available_services))) as executor:
            futures = {executor.submit(run_service, service, item): service.key for service in available_services}
            for future in as_completed(futures):
                try:
                    future.result()
                except Exception as e:
                    logger.error(f"Exception occurred while running service {futures[future]}: {e}")

        if not results:
            logger.log("NOT_FOUND", f"No streams to process for {item.log_string}")
            return {}

        return validate_and_store_streams(item, results, verbose_logging)

    @staticmethod
    def should_submit(item: MediaItem) -> bool:
        """
        Check if an item should be submitted for scraping.

        Implements backoff logic based on scrape count:
        - 0-1 scrapes: 30 minutes
        - 2-5 scrapes: after_2 hours (configurable)
        - 6-10 scrapes: after_5 hours (configurable)
        - 10+ scrapes: after_10 hours (configurable)

        Args:
            item: MediaItem to check.

        Returns:
            bool: True if item should be scraped, False otherwise.
        """
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
