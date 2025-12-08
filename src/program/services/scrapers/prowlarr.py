"""Prowlarr scraper module"""

import concurrent.futures
import time
from datetime import datetime, timedelta

from loguru import logger
from pydantic import BaseModel, Field
from requests import ReadTimeout, RequestException

from program.media.item import Episode, MediaItem, Movie, Season, Show
from program.services.scrapers.base import ScraperService
from program.settings import settings_manager
from program.utils.request import SmartSession
from program.utils.torrent import extract_infohash, normalize_infohash
from program.settings.models import ProwlarrConfig

from schemas.prowlarr import (
    IndexerResource,
    IndexerStatusResource,
    SearchParam,
    TvSearchParam,
    MovieSearchParam,
    ReleaseResource,
)


class GetIndexersResponse(BaseModel):
    indexers: list[IndexerResource]


class GetIndexerStatusResponse(BaseModel):
    statuses: list[IndexerStatusResource]


class Category(BaseModel):
    name: str
    type: str
    ids: list[int]


class SearchParams(BaseModel):
    search: list[SearchParam]
    movie: list[MovieSearchParam]
    tv: list[TvSearchParam]


class Capabilities(BaseModel):
    supports_raw_search: bool | None
    categories: list[Category]
    search_params: SearchParams


class Indexer(BaseModel):
    id: int | None
    name: str | None
    enable: bool
    protocol: str
    capabilities: Capabilities


class Params(BaseModel):
    query: str | None
    type: str | None
    indexer_ids: int | None = Field(alias="indexerIds")
    categories: list[int] | None
    limit: int | None
    season: int | None
    ep: int | None


class ScrapeResponse(BaseModel):
    items: list[ReleaseResource]


class ScrapeErrorResponse(BaseModel):
    message: str | None


ANIME_ONLY_INDEXERS = ("Nyaa.si", "SubsPlease", "Anidub", "Anidex")


