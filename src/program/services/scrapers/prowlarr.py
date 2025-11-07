"""Prowlarr scraper module"""

import concurrent.futures
import re
import time
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict

from loguru import logger
from pydantic import BaseModel
from requests import ReadTimeout, RequestException

from program.media.item import MediaItem
from program.services.scrapers.base import ScraperService
from program.settings.manager import settings_manager
from program.utils.request import CircuitBreakerOpen, SmartSession
from program.utils.torrent import extract_infohash, normalize_infohash


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


class QueryStrategy(str, Enum):
    """Enum for different query strategies with priority order"""

    # For anime episodes - prioritize dubbed searches first
    STRICT_SEASON_EPISODE_DUB = "strict_season_episode_dub"  # "Show S02E09 dub"
    EPISODE_NUMBER_DUB = "episode_number_dub"  # "Show 9 dubbed"
    ROMAN_SEASON_EPISODE_DUB = "roman_season_episode_dub"  # "Show IV - 9 dub" (Overlord IV - 9 dub)
    STRICT_SEASON_EPISODE = "strict_season_episode"  # "Show S02E09"
    EPISODE_NUMBER_ONLY = "episode_number_only"  # "Show 9"
    ROMAN_SEASON_EPISODE = "roman_season_episode"  # "Show IV 9" or "Show IV - 9"
    EPISODE_WITH_TITLE = "episode_with_title"  # "Show 9 Episode Title"

    # For anime seasons
    SEASON_NUMBER_DUB = "season_number_dub"  # "Show Season 2 dub"
    ROMAN_SEASON_DUB = "roman_season_dub"  # "Show IV dub" (for Overlord IV dub)
    SEASON_NUMBER = "season_number"  # "Show 2"
    ROMAN_SEASON = "roman_season"  # "Show IV" (for Overlord IV)
    STRICT_SEASON = "strict_season"  # "Show Season 2"
    STRICT_SEASON_NUMBER = "strict_season_number"  # "Show S02"

    # Standard queries
    STANDARD = "standard"  # Default for non-anime or when no alternatives


class QueryResult(BaseModel):
    """Result of a query attempt"""

    query: str
    strategy: QueryStrategy
    params: dict
    streams: dict[str, str] = {}
    has_results: bool = False


class IndexerError(Exception):
    """Raised when an indexer request fails."""

    def __init__(self, message: str, remove_indexer: bool = False):
        super().__init__(message)
        self.remove_indexer = remove_indexer


