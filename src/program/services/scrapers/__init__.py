import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Dict, Generator, List

from loguru import logger

from program.media.item import MediaItem
from program.media.state import States
from program.media.stream import Stream
from program.services.scrapers.shared import _parse_results
from program.settings.manager import settings_manager

from program.services.scrapers.comet import Comet
from program.services.scrapers.jackett import Jackett
from program.services.scrapers.mediafusion import Mediafusion
from program.services.scrapers.orionoid import Orionoid
from program.services.scrapers.prowlarr import Prowlarr
from program.services.scrapers.rarbg import Rarbg
from program.services.scrapers.torrentio import Torrentio
from program.services.scrapers.zilean import Zilean
from program.core.runner import Runner
from program.settings.models import ScraperModel


class Scraping(Runner[ScraperModel]):
    def __init__(self):
        self.key = "scraping"
        self.initialized = False
        self.settings = settings_manager.settings.scraping
        self.max_failed_attempts = (
            settings_manager.settings.scraping.max_failed_attempts
        )
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
        self.initialized_services = [
            service for service in self.services if service.initialized
        ]
        self.initialized = self.validate()
        if not self.initialized:
            return

    def validate(self) -> bool:
        """Validate that at least one scraper service is initialized."""
        return len(self.initialized_services) > 0

    def run(self, item: MediaItem) -> Generator[MediaItem, None, None]:
        """Scrape an item."""

        sorted_streams = self.scrape(item)
        new_streams = [
            stream
            for stream in sorted_streams.values()
            if stream not in item.streams and stream not in item.blacklisted_streams
        ]

        if new_streams:
            item.streams.extend(new_streams)
            if item.failed_attempts > 0:
                item.failed_attempts = 0  # Reset failed attempts on success
            logger.log(
                "SCRAPER", f"Added {len(new_streams)} new streams to {item.log_string}"
            )
        else:
            logger.log("SCRAPER", f"No new streams added for {item.log_string}")

            item.failed_attempts = getattr(item, "failed_attempts", 0) + 1
            if (
                self.max_failed_attempts > 0
                and item.failed_attempts >= self.max_failed_attempts
            ):
                item.store_state(States.Failed)
                logger.debug(
                    f"Failed scraping after {item.failed_attempts}/{self.max_failed_attempts} tries. Marking as failed: {item.log_string}"
                )
            else:
                logger.debug(
                    f"Failed scraping after {item.failed_attempts}/{self.max_failed_attempts} tries with no new streams: {item.log_string}"
                )

        item.set("scraped_at", datetime.now())
        item.set("scraped_times", item.scraped_times + 1)

        yield item

    def scrape(self, item: MediaItem, verbose_logging=True) -> Dict[str, Stream]:
        """Scrape an item."""

        results: Dict[str, str] = {}
        results_lock = threading.RLock()

        def run_service(svc, it) -> None:
            """Run a single service and update the results."""
            service_results = svc.run(it)
            if not isinstance(service_results, dict):
                logger.error(
                    f"Service {svc.__class__.__name__} returned invalid results: {service_results}"
                )
                return

            with results_lock:
                try:
                    results.update(service_results)
                except Exception as e:
                    logger.exception(
                        f"Error updating results for {svc.__class__.__name__}: {e}"
                    )

        with ThreadPoolExecutor(
            thread_name_prefix="ScraperService_",
            max_workers=max(1, len(self.initialized_services)),
        ) as executor:
            futures = {
                executor.submit(run_service, service, item): service.key
                for service in self.initialized_services
            }
            for future in as_completed(futures):
                try:
                    future.result()
                except Exception as e:
                    logger.error(
                        f"Exception occurred while running service {futures[future]}: {e}"
                    )

        if not results:
            logger.log("NOT_FOUND", f"No streams to process for {item.log_string}")
            return {}

        sorted_streams: Dict[str, Stream] = _parse_results(
            item, results, verbose_logging
        )
        if sorted_streams and (verbose_logging and settings_manager.settings.log_level):
            top_results: List[Stream] = list(sorted_streams.values())[:10]
            logger.debug(
                f"Displaying top {len(top_results)} results for {item.log_string}"
            )
            for stream in top_results:
                logger.debug(
                    f"[Rank: {stream.rank}][Res: {stream.parsed_data.resolution}] {stream.raw_title} ({stream.infohash})"
                )

        return sorted_streams

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

        is_scrapeable = (
            not item.scraped_at
            or (datetime.now() - item.scraped_at).total_seconds() > scrape_time
        )
        if not is_scrapeable:
            return False

        if (
            settings.max_failed_attempts > 0
            and item.failed_attempts >= settings.max_failed_attempts
        ):
            return False

        return True
