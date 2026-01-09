import threading
from collections.abc import Generator
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from queue import Empty, Queue

from loguru import logger

from program.core.runner import MediaItemGenerator, Runner, RunnerResult
from program.media.item import MediaItem
from program.media.state import States
from program.media.stream import Stream
from program.services.scrapers.aiostreams import AIOStreams
from program.services.scrapers.base import ScraperService
from program.services.scrapers.comet import Comet
from program.services.scrapers.jackett import Jackett
from program.services.scrapers.mediafusion import Mediafusion
from program.services.scrapers.models import RankingOverrides
from program.services.scrapers.orionoid import Orionoid
from program.services.scrapers.prowlarr import Prowlarr
from program.services.scrapers.rarbg import Rarbg
from program.services.scrapers.shared import parse_results
from program.services.scrapers.torrentio import Torrentio
from program.services.scrapers.zilean import Zilean
from program.settings import settings_manager
from program.settings.models import Observable, ScraperModel


class Scraping(Runner[ScraperModel, ScraperService[Observable]]):
    def __init__(self):
        super().__init__()
        self.initialized = False
        self.settings = settings_manager.settings.scraping
        self.max_failed_attempts = self.settings.max_failed_attempts

        self.services = {
            AIOStreams: AIOStreams(),
            Comet: Comet(),
            Jackett: Jackett(),
            Mediafusion: Mediafusion(),
            Orionoid: Orionoid(),
            Prowlarr: Prowlarr(),
            Rarbg: Rarbg(),
            Torrentio: Torrentio(),
            Zilean: Zilean(),
        }

        self.initialized_services = [s for s in self.services.values() if s.initialized]
        self.initialized = len(self.initialized_services) > 0

    def run(self, item: MediaItem, relaxed: bool = False, overrides: dict | None = None, max_bitrate_override: int | None = None) -> MediaItemGenerator:
        """Scrape an item and update its streams."""
        sorted_streams = self.scrape(item, relaxed=relaxed, overrides=overrides, max_bitrate_override=max_bitrate_override)
        new_streams = [
            s for s in sorted_streams.values()
            if s not in item.streams and s not in item.blacklisted_streams
        ]

        if new_streams:
            item.streams.extend(new_streams)
            item.failed_attempts = 0
            item.store_state(States.Scraped)
            logger.log("SCRAPER", f"Added {len(new_streams)} streams to {item.log_string}")
        else:
            logger.log("SCRAPER", f"No new streams for {item.log_string}")
            item.failed_attempts += 1
            if self.max_failed_attempts > 0 and item.failed_attempts >= self.max_failed_attempts:
                item.store_state(States.Failed)

        item.set("scraped_at", datetime.now())
        item.set("scraped_times", item.scraped_times + 1)
        yield RunnerResult(media_items=[item])

    def scrape(self, item: MediaItem, relaxed: bool = False, overrides: dict | None = None, max_bitrate_override: int | None = None) -> dict[str, Stream]:
        """Scrape an item and return all found streams."""
        all_streams: dict[str, Stream] = {}
        for _, streams in self.scrape_streaming(item, relaxed, overrides=overrides, max_bitrate_override=max_bitrate_override):
            all_streams.update(streams)

        if not all_streams:
            logger.log("NOT_FOUND", f"No streams for {item.log_string}")
        return all_streams

    def scrape_streaming(
        self, item: MediaItem, relaxed: bool = False, overrides: dict | None = None, max_bitrate_override: int | None = None
    ) -> Generator[tuple[str, dict[str, Stream]], None, None]:
        """Scrape an item and yield results as each scraper finishes."""
        queue: Queue[tuple[str, dict[str, str]]] = Queue()
        all_raw: dict[str, str] = {}
        lock = threading.RLock()

        def run_service(svc: ScraperService, item: MediaItem):
            try:
                results = svc.run(item)
                queue.put((svc.key, results or {}))
            except CircuitBreakerOpen:
                queue.put((svc.key, {}))
            except Exception as e:
                logger.error(f"Error in {svc.key}: {e}")
                queue.put((svc.key, {}))

        with ThreadPoolExecutor(
            thread_name_prefix="Scraper_",
            max_workers=max(1, len(self.initialized_services)),
        ) as executor:
            for svc in self.initialized_services:
                executor.submit(run_service, svc, item)

            for _ in range(len(self.initialized_services)):
                try:
                    name, raw = queue.get(timeout=60.0)
                    if raw:
                        with lock:
                            all_raw.update(raw)
                        parsed = parse_results(item, all_raw, relaxed_validation=relaxed, overrides=overrides, max_bitrate_override=max_bitrate_override)
                        yield (name, parsed)
                    else:
                        yield (name, {})
                except Empty:
                    break

    def should_submit(self, item: MediaItem) -> bool:
        """Check if an item should be submitted for scraping."""
        settings = self.settings
        scrape_time = 30 * 60  # 30 minutes default

        if 2 <= item.scraped_times <= 5:
            scrape_time = settings.after_2 * 3600
        elif 5 < item.scraped_times <= 10:
            scrape_time = settings.after_5 * 3600
        elif item.scraped_times > 10:
            scrape_time = settings.after_10 * 3600

        if item.scraped_at and (datetime.now() - item.scraped_at).total_seconds() <= scrape_time:
            return False

        if settings.max_failed_attempts > 0 and item.failed_attempts >= settings.max_failed_attempts:
            return False

        if item.is_parent_blocked():
            return False

        return True
