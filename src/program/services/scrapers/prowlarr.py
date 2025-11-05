"""Prowlarr scraper module"""

import concurrent.futures
import time
from datetime import datetime, timedelta
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


class IndexerError(Exception):
    """Raised when an indexer request fails."""

    def __init__(self, message: str, remove_indexer: bool = False):
        super().__init__(message)
        self.remove_indexer = remove_indexer


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

    def build_search_params(self, indexer: Indexer, item: MediaItem) -> dict:
        """Build a search query for a single indexer."""
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
            if "q" in search_params.tv:
                # Convert zero-padded season number (e.g., "01") to integer (e.g., 1)
                season_num = (
                    int(item.number) if isinstance(item.number, str) else item.number
                )
                set_query_and_type(f"{item_title} {season_num}", "tvsearch")
                if "season" in search_params.tv:
                    params["season"] = item.number
            elif "q" in search_params.search:
                season_num = (
                    int(item.number) if isinstance(item.number, str) else item.number
                )
                query = f"{item_title} {season_num}"
                set_query_and_type(query, "search")
            else:
                raise ValueError(
                    f"Indexer {indexer.name} does not support season search"
                )

        elif item.type == "episode":
            if "q" in search_params.tv:
                # Different search strategies for anime vs non-anime
                # Anime: use loose searches with episode numbers (e.g., "Show 7" or "Show 7 Episode Title")
                # Non-anime: use strict S##E## format (e.g., "Show S03E07") for better precision
                episode_num = (
                    int(item.number) if isinstance(item.number, str) else item.number
                )
                season_num = (
                    int(item.parent.number)
                    if isinstance(item.parent.number, str)
                    else item.parent.number
                )

                if item.is_anime:
                    # Anime: use loose format to catch various naming conventions
                    # - "Show III 07" (Roman numerals)
                    # - "Show Season 3 Episode 7" (spelled out)
                    # - "Show 3 07" (plain numbers)
                    query = f"{item_title} {episode_num}"
                    if item.title:
                        query = f"{query} {item.title}"
                else:
                    # Non-anime: use strict S##E## format for better precision
                    query = f"{item_title} S{season_num:02d}E{episode_num:02d}"

                # Include structured params if available (doesn't hurt, might help some)
                if "season" in search_params.tv:
                    params["season"] = season_num
                if "ep" in search_params.tv:
                    params["ep"] = episode_num

                set_query_and_type(query, "tvsearch")
            elif "q" in search_params.search:
                # Basic search fallback
                episode_num = (
                    int(item.number) if isinstance(item.number, str) else item.number
                )
                season_num = (
                    int(item.parent.number)
                    if isinstance(item.parent.number, str)
                    else item.parent.number
                )

                if item.is_anime:
                    # Anime: use loose format
                    query = f"{item_title} {episode_num}"
                    if item.title:
                        query = f"{query} {item.title}"
                else:
                    # Non-anime: use strict S##E## format
                    query = f"{item_title} S{season_num:02d}E{episode_num:02d}"

                set_query_and_type(query, "search")
            else:
                raise ValueError(
                    f"Indexer {indexer.name} does not support episode search"
                )

        categories = {
            cat_id
            for category in indexer.capabilities.categories
            if category.type == item.type
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

    def scrape_indexer(self, indexer: Indexer, item: MediaItem) -> dict[str, str]:
        """Scrape results from a single indexer."""

        if indexer.name in ANIME_ONLY_INDEXERS or "anime" in indexer.name.lower():
            if not item.is_anime:
                logger.debug(f"Indexer {indexer.name} is anime only, skipping")
                return {}

        try:
            params = self.build_search_params(indexer, item)
        except ValueError as exc:
            logger.error(f"Failed to build search params for {indexer.name}: {exc}")
            return {}

        start_time = time.time()

        try:
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
                logger.debug(f"Indexer {indexer.name} returned empty data set")
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

                if (
                    not infohash
                    and hasattr(torrent, "downloadUrl")
                    and torrent.downloadUrl
                ):
                    urls_to_fetch.append((torrent, title))
                elif infohash:
                    streams[infohash] = title

            if urls_to_fetch:
                try:
                    with concurrent.futures.ThreadPoolExecutor(
                        thread_name_prefix="ProwlarrHashExtract", max_workers=10
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

            logger.debug(
                f"Indexer {indexer.name} found {len(streams)} streams for {item.log_string} in {time.time() - start_time:.2f} seconds"
            )
            return streams

        except IndexerError:
            raise
        except Exception as exc:
            raise IndexerError(
                f"Unexpected error scraping {indexer.name}: {exc}",
                remove_indexer=False,
            ) from exc
