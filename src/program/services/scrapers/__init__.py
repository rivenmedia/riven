import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Dict, List, TYPE_CHECKING

from loguru import logger

from program.media.item import MediaItem
from program.media.state import States
from program.media.stream import Stream
from program.services.scrapers.comet import Comet
from program.services.scrapers.jackett import Jackett
from program.services.scrapers.mediafusion import Mediafusion
from program.services.scrapers.orionoid import Orionoid
from program.services.scrapers.prowlarr import Prowlarr
from program.services.scrapers.rarbg import Rarbg
from program.services.scrapers.shared import _parse_results
from program.services.scrapers.torrentio import Torrentio
from program.services.scrapers.zilean import Zilean
from program.settings.manager import settings_manager

if TYPE_CHECKING:
    from program.managers.event_manager import EventManager

class TemporaryScrapeUnavailable(Exception):
    """All providers failed temporarily; let EventManager requeue."""
    pass

class Scraping:
    def __init__(self, event_manager: "EventManager"):
        self.key = "scraping"
        self.em = event_manager
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

    def run(self, item: MediaItem):
        """Scrape an item and yield it when complete."""
        try:
            sorted_streams = self.scrape(item)
            new_streams = [
                stream
                for stream in sorted_streams.values()
                if stream not in item.streams and stream not in item.blacklisted_streams
            ]

            if new_streams:
                item.streams.extend(new_streams)
                item.failed_attempts = min(
                    item.failed_attempts, 0
                )  # Reset failed attempts on success
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
        except Exception as e:
            logger.error(f"Fatal error during scraping of {item.log_string}: {type(e).__name__}: {e}")
            # Re-raise so EventManager can handle the retry logic
            raise

    def scrape(self, item: MediaItem, verbose_logging=True) -> Dict[str, Stream]:
        """Scrape an item."""

        results: Dict[str, str] = {}
        results_lock = threading.RLock()

        def run_service(svc, it) -> None:
            """Run a single service and update the results."""
            try:
                service_results = svc.run(it)
                if not isinstance(service_results, dict):
                    logger.error(
                        f"Service {svc.__class__.__name__} returned invalid results: {service_results}"
                    )
                    return

                # The 'with results_lock:' statement guarantees lock release even if an exception occurs
                # inside the block, so this is safe from deadlock scenarios
                with results_lock:
                    try:
                        results.update(service_results)
                    except Exception as e:
                        logger.error(
                            f"Error updating results for {svc.__class__.__name__}: {e}"
                        )
                        # Lock is automatically released here by 'with' statement
            except Exception as e:
                # Catch any unhandled exceptions from svc.run() to prevent thread crashes
                # This is placed OUTSIDE the lock context to avoid any potential lock issues
                logger.error(
                    f"Critical error in {svc.__class__.__name__}.run(): {type(e).__name__}: {e}"
                )
                # Note: We don't re-raise here - this allows other scrapers to continue
                # and prevents the entire scraping operation from failing

        try:
            had_error = False
            with ThreadPoolExecutor(
                thread_name_prefix="ScraperService_",
                max_workers=max(1, len(self.initialized_services)),
            ) as executor:
                if self.em._shutting_down:
                    logger.debug(
                        "EventManager is shutting down, skipping scraper sub-tasks."
                    )
                    return {}  # Abort before submitting new futures
                futures = {
                    executor.submit(run_service, service, item): service.key
                    for service in self.initialized_services
                }
                for future in as_completed(futures):
                    svc_key = futures[future]
                    try:
                        future.result()
                    except Exception as e:
                        had_error = True
                        logger.error(f"Exception occurred while running service {svc_key}: {e}")
                        # keep going to collect other providers
                        continue

            if not results and had_error:
                logger.debug(
                    f"No results, retrying due to scraper error(s) for {item.log_string}"
                )
                raise TemporaryScrapeUnavailable(
                    f"All scraper services failed temporarily for {item.log_string}"
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
        except RuntimeError as re:  # Guard against shutdown-related executor errors
            logger.debug(f"Scraper executor setup skipped: {re}")
            return {}

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