class Prowlarr(ScraperService[ProwlarrConfig]):
    """Scraper for `Prowlarr`"""

    def __init__(self):
        super().__init__()

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
                if self.timeout <= 0:
                    logger.error("Prowlarr timeout must be a positive integer.")
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
        assert self.session

        statuses = self.session.get("/indexerstatus", timeout=15, headers=self.headers)
        response = self.session.get("/indexer", timeout=15, headers=self.headers)

        data = GetIndexersResponse.model_validate(
            {
                "indexers": response.json(),
            }
        ).indexers
        statuses = GetIndexerStatusResponse.model_validate(
            {
                "statuses": statuses.json(),
            }
        ).statuses

        indexers = list[Indexer]()

        for indexer_data in data:
            id = indexer_data.id

            if statuses:
                status = next(
                    (x for x in statuses if x.indexer_id == id),
                    None,
                )

                if (
                    status
                    and status.disabled_till
                    and status.disabled_till > datetime.now()
                ):
                    disabled_until = status.disabled_till.strftime("%Y-%m-%d %H:%M")

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

            categories = list[Category]()

            if not indexer_data.capabilities:
                logger.warning(
                    f"No capabilities found for indexer {name}. Consider removing this indexer."
                )
                continue

            if indexer_data.capabilities and indexer_data.capabilities.categories:
                for cap in indexer_data.capabilities.categories:
                    if cap.name:
                        if "TV" in cap.name:
                            category = next(
                                (x for x in categories if "TV" in x.name), None
                            )

                            if cap.id:
                                if category:
                                    category.ids.append(cap.id)
                                else:
                                    categories.append(
                                        Category(name="TV", type="tv", ids=[cap.id])
                                    )
                        elif "Movies" in cap.name:
                            category = next(
                                (x for x in categories if "Movies" in x.name), None
                            )

                            if cap.id:
                                if category:
                                    category.ids.append(cap.id)
                                else:
                                    categories.append(
                                        Category(
                                            name="Movies", type="movie", ids=[cap.id]
                                        )
                                    )
                        elif "Anime" in cap.name:
                            category = next(
                                (x for x in categories if "Anime" in x.name), None
                            )

                            if cap.id:
                                if category:
                                    category.ids.append(cap.id)
                                else:
                                    categories.append(
                                        Category(
                                            name="Anime", type="anime", ids=[cap.id]
                                        )
                                    )

            if not categories:
                logger.warning(
                    f"No valid capabilities found for indexer {name}. Consider removing this indexer."
                )
                continue

            search_params = SearchParams(
                search=list(set(indexer_data.capabilities.search_params or [])),
                movie=list(set(indexer_data.capabilities.movie_search_params or [])),
                tv=list(set(indexer_data.capabilities.tv_search_params or [])),
            )

            capabilities = Capabilities(
                supports_raw_search=indexer_data.capabilities.supports_raw_search,
                categories=categories,
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
        """Scan indexers every 30 minutes"""

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

    def run(self, item: MediaItem) -> dict[str, str]:
        """
        Scrape the Prowlarr site for the given media items
        and update the object with scraped streams
        """

        try:
            return self.scrape(item)
        except Exception as e:
            if "rate limit" in str(e).lower() or "429" in str(e):
                logger.debug(f"Prowlarr ratelimit exceeded for item: {item.log_string}")
            elif isinstance(e, RequestException):
                logger.error(f"Prowlarr request exception: {e}")
            else:
                logger.exception(f"Prowlarr failed to scrape item with error: {e}")
        return {}

    def scrape(self, item: MediaItem) -> dict[str, str]:
        """Scrape a single item from all indexers at the same time, return a list of streams"""

        self._periodic_indexer_scan()

        torrents = dict[str, str]()
        start_time = time.time()

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
                except Exception as e:
                    logger.error(f"Error processing indexer {indexer.name}: {e}")

        elapsed = time.time() - start_time

        if torrents:
            logger.log(
                "SCRAPER", f"Found {len(torrents)} streams for {item.log_string}"
            )
            logger.debug(f"Total time taken: {elapsed:.2f} seconds")
        else:
            logger.log("NOT_FOUND", f"No streams found for {item.log_string}")

        return torrents

    def build_search_params(self, indexer: Indexer, item: MediaItem) -> Params:
        """Build a search query for a single indexer."""

        params = {}

        item_title = item.top_title

        search_params = indexer.capabilities.search_params

        def set_query_and_type(query: str, search_type: str):
            params["query"] = query
            params["type"] = search_type

        if isinstance(item, Movie):
            if "imdbId" in search_params.movie and item.imdb_id:
                set_query_and_type(item.imdb_id, "movie-search")
            if "q" in search_params.movie:
                set_query_and_type(item_title, "movie-search")
            elif "q" in search_params.search:
                set_query_and_type(item_title, "search")
            else:
                raise ValueError(
                    f"Indexer {indexer.name} does not support movie search"
                )

        elif isinstance(item, Show):
            if "imdbId" in search_params.tv and item.imdb_id:
                set_query_and_type(item.imdb_id, "tv-search")
            elif "q" in search_params.tv:
                set_query_and_type(item_title, "tv-search")
            elif "q" in search_params.search:
                set_query_and_type(item_title, "search")
            else:
                raise ValueError(f"Indexer {indexer.name} does not support show search")

        elif isinstance(item, Season):
            if "q" in search_params.tv:
                set_query_and_type(f"{item_title} S{item.number}", "tv-search")
                if "season" in search_params.tv:
                    params["season"] = item.number
            elif "q" in search_params.search:
                query = f"{item_title} S{item.number}"
                set_query_and_type(query, "search")
            else:
                raise ValueError(
                    f"Indexer {indexer.name} does not support season search"
                )

        elif isinstance(item, Episode):
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

        return Params.model_validate(params)

    def scrape_indexer(self, indexer: Indexer, item: MediaItem) -> dict[str, str]:
        """Scrape from a single indexer"""

        if (
            indexer.name in ANIME_ONLY_INDEXERS
            or "anime" in (indexer.name or "").lower()
        ):
            if not item.is_anime:
                logger.debug(f"Indexer {indexer.name} is anime only, skipping")
                return {}

        try:
            params = self.build_search_params(indexer, item)
        except ValueError as e:
            logger.error(f"Failed to build search params for {indexer.name}: {e}")
            return {}

        start_time = time.time()

        assert self.session

        response = self.session.get(
            "/search",
            params=params.model_dump(),
            timeout=self.timeout,
            headers=self.headers,
        )

        if not response.ok:
            data = ScrapeErrorResponse.model_validate(response.json())

            message = data.message or "Unknown error"

            logger.debug(
                f"Failed to scrape {indexer.name}: [{response.status_code}] {message}"
            )

            self.indexers.remove(indexer)

            logger.debug(
                f"Removed indexer {indexer.name} from the list of usable indexers"
            )

            return {}

        data = ScrapeResponse.model_validate({"items": response.json()}).items
        streams = dict[str, str]()

        # List of (torrent, title) tuples that need URL fetching
        urls_to_fetch = list[tuple[ReleaseResource, str]]()

        # First pass: extract infohashes from available fields and collect URLs that need fetching
        for torrent in data:
            title = torrent.title
            infohash = None

            # Priority 1: Use infoHash field directly if available (normalize to handle base32)
            if torrent.info_hash:
                infohash = normalize_infohash(torrent.info_hash)

            # Priority 2: Try to extract from guid (handles magnets and bare hashes)
            if not infohash and torrent.guid:
                infohash = extract_infohash(torrent.guid)

            # Priority 3: Collect URLs that need fetching
            if not infohash and torrent.download_url and title:
                urls_to_fetch.append((torrent, title))
            elif infohash and title:
                # We already have an infohash, add it directly
                streams[infohash] = title

        # Fetch URLs in parallel
        if urls_to_fetch:
            with concurrent.futures.ThreadPoolExecutor(
                thread_name_prefix="ProwlarrHashExtract", max_workers=10
            ) as executor:
                future_to_torrent = {
                    executor.submit(self.get_infohash_from_url, torrent.download_url): (
                        torrent,
                        title,
                    )
                    for torrent, title in urls_to_fetch
                    if torrent.download_url
                }

                done, pending = concurrent.futures.wait(
                    future_to_torrent.keys(),
                    timeout=self.settings.infohash_fetch_timeout,
                )

                # Process completed futures
                for future in done:
                    torrent, title = future_to_torrent[future]

                    try:
                        infohash = future.result()
                        if infohash:
                            streams[infohash] = title
                    except Exception as e:
                        logger.debug(
                            f"Failed to get infohash from downloadUrl for {title}: {e}"
                        )

                # Cancel and log timeouts for pending futures
                for future in pending:
                    torrent, title = future_to_torrent[future]
                    future.cancel()
                    logger.debug(
                        f"Timeout getting infohash from downloadUrl for {title}"
                    )

        logger.debug(
            f"Indexer {indexer.name} found {len(streams)} streams for {item.log_string} in {time.time() - start_time:.2f} seconds"
        )

        return streams
