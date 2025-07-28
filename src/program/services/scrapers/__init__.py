from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError
import threading
import time
from datetime import datetime
from typing import Dict, Generator, List, Tuple

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

        # Service performance tracking for dynamic ordering
        self.service_stats = {}  # service_name -> {"response_times": [], "success_rate": float, "last_used": timestamp}
        self._stats_lock = threading.Lock()

        # Initialize stats for all services
        for service_name in self.services.keys():
            self.service_stats[service_name.__name__] = {
                "response_times": [],
                "success_count": 0,
                "total_requests": 0,
                "last_used": 0,
                "avg_response_time": float('inf')  # Start with worst case
            }
        self.initialized = self.validate()
        if not self.initialized:
            return

    def _update_service_stats(self, service_name: str, response_time: float, success: bool):
        """Update performance statistics for a service with optimized locking."""
        # Minimize time in critical section by preparing data outside lock
        current_time = time.time()

        # Use a shorter critical section
        with self._stats_lock:
            stats = self.service_stats.get(service_name)
            if stats is None:
                # Initialize stats if not exists
                stats = {
                    "response_times": [],
                    "success_count": 0,
                    "total_requests": 0,
                    "last_used": 0,
                    "avg_response_time": float('inf')
                }
                self.service_stats[service_name] = stats

            # Quick updates in critical section
            stats["response_times"].append(response_time)
            if len(stats["response_times"]) > 20:
                stats["response_times"].pop(0)

            stats["total_requests"] += 1
            if success:
                stats["success_count"] += 1

            stats["last_used"] = current_time

            # Calculate average (this is the most expensive operation)
            if stats["response_times"]:
                stats["avg_response_time"] = sum(stats["response_times"]) / len(stats["response_times"])

    def _batch_update_service_stats(self, updates: list[tuple[str, float, bool]]):
        """
        Batch update service statistics to reduce lock contention.

        Args:
            updates: List of (service_name, response_time, success) tuples
        """
        if not updates:
            return

        current_time = time.time()

        # Single lock acquisition for all updates
        with self._stats_lock:
            for service_name, response_time, success in updates:
                stats = self.service_stats.get(service_name)
                if stats is None:
                    stats = {
                        "response_times": [],
                        "success_count": 0,
                        "total_requests": 0,
                        "last_used": 0,
                        "avg_response_time": float('inf')
                    }
                    self.service_stats[service_name] = stats

                # Quick updates
                stats["response_times"].append(response_time)
                if len(stats["response_times"]) > 20:
                    stats["response_times"].pop(0)

                stats["total_requests"] += 1
                if success:
                    stats["success_count"] += 1

                stats["last_used"] = current_time

                if stats["response_times"]:
                    stats["avg_response_time"] = sum(stats["response_times"]) / len(stats["response_times"])

    def _get_service_priority_score(self, service_name: str) -> float:
        """Calculate priority score for a service (higher = better priority)."""
        # Read stats without locking (dict access is atomic in CPython)
        # This is safe because we only read, and dict.get() is atomic
        stats = self.service_stats.get(service_name, {})

        if stats.get("total_requests", 0) == 0:
            # New service - give it medium priority
            return 50.0

        # Calculate success rate (0-100)
        success_rate = (stats.get("success_count", 0) / stats.get("total_requests", 1)) * 100

        # Calculate speed score (inverse of response time, normalized)
        avg_response_time = stats.get("avg_response_time", float('inf'))
        if avg_response_time == float('inf'):
            speed_score = 0
        else:
            # Normalize: 1 second = 100 points, 10 seconds = 10 points
            speed_score = max(0, 100 - (avg_response_time * 10))

        # Calculate recency bonus (services used recently get slight boost)
        last_used = stats.get("last_used", 0)
        recency_bonus = max(0, 10 - ((time.time() - last_used) / 3600))  # Decay over hours

        # Combined score: success rate (60%) + speed (30%) + recency (10%)
        total_score = (success_rate * 0.6) + (speed_score * 0.3) + (recency_bonus * 0.1)

        return total_score

    def _order_services_by_performance(self, services: Dict) -> List[Tuple[str, object]]:
        """Order services by performance metrics (best first)."""
        service_items = list(services.items())

        # Sort by priority score (descending)
        service_items.sort(
            key=lambda x: self._get_service_priority_score(x[1].__class__.__name__),
            reverse=True
        )

        return service_items

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
        """Scrape an item with optimized concurrent processing and minimal locking."""
        # Use lock-free approach: collect results from futures directly
        # This eliminates the need for a shared results dictionary and lock

        imdb_id = item.get_top_imdb_id()
        available_services = self.services if imdb_id else self.keyword_services

        # Filter initialized services upfront
        initialized_services = {name: service for name, service in available_services.items() if service.initialized}

        if not initialized_services:
            logger.log("NOT_FOUND", f"No initialized services available for {item.log_string}")
            return {}

        # Order services by performance (best first)
        ordered_services = self._order_services_by_performance(initialized_services)

        def run_service(service_name, service, item):
            """Run a single scraper service with performance tracking."""
            start_time = time.time()
            success = False

            try:
                service_results = service.run(item)
                if not isinstance(service_results, dict):
                    logger.error(f"Service {service_name} returned invalid results: {service_results}")
                    return {}

                success = len(service_results) > 0  # Success if we got results
                return service_results

            except Exception as e:
                logger.error(f"Service {service_name} failed: {e}")
                return {}

            finally:
                # Update performance stats
                response_time = time.time() - start_time
                self._update_service_stats(service_name, response_time, success)

        # Optimize thread pool size based on number of services and system capabilities
        max_workers = min(len(ordered_services), 8)  # Limit to 8 concurrent scrapers max

        # Use staggered execution: start with best services first, then add others
        fast_services = ordered_services[:3]  # Top 3 performers
        remaining_services = ordered_services[3:]

        with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="scraper") as executor:
            # Start with fast services first
            future_to_service = {}

            # Submit fast services immediately
            for service_name, service in fast_services:
                future = executor.submit(run_service, service.__class__.__name__, service, item)
                future_to_service[future] = service.__class__.__name__

            # Submit remaining services with slight delay to prioritize fast ones
            if remaining_services:
                time.sleep(0.1)  # Small delay to let fast services start
                for service_name, service in remaining_services:
                    future = executor.submit(run_service, service.__class__.__name__, service, item)
                    future_to_service[future] = service.__class__.__name__

            # Collect results with timeout using lock-free approach
            service_results_list = []
            for future in as_completed(future_to_service, timeout=60):  # 60 second timeout
                try:
                    service_results = future.result(timeout=10)  # 10 second timeout per service
                    if service_results:
                        service_results_list.append(service_results)
                except Exception as e:
                    service_name = future_to_service[future]
                    logger.error(f"Exception occurred while running service {service_name}: {e}")

        # Merge results without locking (done in main thread)
        results = {}
        for service_result in service_results_list:
            results.update(service_result)

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
        """Check if an item should be submitted for scraping with adaptive intervals."""
        settings = settings_manager.settings.scraping

        # Use adaptive polling intervals based on data volatility
        scrape_time = Scraping._get_adaptive_scrape_interval(item)

        is_scrapeable = not item.scraped_at or (datetime.now() - item.scraped_at).total_seconds() > scrape_time
        if not is_scrapeable:
            return False

        if settings.max_failed_attempts > 0 and item.failed_attempts >= settings.max_failed_attempts:
            return False

        return True

    @staticmethod
    def _get_adaptive_scrape_interval(item: MediaItem) -> int:
        """
        Get adaptive scraping interval based on item characteristics and data volatility.
        Returns interval in seconds.
        """
        settings = settings_manager.settings.scraping
        base_interval = 30 * 60  # 30 minutes base

        # Factor in scrape attempts (exponential backoff for failed items)
        if item.scraped_times >= 2 and item.scraped_times <= 5:
            base_interval = settings.after_2 * 60 * 60
        elif item.scraped_times > 5 and item.scraped_times <= 10:
            base_interval = settings.after_5 * 60 * 60
        elif item.scraped_times > 10:
            base_interval = settings.after_10 * 60 * 60

        # Adaptive factors based on item characteristics
        multiplier = 1.0

        # Recently requested items need more frequent checks
        if item.requested_at and (datetime.now() - item.requested_at).days < 1:
            multiplier *= 0.5  # Check twice as often

        # Items with recent activity (new streams found) need more frequent checks
        if hasattr(item, 'streams') and item.streams:
            last_stream_time = max((s.created_at for s in item.streams if hasattr(s, 'created_at')), default=None)
            if last_stream_time and (datetime.now() - last_stream_time).hours < 6:
                multiplier *= 0.7  # Check more frequently if streams were recently found

        # Failed items get exponential backoff
        if item.failed_attempts > 0:
            multiplier *= (1.5 ** item.failed_attempts)  # Exponential backoff

        # Items in active states need more frequent checks
        if item.last_state in [States.Requested, States.Indexed, States.Scraped]:
            multiplier *= 0.8  # Check more frequently for active items
        elif item.last_state in [States.Downloaded, States.Symlinked, States.Completed]:
            multiplier *= 2.0  # Check less frequently for completed items

        # Cap the interval between 5 minutes and 24 hours
        final_interval = max(300, min(86400, int(base_interval * multiplier)))

        return final_interval
