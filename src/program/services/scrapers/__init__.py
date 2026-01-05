import threading
from collections.abc import Generator
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from queue import Queue, Empty

from loguru import logger

from program.media.item import MediaItem
from program.media.state import States
from program.media.stream import Stream
from program.services.scrapers.shared import parse_results
from program.settings import settings_manager

from program.services.scrapers.comet import Comet
from program.services.scrapers.jackett import Jackett
from program.services.scrapers.mediafusion import Mediafusion
from program.services.scrapers.orionoid import Orionoid
from program.services.scrapers.prowlarr import Prowlarr
from program.services.scrapers.rarbg import Rarbg
from program.services.scrapers.torrentio import Torrentio
from program.services.scrapers.zilean import Zilean
from program.core.runner import MediaItemGenerator, Runner, RunnerResult
from program.settings.models import Observable, ScraperModel
from program.services.scrapers.base import ScraperService
from program.services.scrapers.models import RankingOverrides
from program.utils.request import CircuitBreakerOpen


class Scraping(Runner[ScraperModel, ScraperService[Observable]]):
    def __init__(self):
        super().__init__()

        self.initialized = False
        self.settings = settings_manager.settings.scraping
        self.max_failed_attempts = (
            settings_manager.settings.scraping.max_failed_attempts
        )

        self.services = {
            Comet: Comet(),
            Jackett: Jackett(),
            Mediafusion: Mediafusion(),
            Orionoid: Orionoid(),
            Prowlarr: Prowlarr(),
            Rarbg: Rarbg(),
            Torrentio: Torrentio(),
            Zilean: Zilean(),
        }

        self.initialized_services = [
            service for service in self.services.values() if service.initialized
        ]
        self.initialized = self.validate()

        if not self.initialized:
            return

    def validate(self) -> bool:
        """Validate that at least one scraper service is initialized."""

        return len(self.initialized_services) > 0

    def run(self, item: MediaItem) -> MediaItemGenerator:
        """Scrape an item."""

        # Check if item has stored ranking overrides (set via auto scrape)
        ranking_overrides = None
        if item.ranking_overrides is not None and len(item.ranking_overrides) > 0:
            ranking_overrides = RankingOverrides.model_validate(item.ranking_overrides)

        sorted_streams = self.scrape(item, ranking_overrides=ranking_overrides)
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

            item.failed_attempts += 1

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

        yield RunnerResult(media_items=[item])

    def scrape(
        self,
        item: MediaItem,
        verbose_logging: bool = True,
        ranking_overrides: RankingOverrides | None = None,
        manual: bool = False,
    ) -> dict[str, Stream]:
        """Scrape an item."""

        all_streams = dict[str, Stream]()

        # Consume the streaming generator to get all results
        for _, streams in self.scrape_streaming(item, ranking_overrides, manual):
            all_streams.update(streams)

        if not all_streams:
            logger.log("NOT_FOUND", f"No streams to process for {item.log_string}")
            return {}

        if verbose_logging and settings_manager.settings.log_level:
            top_results = list(all_streams.values())[:10]

            logger.debug(
                f"Displaying top {len(top_results)} results for {item.log_string}"
            )

            for stream in top_results:
                logger.debug(
                    f"[Rank: {stream.rank}][Res: {stream.parsed_data.resolution}] {stream.raw_title} ({stream.infohash})"
                )

        return all_streams

    def scrape_streaming(
        self,
        item: MediaItem,
        ranking_overrides: RankingOverrides | None = None,
        manual: bool = False,
    ) -> Generator[tuple[str, dict[str, Stream]], None, None]:
        """
        Scrape an item and yield results incrementally as each scraper finishes.

        Yields:
            Tuples of (service_name, parsed_streams_dict) as each service completes.
        """

        results_queue: Queue[tuple[str, dict[str, str]]] = Queue()
        all_raw_results = dict[str, str]()
        results_lock = threading.RLock()

        def run_service_streaming(
            svc: "ScraperService[Observable]", item: MediaItem
        ) -> None:
            """Run a single service and put results in the queue."""
            try:
                service_results = svc.run(item)
                if service_results:
                    results_queue.put((svc.key, service_results))
                else:
                    results_queue.put((svc.key, {}))
            except CircuitBreakerOpen:
                logger.debug(f"Circuit breaker OPEN for {svc.key}")
                results_queue.put((svc.key, {}))
            except Exception as e:
                logger.error(f"Error running {svc.key}: {e}")
                results_queue.put((svc.key, {}))

        # Start all scrapers in thread pool
        with ThreadPoolExecutor(
            thread_name_prefix="ScraperServiceStreaming_",
            max_workers=max(1, len(self.initialized_services)),
        ) as executor:
            futures = {
                executor.submit(run_service_streaming, service, item): service.key
                for service in self.initialized_services
            }

            services_completed = 0
            total_services = len(futures)

            # Yield results as they complete
            while services_completed < total_services:
                try:
                    # Wait for next result with timeout
                    service_name, raw_results = results_queue.get(timeout=60.0)
                    services_completed += 1

                    if raw_results:
                        # Merge into all results for proper ranking
                        with results_lock:
                            all_raw_results.update(raw_results)

                        # Parse and rank only the new streams
                        parsed_streams = parse_results(
                            item,
                            all_raw_results,
                            ranking_overrides=ranking_overrides,
                            manual=manual,
                        )

                        yield (service_name, parsed_streams)
                    else:
                        # Still yield empty to signal progress
                        yield (service_name, {})

                except Empty:
                    logger.warning("Timeout waiting for scraper results")
                    break

    def should_submit(self, item: MediaItem) -> bool:
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
