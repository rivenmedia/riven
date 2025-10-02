import importlib
import inspect
import os
import pkgutil
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Dict, Generator, List

from loguru import logger

from program.media.item import MediaItem
from program.media.state import States
from program.media.stream import Stream
from program.services.scrapers.scraper_base import ScraperService
from program.services.scrapers.shared import _parse_results
from program.settings.manager import settings_manager


class Scraping:
    def __init__(self):
        self.key = "scraping"
        self.initialized = False
        self.settings = settings_manager.settings.scraping
        self.max_failed_attempts = settings_manager.settings.scraping.max_failed_attempts
        self.services: Dict[str, ScraperService] = self._discover_services()
        self.initialized = self.validate()
        if not self.initialized:
            return

    def _discover_services(self) -> Dict[str, ScraperService]:
        """Discover and validate scraper services.

        - Only consider proper subclasses of ScraperService
        - Instantiate each class and call validate()
        - Keep only instances where validate() returns True
        """
        services: Dict[str, ScraperService] = {}
        package_path = os.path.dirname(__file__)
        package_name = __package__ or "program.services.scrapers"

        skip_modules = {"__init__", "shared", "scraper_base", "__pycache__"}
        for module_info in pkgutil.iter_modules([package_path]):
            name = module_info.name
            if name in skip_modules or name.startswith("_"):
                continue
            try:
                module = importlib.import_module(f"{package_name}.{name}")
            except Exception as e:
                logger.error(f"Failed to import scraper module '{name}': {e}")
                continue

            for _, cls in inspect.getmembers(module, inspect.isclass):
                if cls.__module__ != module.__name__:
                    continue
                if cls is ScraperService or not issubclass(cls, ScraperService):
                    continue
                try:
                    instance: ScraperService = cls()  # type: ignore[call-arg]
                except Exception as e:
                    logger.error(f"Failed to instantiate scraper '{cls.__name__}': {e}")
                    continue
                try:
                    if not instance.validate():
                        continue
                    # Mark as initialized to satisfy existing checks
                    # setattr(instance, "initialized", True)
                except Exception as e:
                    logger.error(f"Validation failed for scraper '{cls.__name__}': {e}")
                    continue
                key: str = getattr(instance, "key", cls.__name__.lower())
                services[key] = instance
        return services

    def validate(self) -> bool:
        """Validate that at least one scraper service is initialized."""
        return bool(self.services)

    def run(self, item: MediaItem) -> Generator[MediaItem, None, None]:
        """Scrape an item."""

        sorted_streams = self.scrape(item)
        new_streams = [
            stream for stream in sorted_streams.values()
            if stream not in item.streams
            and stream not in item.blacklisted_streams
        ]

        if new_streams:
            # Ensure streams don't carry stale backrefs to detached parents
            for s in new_streams:
                try:
                    if hasattr(s, "parents") and isinstance(s.parents, list):
                        s.parents.clear()
                    if hasattr(s, "blacklisted_parents") and isinstance(s.blacklisted_parents, list):
                        s.blacklisted_parents.clear()
                except Exception:
                    pass
            item.streams.extend(new_streams)
            if item.failed_attempts > 0:
                item.failed_attempts = 0  # Reset failed attempts on success
            logger.log("SCRAPER", f"Added {len(new_streams)} new streams to {item.log_string}")
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
        """Scrape an item."""

        results: Dict[str, str] = {}
        results_lock = threading.RLock()

        imdb_id = item.get_top_imdb_id()
        if imdb_id:
            available_services = self.services
        else:
            available_services = {k: svc for k, svc in self.services.items() if not getattr(svc, "requires_imdb_id", False)}

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
            futures = {executor.submit(run_service, service, item): key for key, service in available_services.items() if service.initialized}
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
