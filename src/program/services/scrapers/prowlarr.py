""" Prowlarr scraper module """

import concurrent.futures
import queue
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import regex
from loguru import logger
from pydantic import BaseModel
from requests import ReadTimeout, RequestException

from program.media.item import MediaItem
from program.services.scrapers.shared import ScraperRequestHandler, _get_infohash_from_torrent_url
from program.settings.manager import settings_manager
from program.utils.request import (
    HttpMethod,
    RateLimitExceeded,
    get_http_adapter,
    get_rate_limit_params,
    create_service_session
)


class SearchParams(BaseModel):
    search: list[str]
    movie: list[str]
    tv: list[str]

class Category(BaseModel):
    name: str
    type: str
    ids: list[int]

class Capabilities(BaseModel):
    supports_raw_search: bool
    categories: list[Category]
    search_params: SearchParams

class Indexer(BaseModel):
    id: int
    name: str
    enable: bool
    protocol: str
    capabilities: Capabilities

ANIME_ONLY_INDEXERS = ("Nyaa.si", "SubsPlease", "Anidub", "Anidex")
INFOHASH_PATTERN = regex.compile(r"btih:([A-Fa-f0-9]{40})")


class Prowlarr:
    """Scraper for `Prowlarr`"""

    def __init__(self):
        self.key = "prowlarr"
        self.settings = settings_manager.settings.scraping.prowlarr
        self.api_key = self.settings.api_key
        self.indexers = []
        self.headers = {
            "Content-Type": "application/json",
            "X-Api-Key": self.api_key,
        }
        self.timeout = self.settings.timeout
        self.request_handler = None
        self.indexer_handler = None
        self.last_indexer_scan = None
        self.initialized = self.validate()
        if not self.initialized and not self.api_key:
            return
        logger.success("Prowlarr initialized!")

    def _create_session(self, pool_connections: int = 1, pool_maxsize: int = 1) -> ScraperRequestHandler:
        rate_limit_params = get_rate_limit_params(max_calls=1, period=self.settings.limiter_seconds) if self.settings.ratelimit else None
        http_adapter = get_http_adapter(pool_connections=pool_connections, pool_maxsize=pool_maxsize)
        session = create_service_session(rate_limit_params=rate_limit_params, session_adapter=http_adapter)
        return ScraperRequestHandler(session)

    def validate(self) -> bool:
        """Validate Prowlarr settings."""
        if not self.settings.enabled:
            return False
        if self.settings.url and self.settings.api_key:
            self.api_key = self.settings.api_key
            try:
                if not isinstance(self.timeout, int) or self.timeout <= 0:
                    logger.error("Prowlarr timeout is not set or invalid.")
                    return False
                if not isinstance(self.settings.ratelimit, bool):
                    logger.error("Prowlarr ratelimit must be a valid boolean.")
                    return False
                self.indexer_handler = self._create_session()
                self.indexers = self.get_indexers()
                self.request_handler = self._create_session(pool_connections=len(self.indexers), pool_maxsize=len(self.indexers))
                if not self.indexers:
                    logger.error("No Prowlarr indexers configured.")
                    return False
                return True
            except ReadTimeout:
                logger.error("Prowlarr request timed out. Check your indexers, they may be too slow to respond.")
                return False
            except Exception as e:
                logger.error(f"Prowlarr failed to initialize with API Key: {e}")
                return False
        logger.warning("Prowlarr is not configured and will not be used.")
        return False

    def get_indexers(self) -> list[Indexer]:
        statuses = self.indexer_handler.execute(HttpMethod.GET, f"{self.settings.url}/api/v1/indexerstatus", timeout=15, headers=self.headers)
        response = self.indexer_handler.execute(HttpMethod.GET, f"{self.settings.url}/api/v1/indexer", timeout=15, headers=self.headers)
        data = response.data
        statuses = statuses.data
        indexers = []
        for indexer_data in data:
            id = indexer_data.id
            if statuses:
                status = next((x for x in statuses if x.indexerId == id), None)
                if status and status.disabledTill > datetime.now().isoformat():
                    disabled_until = datetime.fromisoformat(status.disabledTill).strftime('%Y-%m-%d %H:%M')
                    logger.debug(f"Indexer {indexer_data.name} is disabled until {disabled_until}, skipping")
                    continue

            name = indexer_data.name
            enable = indexer_data.enable
            if not enable:
                logger.debug(f"Indexer {name} is disabled, skipping")
                continue

            protocol = indexer_data.protocol
            if protocol != "torrent":
                logger.debug(f"Indexer {name} is not a torrent indexer, skipping")
                continue

            caps = []
            for cap in indexer_data.capabilities.categories:
                if "TV" in cap.name:
                    category = next((x for x in caps if "TV" in x.name), None)
                    if category:
                        category.ids.append(cap.id)
                    else:
                        caps.append(Category(name="TV", type="tv", ids=[cap.id]))
                elif "Movies" in cap.name:
                    category = next((x for x in caps if "Movies" in x.name), None)
                    if category:
                        category.ids.append(cap.id)
                    else:
                        caps.append(Category(name="Movies", type="movie", ids=[cap.id]))
                elif "Anime" in cap.name:
                    category = next((x for x in caps if "Anime" in x.name), None)
                    if category:
                        category.ids.append(cap.id)
                    else:
                        caps.append(Category(name="Anime", type="anime", ids=[cap.id]))

            if not caps:
                logger.warning(f"No valid capabilities found for indexer {name}. Consider removing this indexer.")
                continue

            search_params = SearchParams(
                search=list(set(indexer_data.capabilities.searchParams)),
                movie=list(set(indexer_data.capabilities.movieSearchParams)),
                tv=list(set(indexer_data.capabilities.tvSearchParams))
            )

            capabilities = Capabilities(
                supports_raw_search=indexer_data.capabilities.supportsRawSearch,
                categories=caps,
                search_params=search_params
            )

            indexers.append(Indexer(
                id=id,
                name=name,
                enable=enable,
                protocol=protocol,
                capabilities=capabilities
            ))

        self.last_indexer_scan = datetime.now()
        return indexers

    def _periodic_indexer_scan(self):
        """scan indexers every 30 minutes"""
        previous_count = len(self.indexers)
        if self.last_indexer_scan is None or (datetime.now() - self.last_indexer_scan).total_seconds() > 1800:
            self.indexers = self.get_indexers()
            self.last_indexer_scan = datetime.now()
            if len(self.indexers) != previous_count:
                logger.info(f"Indexers count changed from {previous_count} to {len(self.indexers)}")
                next_scan_time = self.last_indexer_scan + timedelta(seconds=1800)
                logger.info(f"Next scan will be at {next_scan_time.strftime('%Y-%m-%d %H:%M')}")

    def run(self, item: MediaItem) -> Dict[str, str]:
        """Scrape the Prowlarr site for the given media items
        and update the object with scraped streams"""
        if not item:
            return {}

        try:
            return self.scrape(item)
        except RateLimitExceeded:
            logger.debug(f"Prowlarr ratelimit exceeded for item: {item.log_string}")
        except RequestException as e:
            logger.error(f"Prowlarr request exception: {e}")
        except Exception as e:
            logger.exception(f"Prowlarr failed to scrape item with error: {e}")
        return {}

    def scrape(self, item: MediaItem) -> Dict[str, str]:
        """Scrape a single item from all indexers at the same time, return a list of streams"""
        self._periodic_indexer_scan()

        torrents = {}
        start_time = time.time()

        with concurrent.futures.ThreadPoolExecutor(thread_name_prefix="ProwlarrScraper", max_workers=len(self.indexers)) as executor:
            future_to_indexer = {
                executor.submit(self.scrape_indexer, indexer, item): indexer
                for indexer in self.indexers
            }

            for future in future_to_indexer:
                indexer = future_to_indexer[future]
                try:
                    result = future.result(timeout=self.timeout)
                    torrents.update(result)
                except concurrent.futures.TimeoutError:
                    logger.debug(f"Timeout for indexer {indexer.name}, skipping.")
                except Exception as e:
                    logger.error(f"Error processing indexer {indexer.name}: {e}")

        elapsed = time.time() - start_time
        if torrents:
            logger.log("SCRAPER", f"Found {len(torrents)} streams for {item.log_string}")
            logger.debug(f"Total time taken: {elapsed:.2f} seconds")
        else:
            logger.log("NOT_FOUND", f"No streams found for {item.log_string}")

        return torrents

    def build_search_params(self, indexer: Indexer, item: MediaItem) -> dict:
        """Build a search query for a single indexer."""
        params = {}
        item_title = item.get_top_title() if item.type in ("show", "season", "episode") else item.title
        search_params = indexer.capabilities.search_params

        def set_query_and_type(query, search_type):
            params["query"] = query
            params["type"] = search_type

        if item.type == "movie":
            if "imdbId" in search_params.movie:
                set_query_and_type(item.imdb_id, "movie-search")
            if "q" in search_params.movie:
                set_query_and_type(item_title, "movie-search")
            elif "q" in search_params.search:
                set_query_and_type(item_title, "search")
            else:
                raise ValueError(f"Indexer {indexer.name} does not support movie search")

        elif item.type == "show":
            if "imdbId" in search_params.tv:
                set_query_and_type(item.imdb_id, "tv-search")
            elif "q" in search_params.tv:
                set_query_and_type(item_title, "tv-search")
            elif "q" in search_params.search:
                set_query_and_type(item_title, "search")
            else:
                raise ValueError(f"Indexer {indexer.name} does not support show search")

        elif item.type == "season":
            if "q" in search_params.tv:
                set_query_and_type(f"{item_title} S{item.number}", "tv-search")
                if "season" in search_params.tv:
                    params["season"] = item.number
            elif "q" in search_params.search:
                query = f"{item_title} S{item.number}"
                set_query_and_type(query, "search")
            else:
                raise ValueError(f"Indexer {indexer.name} does not support season search")

        elif item.type == "episode":
            if "q" in search_params.tv:
                if "ep" in search_params.tv:
                    query = f"{item_title}"
                    params["season"] = item.parent.number
                    params["ep"] = item.number
                else:
                    query = f"{item.log_string}"
                set_query_and_type(query, "tv-search")
            elif "q" in search_params.search:
                query = f"{item.log_string}"
                set_query_and_type(query, "search")
            else:
                raise ValueError(f"Indexer {indexer.name} does not support episode search")

        categories = {cat_id for category in indexer.capabilities.categories
                      if category.type == item.type or (category.type == "anime" and item.is_anime)
                      for cat_id in category.ids}

        params["indexerIds"] = indexer.id
        params["categories"] = list(categories)
        params["limit"] = 1000
        return params

    def scrape_indexer(self, indexer: Indexer, item: MediaItem) -> dict[str, str]:
        """scrape from a single indexer"""
        if indexer.name in ANIME_ONLY_INDEXERS or "anime" in indexer.name.lower():
            if not item.is_anime:
                logger.debug(f"Indexer {indexer.name} is anime only, skipping")
                return {}

        try:
            params = self.build_search_params(indexer, item)
        except ValueError as e:
            logger.error(f"Failed to build search params for {indexer.name}: {e}")
            return {}

        start_time = time.time()
        response = self.request_handler.execute(HttpMethod.GET, f"{self.settings.url}/api/v1/search", params=params, timeout=self.timeout, headers=self.headers)
        if not response.is_ok:
            message = response.data.message or "Unknown error"
            logger.debug(f"Failed to scrape {indexer.name}: [{response.status_code}] {message}")
            self.indexers.remove(indexer)
            logger.debug(f"Removed indexer {indexer.name} from the list of usable indexers")
            return {}

        data = response.data
        streams = {}
        for torrent in data:
            title = torrent.title
            infohash = torrent.infoHash if hasattr(torrent, "infoHash") else None
            guid = torrent.guid if hasattr(torrent, "guid") else None
            if not infohash and not guid:
                continue
            if not infohash and guid and not guid.endswith(".torrent"):
                infohash = INFOHASH_PATTERN.search(guid)
                if infohash:
                    infohash = infohash.group(1).lower()
                else:
                    continue
            if not infohash and guid and guid.endswith(".torrent"):
                try:
                    infohash = _get_infohash_from_torrent_url(url=guid)
                    if not infohash or not len(infohash) == 40:
                        continue
                    infohash = infohash.lower()
                except Exception:
                    continue

            streams[infohash.lower()] = title

        logger.debug(f"Indexer {indexer.name} found {len(streams)} streams for {item.log_string} in {time.time() - start_time:.2f} seconds")
        return streams