def _arabic_to_roman(num: int) -> str:
    """Convert Arabic number to Roman numeral (I-X range for seasons)."""
    val = [1000, 900, 500, 400, 100, 90, 50, 40, 10, 9, 5, 4, 1]
    syms = ["M", "CM", "D", "CD", "C", "XC", "L", "XL", "X", "IX", "V", "IV", "I"]
    roman_num = ""
    i = 0
    while num > 0:
        for _ in range(num // val[i]):
            roman_num += syms[i]
            num -= val[i]
        i += 1
    return roman_num if roman_num else None


class Prowlarr(ScraperService):
    """Scraper for `Prowlarr`"""

    def __init__(self):
        super().__init__("prowlarr")
        self.settings = settings_manager.settings.scraping.prowlarr
        self.api_key = self.settings.api_key
        self.indexers = []
        self.headers = {
            "Content-Type": "application/json",
            "X-Api-Key": self.api_key,
        }
        self.timeout = self.settings.timeout
        self.session = None
        self.last_indexer_scan = None
        self._initialize()

    def _create_session(self) -> SmartSession:
        """Create a session for Prowlarr"""
        return SmartSession(
            base_url=f"{self.settings.url.rstrip('/')}/api/v1",
            retries=self.settings.retries,
            backoff_factor=0.3,
        )

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
                self.session = self._create_session()
                self.indexers = self.get_indexers()
                if not self.indexers:
                    logger.error("No Prowlarr indexers configured.")
                    return False
                return True
            except ReadTimeout:
                logger.error(
                    "Prowlarr request timed out. Check your indexers, they may be too slow to respond."
                )
                return False
            except Exception as e:
                logger.error(f"Prowlarr failed to initialize with API Key: {e}")
                return False
        logger.warning("Prowlarr is not configured and will not be used.")
        return False

    def get_indexers(self) -> list[Indexer]:
        statuses = self.session.get("/indexerstatus", timeout=15, headers=self.headers)
        response = self.session.get("/indexer", timeout=15, headers=self.headers)
        data = response.data
        statuses = statuses.data
        indexers = []
        for indexer_data in data:
            id = indexer_data.id
            if statuses:
                status = next((x for x in statuses if x.indexerId == id), None)
                if status and status.disabledTill > datetime.now().isoformat():
                    disabled_until = datetime.fromisoformat(
                        status.disabledTill
                    ).strftime("%Y-%m-%d %H:%M")
                    logger.debug(
                        f"Indexer {indexer_data.name} is disabled until {disabled_until}, skipping"
                    )
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
                logger.warning(
                    f"No valid capabilities found for indexer {name}. Consider removing this indexer."
                )
                continue

            search_params = SearchParams(
                search=list(set(indexer_data.capabilities.searchParams)),
                movie=list(set(indexer_data.capabilities.movieSearchParams)),
                tv=list(set(indexer_data.capabilities.tvSearchParams)),
            )

            capabilities = Capabilities(
                supports_raw_search=indexer_data.capabilities.supportsRawSearch,
                categories=caps,
                search_params=search_params,
            )

            indexers.append(
                Indexer(
                    id=id,
                    name=name,
                    enable=enable,
                    protocol=protocol,
                    capabilities=capabilities,
                )
            )

        self.last_indexer_scan = datetime.now()
        return indexers

    def _periodic_indexer_scan(self):
        """scan indexers every 30 minutes"""
        previous_count = len(self.indexers)
        if (
            self.last_indexer_scan is None
            or (datetime.now() - self.last_indexer_scan).total_seconds() > 1800
        ):
            self.indexers = self.get_indexers()
            self.last_indexer_scan = datetime.now()
            if len(self.indexers) != previous_count:
                logger.info(
                    f"Indexers count changed from {previous_count} to {len(self.indexers)}"
                )
                next_scan_time = self.last_indexer_scan + timedelta(seconds=1800)
                logger.info(
                    f"Next scan will be at {next_scan_time.strftime('%Y-%m-%d %H:%M')}"
                )

    def run(self, item: MediaItem) -> Dict[str, str]:
        """Scrape the Prowlarr site for the given media items
        and update the object with scraped streams"""
        if not item:
            return {}

        try:
            return self.scrape(item)
        except Exception as e:
            # Comprehensive error handling to prevent service crashes
            if "rate limit" in str(e).lower() or "429" in str(e):
                logger.debug(f"Prowlarr ratelimit exceeded for item: {item.log_string}")
            elif isinstance(e, RequestException):
                logger.error(f"Prowlarr request exception: {e}")
            elif "deque mutated" in str(e):
                logger.error(f"Prowlarr thread safety error (fixed in next run): {e}")
            elif "ConnectionState" in str(e) or "ConnectionInputs" in str(e):
                logger.error(f"Prowlarr connection state error: {e}")
            else:
                logger.error(f"Prowlarr unexpected error: {type(e).__name__}: {e}")
                # Log full traceback for debugging unknown errors
                logger.debug(f"Full traceback for {item.log_string}", exc_info=True)

            # Always return empty dict - never let exceptions bubble up
            return {}

    def scrape(self, item: MediaItem) -> Dict[str, str]:
        """Scrape a single item from all indexers at the same time, return a list of streams"""
        self._periodic_indexer_scan()

        torrents = {}
        start_time = time.time()
        failed_indexers = []  # Track failed indexers to remove after iteration

        if len(self.indexers) == 0:
            logger.debug("No Prowlarr indexers available for scraping.")
            return torrents
        
        with concurrent.futures.ThreadPoolExecutor(
            thread_name_prefix="ProwlarrScraper", max_workers=len(self.indexers)
        ) as executor:
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
                except Exception as exc:
                    remove_indexer = False

                    if isinstance(exc, IndexerError):
                        log_fn = logger.error if exc.remove_indexer else logger.warning
                        log_fn(f"Error processing indexer {indexer.name}: {exc}")
                        remove_indexer = exc.remove_indexer
                    else:
                        logger.error(f"Error processing indexer {indexer.name}: {exc}")
                        if "deque mutated" not in str(exc):
                            remove_indexer = True

                    if remove_indexer and indexer not in failed_indexers:
                        failed_indexers.append(indexer)

        # Safely remove failed indexers after concurrent iteration is complete
        for failed_indexer in failed_indexers:
            if failed_indexer in self.indexers:
                self.indexers.remove(failed_indexer)
                logger.debug(
                    f"Removed failed indexer {failed_indexer.name} from usable indexers"
                )

        elapsed = time.time() - start_time
        if torrents:
            logger.log(
                "SCRAPER", f"Found {len(torrents)} streams for {item.log_string}"
            )
            logger.debug(f"Total time taken: {elapsed:.2f} seconds")
        else:
            logger.log("NOT_FOUND", f"No streams found for {item.log_string}")

        return torrents

    def get_query_strategies(self, item: MediaItem) -> list[QueryStrategy]:
        """
        Determine which query strategies to try for an item, in priority order.
        Returns a list of strategies to attempt in sequence.
        Prioritizes dubbed anime searches when dubbed_anime_only is enabled.
        """
        scraping_settings = settings_manager.settings.scraping
        
        if item.type == "episode" and item.is_anime:
            # For anime episodes: prioritize dubbed searches if setting is enabled
            strategies = []
            
            if scraping_settings.dubbed_anime_only:
                # Try dubbed-specific searches first (including Roman numerals)
                strategies.extend([
                    QueryStrategy.STRICT_SEASON_EPISODE_DUB,
                    QueryStrategy.EPISODE_NUMBER_DUB,
                    QueryStrategy.ROMAN_SEASON_EPISODE_DUB,
                ])
            
            # Then try standard anime searches (including Roman numerals)
            strategies.extend([
                QueryStrategy.STRICT_SEASON_EPISODE,
                QueryStrategy.EPISODE_NUMBER_ONLY,
                QueryStrategy.ROMAN_SEASON_EPISODE,
                QueryStrategy.EPISODE_WITH_TITLE if item.title else None,
            ])
            
            return [s for s in strategies if s is not None]
            
        elif item.type == "season" and item.is_anime:
            # For anime seasons: prioritize dubbed searches if setting is enabled
            strategies = []
            
            if scraping_settings.dubbed_anime_only:
                # Try dubbed-specific searches first (including Roman numerals)
                strategies.extend([
                    QueryStrategy.SEASON_NUMBER_DUB,
                    QueryStrategy.ROMAN_SEASON_DUB,
                ])
            
            # Then try standard anime searches (including Roman numerals)
            strategies.extend([
                QueryStrategy.SEASON_NUMBER,
                QueryStrategy.ROMAN_SEASON,
                QueryStrategy.STRICT_SEASON,
                QueryStrategy.STRICT_SEASON_NUMBER,
            ])
            
            return strategies
        else:
            # For non-anime or other types: use standard approach
            return [QueryStrategy.STANDARD]

    def build_search_params(
        self,
        indexer: Indexer,
        item: MediaItem,
        strategy: QueryStrategy = QueryStrategy.STANDARD,
    ) -> dict:
        """Build a search query for a single indexer using the specified strategy."""
        params = {}
        item_title = (
            item.get_top_title()
            if item.type in ("show", "season", "episode")
            else item.title
        )
        search_params = indexer.capabilities.search_params

        def set_query_and_type(query, search_type):
            params["query"] = query
            params["type"] = search_type

        if item.type == "movie":
            if "imdbId" in search_params.movie:
                set_query_and_type(item.imdb_id, "moviesearch")
            if "q" in search_params.movie:
                set_query_and_type(item_title, "moviesearch")
            elif "q" in search_params.search:
                set_query_and_type(item_title, "search")
            else:
                raise ValueError(
                    f"Indexer {indexer.name} does not support movie search"
                )

        elif item.type == "show":
            if "imdbId" in search_params.tv:
                set_query_and_type(item.imdb_id, "tvsearch")
            elif "q" in search_params.tv:
                set_query_and_type(item_title, "tvsearch")
            elif "q" in search_params.search:
                set_query_and_type(item_title, "search")
            else:
                raise ValueError(f"Indexer {indexer.name} does not support show search")

        elif item.type == "season":
            season_num = (
                int(item.number) if isinstance(item.number, str) else item.number
            )

            if "q" in search_params.tv:
                # Build query based on strategy
                if strategy == QueryStrategy.STRICT_SEASON_NUMBER:
                    query = f"{item_title} S{season_num:02d}"
                elif strategy == QueryStrategy.STRICT_SEASON:
                    query = f"{item_title} Season {season_num}"
                elif strategy == QueryStrategy.SEASON_NUMBER:
                    query = f"{item_title} {season_num}"
                elif strategy == QueryStrategy.ROMAN_SEASON:
                    # Roman numeral season (e.g., "Overlord IV")
                    roman = _arabic_to_roman(season_num)
                    query = f"{item_title} {roman}" if roman else f"{item_title} {season_num}"
                elif strategy == QueryStrategy.ROMAN_SEASON_DUB:
                    # Roman numeral season with dubbed keyword (e.g., "Overlord IV dub")
                    roman = _arabic_to_roman(season_num)
                    query = f"{item_title} {roman} dub" if roman else f"{item_title} {season_num} dub"
                else:
                    # STANDARD strategy
                    query = f"{item_title} {season_num}"

                set_query_and_type(query, "tvsearch")
                if "season" in search_params.tv:
                    params["season"] = item.number
            elif "q" in search_params.search:
                if strategy == QueryStrategy.STRICT_SEASON:
                    query = f"{item_title} Season {season_num}"
                elif strategy == QueryStrategy.ROMAN_SEASON:
                    # Roman numeral season (e.g., "Overlord IV")
                    roman = _arabic_to_roman(season_num)
                    query = f"{item_title} {roman}" if roman else f"{item_title} {season_num}"
                elif strategy == QueryStrategy.ROMAN_SEASON_DUB:
                    # Roman numeral season with dubbed keyword (e.g., "Overlord IV dub")
                    roman = _arabic_to_roman(season_num)
                    query = f"{item_title} {roman} dub" if roman else f"{item_title} {season_num} dub"
                else:
                    query = f"{item_title} {season_num}"
                set_query_and_type(query, "search")
            else:
                raise ValueError(
                    f"Indexer {indexer.name} does not support season search"
                )

        elif item.type == "episode":
            episode_num = (
                int(item.number) if isinstance(item.number, str) else item.number
            )
            season_num = (
                int(item.parent.number)
                if isinstance(item.parent.number, str)
                else item.parent.number
            )

            if "q" in search_params.tv:
                # Build query based on strategy
                if strategy == QueryStrategy.STRICT_SEASON_EPISODE:
                    # Always use strict S##E## format for this strategy
                    query = f"{item_title} S{season_num:02d}E{episode_num:02d}"
                elif strategy == QueryStrategy.STRICT_SEASON_EPISODE_DUB:
                    # Strict S##E## format with dubbed keyword
                    query = f"{item_title} S{season_num:02d}E{episode_num:02d} dubbed"
                elif strategy == QueryStrategy.ROMAN_SEASON_EPISODE:
                    # Roman numeral season with episode (e.g., "Overlord IV 9")
                    roman = _arabic_to_roman(season_num)
                    query = f"{item_title} {roman} {episode_num}" if roman else f"{item_title} {episode_num}"
                elif strategy == QueryStrategy.ROMAN_SEASON_EPISODE_DUB:
                    # Roman numeral season with episode and dubbed keyword (e.g., "Overlord IV 9 dub")
                    roman = _arabic_to_roman(season_num)
                    query = f"{item_title} {roman} {episode_num} dub" if roman else f"{item_title} {episode_num} dub"
                elif strategy == QueryStrategy.EPISODE_NUMBER_ONLY:
                    # Just episode number (good for anime)
                    query = f"{item_title} {episode_num}"
                elif strategy == QueryStrategy.EPISODE_NUMBER_DUB:
                    # Episode number with dubbed keyword
                    query = f"{item_title} {episode_num} dubbed"
                elif strategy == QueryStrategy.SEASON_NUMBER_DUB:
                    # Season number with dubbed keyword
                    query = f"{item_title} Season {season_num} dub"
                elif strategy == QueryStrategy.EPISODE_WITH_TITLE:
                    # Episode number with title (fallback for anime)
                    query = f"{item_title} {episode_num}"
                    if item.title:
                        query = f"{query} {item.title}"
                else:
                    # STANDARD strategy: use appropriate format based on anime status
                    if item.is_anime:
                        query = f"{item_title} {episode_num}"
                    else:
                        query = f"{item_title} S{season_num:02d}E{episode_num:02d}"

                # Include structured params if available (helps some indexers)
                if "season" in search_params.tv:
                    params["season"] = season_num
                if "ep" in search_params.tv:
                    params["ep"] = episode_num

                set_query_and_type(query, "tvsearch")
            elif "q" in search_params.search:
                # Basic search fallback
                if strategy == QueryStrategy.STRICT_SEASON_EPISODE:
                    query = f"{item_title} S{season_num:02d}E{episode_num:02d}"
                elif strategy == QueryStrategy.STRICT_SEASON_EPISODE_DUB:
                    query = f"{item_title} S{season_num:02d}E{episode_num:02d} dubbed"
                elif strategy == QueryStrategy.ROMAN_SEASON_EPISODE:
                    # Roman numeral season with episode (e.g., "Overlord IV 9")
                    roman = _arabic_to_roman(season_num)
                    query = f"{item_title} {roman} {episode_num}" if roman else f"{item_title} {episode_num}"
                elif strategy == QueryStrategy.ROMAN_SEASON_EPISODE_DUB:
                    # Roman numeral season with episode and dubbed keyword (e.g., "Overlord IV 9 dub")
                    roman = _arabic_to_roman(season_num)
                    query = f"{item_title} {roman} {episode_num} dub" if roman else f"{item_title} {episode_num} dub"
                elif strategy == QueryStrategy.EPISODE_NUMBER_ONLY:
                    query = f"{item_title} {episode_num}"
                elif strategy == QueryStrategy.EPISODE_NUMBER_DUB:
                    query = f"{item_title} {episode_num} dubbed"
                elif strategy == QueryStrategy.SEASON_NUMBER_DUB:
                    query = f"{item_title} Season {season_num} dub"
                elif strategy == QueryStrategy.EPISODE_WITH_TITLE:
                    query = f"{item_title} {episode_num}"
                    if item.title:
                        query = f"{query} {item.title}"
                else:
                    # STANDARD strategy
                    if item.is_anime:
                        query = f"{item_title} {episode_num}"
                    else:
                        query = f"{item_title} S{season_num:02d}E{episode_num:02d}"

                set_query_and_type(query, "search")
            else:
                raise ValueError(
                    f"Indexer {indexer.name} does not support episode search"
                )

        categories = {
            cat_id
            for category in indexer.capabilities.categories
            if (category.type == "tv" and item.type in ("show", "season", "episode"))
            or (category.type == "anime" and item.is_anime)
            for cat_id in category.ids
        }

        params["indexerIds"] = indexer.id
        params["categories"] = list(categories)
        params["limit"] = 1000

        return params

    def _perform_search_request(self, indexer: Indexer, params: dict):
        """Perform the search request, retrying once on transient request failures."""

        session = self.session or self._create_session()
        self.session = session

        try:
            return session.get(
                "/search", params=params, timeout=self.timeout, headers=self.headers
            )
        except CircuitBreakerOpen as exc:
            raise IndexerError(str(exc), remove_indexer=False) from exc
        except RequestException as exc:
            logger.warning(
                f"Request error while scraping {indexer.name}: {exc}. Reinitializing session and retrying once."
            )
            self.session = self._create_session()
            try:
                return self.session.get(
                    "/search",
                    params=params,
                    timeout=self.timeout,
                    headers=self.headers,
                )
            except CircuitBreakerOpen as retry_cb:
                raise IndexerError(str(retry_cb), remove_indexer=False) from retry_cb
            except RequestException as retry_exc:
                raise IndexerError(
                    f"Repeated request error while scraping {indexer.name}: {retry_exc}",
                    remove_indexer=False,
                ) from retry_exc

    def _execute_search_strategy(
        self, indexer: Indexer, item: MediaItem, params: dict, strategy: QueryStrategy
    ) -> dict[str, str]:
        """Execute a single search strategy and return streams found."""
        start_time = time.time()

        response = self._perform_search_request(indexer, params)

        if not getattr(response, "ok", False):
            message = "Unknown error"
            data = getattr(response, "data", None)
            if hasattr(data, "message"):
                message = data.message or message
            elif isinstance(data, dict):
                message = data.get("message") or data.get("error") or message

            status_code = getattr(response, "status_code", None)
            lower_message = (message or "").lower()

            remove_indexer = True
            if status_code == 400 and "all selected indexers" in lower_message:
                remove_indexer = False

            raise IndexerError(
                f"[{status_code if status_code is not None else 'N/A'}] {message}",
                remove_indexer=remove_indexer,
            )

        data = getattr(response, "data", None)
        if not data:
            logger.debug(
                f"Indexer {indexer.name} returned empty data set for strategy {strategy.value}"
            )
            return {}

        streams: dict[str, str] = {}
        urls_to_fetch: list[tuple[object, str]] = []

        for torrent in data:
            title = getattr(torrent, "title", None)
            if not title:
                continue

            # Log all available attributes from the torrent object for debugging
            logger.debug(
                f"Prowlarr torrent object attributes: {vars(torrent) if hasattr(torrent, '__dict__') else str(torrent)}"
            )

            infohash = None
            if hasattr(torrent, "infoHash") and torrent.infoHash:
                infohash = normalize_infohash(torrent.infoHash)
            if not infohash and hasattr(torrent, "guid") and torrent.guid:
                infohash = extract_infohash(torrent.guid)

            if not infohash and hasattr(torrent, "downloadUrl") and torrent.downloadUrl:
                urls_to_fetch.append((torrent, title))
            elif infohash:
                streams[infohash] = title

        if urls_to_fetch:
            try:
                with concurrent.futures.ThreadPoolExecutor(
                    thread_name_prefix="ProwlarrHashExtract",
                    max_workers=max(1, len(self.indexers)),
                ) as executor:
                    future_to_torrent = {
                        executor.submit(
                            self.get_infohash_from_url, torrent.downloadUrl
                        ): (torrent, title)
                        for torrent, title in urls_to_fetch
                    }

                    done, pending = concurrent.futures.wait(
                        future_to_torrent.keys(),
                        timeout=self.settings.infohash_fetch_timeout,
                    )

                    for future in done:
                        torrent, title = future_to_torrent[future]
                        try:
                            infohash = future.result()
                            if infohash:
                                streams[infohash] = title
                        except Exception as exc:
                            logger.debug(
                                f"Failed to get infohash from downloadUrl for {title}: {exc}"
                            )

                    for future in pending:
                        torrent, title = future_to_torrent[future]
                        future.cancel()
                        logger.debug(
                            f"Timeout getting infohash from downloadUrl for {title}"
                        )
            except Exception as exc:
                logger.error(
                    f"Error during parallel infohash fetching for {indexer.name}: {exc}"
                )

        elapsed = time.time() - start_time
        logger.debug(
            f"Indexer {indexer.name} found {len(streams)} streams using strategy '{strategy.value}' for {item.log_string} in {elapsed:.2f}s"
        )

        return streams

    def scrape_indexer(self, indexer: Indexer, item: MediaItem) -> dict[str, str]:
        """Scrape results from a single indexer with multi-strategy fallback.
        
        Uses RTN/PTT parsing to validate result quality and determine if fallback
        strategies should be attempted based on actual result validity, not just count.
        """

        if indexer.name in ANIME_ONLY_INDEXERS or "anime" in indexer.name.lower():
            if not item.is_anime:
                logger.debug(f"Indexer {indexer.name} is anime only, skipping")
                return {}

        # Get strategies to try for this item
        strategies = self.get_query_strategies(item)
        strategies = [s for s in strategies if s is not None]  # Filter out None values

        if not strategies:
            strategies = [QueryStrategy.STANDARD]

        all_streams: dict[str, str] = {}
        
        # Minimum acceptable results before stopping fallback attempts
        # If failed_attempts > 5, we're more lenient and accept fewer results
        min_acceptable_results = max(2, 10 - (item.failed_attempts or 0))

        for strategy_idx, strategy in enumerate(strategies):
            try:
                params = self.build_search_params(indexer, item, strategy)
            except ValueError as exc:
                logger.error(
                    f"Failed to build search params for {indexer.name} with strategy {strategy.value}: {exc}"
                )
                continue

            try:
                strategy_streams = self._execute_search_strategy(
                    indexer, item, params, strategy
                )

                # Merge streams from this strategy
                if strategy_streams:
                    all_streams.update(strategy_streams)
                    strategy_quality = self._validate_result_quality(strategy_streams, item)
                    
                    if strategy_idx == 0:
                        # First strategy: only stop if we have enough good results
                        if len(strategy_streams) >= min_acceptable_results and strategy_quality > 0.3:
                            logger.debug(
                                f"First strategy '{strategy.value}' succeeded with {len(strategy_streams)} results (quality: {strategy_quality:.2f}), sufficient for {item.log_string}"
                            )
                            break
                        elif len(strategy_streams) > 0:
                            logger.debug(
                                f"First strategy '{strategy.value}' found {len(strategy_streams)} results (quality: {strategy_quality:.2f}) for {item.log_string}, below threshold ({min_acceptable_results}), trying fallback strategies"
                            )
                    else:
                        logger.debug(
                            f"Fallback strategy '{strategy.value}' added {len(strategy_streams)} results (quality: {strategy_quality:.2f})"
                        )
                else:
                    # No results with this strategy, try next one
                    if strategy_idx == 0:
                        logger.debug(
                            f"First strategy '{strategy.value}' found no results, trying fallback strategies"
                        )
                    else:
                        logger.debug(
                            f"Fallback strategy '{strategy.value}' also found no results"
                        )

            except IndexerError:
                # Don't try fallback strategies if we got an indexer error
                raise
            except Exception as exc:
                logger.warning(
                    f"Error executing strategy '{strategy.value}' for {indexer.name}: {exc}"
                )
                # Try next strategy on error

        return all_streams

    def _validate_result_quality(self, streams: dict[str, str], item: MediaItem) -> float:
        """Validate result quality using RTN parsing to determine if results are usable.
        
        Returns a quality score from 0.0 to 1.0 indicating how many of the results
        appear to be valid for the given item based on RTN parsing.
        """
        from program.services.scrapers.shared import _parse_results
        
        if not streams:
            return 0.0
        
        # Parse results to see how many pass RTN validation
        try:
            parsed = _parse_results(item, streams, log_msg=False)
            quality_ratio = len(parsed) / len(streams) if streams else 0.0
            return quality_ratio
        except Exception as exc:
            logger.debug(f"Error during result quality validation: {exc}")
            # If parsing fails, assume moderate quality
            return 0.5
