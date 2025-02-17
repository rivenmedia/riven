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
        """
        Initialize a Scraping instance with configuration settings and scraping services.
        
        This constructor loads scraping-related settings from the settings manager, sets the maximum allowed
        failed scraping attempts, and instantiates both IMDb-based and keyword-based scraping services. The
        combined services are stored in the `services` attribute. The instance is marked as initialized based
        on the result of the `validate()` method; if validation fails, the initialization process exits early.
        
        Attributes:
            key (str): Identifier for the scraping process.
            initialized (bool): Indicates whether any scraping service was successfully initialized.
            settings: Configuration settings for scraping.
            max_failed_attempts (int): Maximum number of consecutive failed scraping attempts before marking an item as failed.
            imdb_services (dict): Dictionary mapping IMDb-based scraping service classes to their instances.
            keyword_services (dict): Dictionary mapping keyword-based scraping service classes to their instances.
            services (dict): Combined dictionary of both IMDb-based and keyword-based scraping service instances.
        """
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
        """
        Run the scraping process for a media item and yield the updated item.
        
        This method checks whether scraping should proceed based on the media item's state and other conditions. If the item's state is Paused, the item is immediately yielded without further processing. Otherwise, the method verifies eligibility with `can_we_scrape` and, if allowed, invokes the `scrape` method to retrieve streaming sources. New streams that are not already present in the item's collection or its blacklist are added; successful scraping resets the failed attempts counter, while absence of new streams increments the failed attempts count. If the number of failed attempts reaches the configured maximum, the item's state is updated to Failed. Finally, the method updates the item's scraping metadata before yielding the modified item.
        
        Parameters:
            item (MediaItem): The media item to be scraped, which should include attributes such as state, failed_attempts, scraped_times, streams, and blacklisted_streams.
        
        Yields:
            MediaItem: The updated media item reflecting new streams, state changes, and updated scrape timestamps and attempt counts.
        
        Notes:
            - Detailed logging is performed at each step for debugging purposes.
            - This method integrates error handling by managing the failed attempts counter and marking the item as Failed when necessary.
        """
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
                if self.max_failed_attempts > 0 and item.failed_attempts >= self.max_failed_attempts:
                    item.store_state(States.Failed)
                    logger.debug(f"Failed scraping after {item.failed_attempts}/{self.max_failed_attempts} tries. Marking as failed: {item.log_string}")
                else:
                    logger.debug(f"Failed scraping after {item.failed_attempts}/{self.max_failed_attempts} tries: {item.log_string}")

                logger.log("NOT_FOUND", f"Scraping returned no good results for {item.log_string}")

            item.set("scraped_at", datetime.now())
            item.set("scraped_times", item.scraped_times + 1)

        yield item

    def scrape(self, item: MediaItem, log = True) -> Dict[str, Stream]:
        """
        Scrapes streaming information for the given media item using available scraping services.
        
        This method spawns a separate thread for each initialized service (selected based on whether the media item has an IMDb ID) to concurrently gather scraping results. Each service's output is verified to be a dictionary, and any infohash keys are normalized to lowercase before being merged into a shared results dictionary. After all services have completed, duplicate results are filtered out, and the aggregated results are parsed into a sorted dictionary of Stream objects. Detailed debug logging is provided if enabled, including information on duplicate removals and the top scraped streams.
        
        Parameters:
            item (MediaItem): The media item to scrape for streaming information.
            log (bool, optional): If True, enables detailed debug logging of the scraping process. Defaults to True.
        
        Returns:
            Dict[str, Stream]: A dictionary mapping normalized infohash strings to their corresponding Stream objects.
        
        Side Effects:
            - Initiates multiple threads to run scraping services concurrently.
            - Updates shared results using a thread-safe mechanism.
            - Logs errors if a service returns invalid results and debug details if logging is enabled.
        """
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
        """
        Determine whether a MediaItem is eligible to be scraped.
        
        This method verifies that the media item has been released and satisfies additional submission criteria as determined by the class's `should_submit` method. If the item is not released, a debug message is logged and the method returns False.
        
        Parameters:
            item (MediaItem): The media item to evaluate for scraping eligibility.
        
        Returns:
            bool: True if the item is eligible for scraping, otherwise False.
        """
        if not item.is_released:
            logger.debug(f"Cannot scrape {item.log_string}: Item is not released")
            return False
        if not cls.should_submit(item):
            return False
        return True

    @staticmethod
    def should_submit(item: MediaItem) -> bool:
        """
        Determine whether a media item is eligible to be submitted for scraping based on its current state and history.
        
        This function checks multiple criteria to decide if a new scraping attempt should be performed for the given media item. The eligibility is determined by the following conditions:
        - The item must be released.
        - The item must not already have an active stream, which could indicate it is being processed in another session.
        - The item must not be blocked either directly or by its parent.
        - A sufficient time interval must have elapsed since the last scraping attempt. The default interval is 30 minutes, which may be extended based on the number of previous scraping attempts:
          - Between 2 and 5 previous attempts, the interval is set according to settings.after_2 (in hours).
          - Between 5 and 10 previous attempts, the interval is set according to settings.after_5 (in hours).
          - More than 10 previous attempts, the interval is set according to settings.after_10 (in hours).
        - The number of failed scraping attempts must be less than the maximum allowed as defined in settings.max_failed_attempts.
        
        Parameters:
            item (MediaItem): The media item to evaluate. It must have attributes such as is_released, active_stream, scraped_times, scraped_at, and failed_attempts, along with a method is_parent_blocked().
        
        Returns:
            bool: True if the item meets all criteria and is eligible for scraping; False otherwise.
        """
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
