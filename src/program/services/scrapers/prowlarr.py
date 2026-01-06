"""Prowlarr scraper module"""

import concurrent.futures
import time
from datetime import datetime, timedelta, timezone

import defusedxml.ElementTree as ET
import requests as http_requests
from loguru import logger
from pydantic import BaseModel, ConfigDict, Field
from requests import ReadTimeout, RequestException

from program.media.item import Episode, MediaItem, Movie, Season, Show
from program.services.scrapers.base import ScraperService
from program.settings import settings_manager
from program.settings.models import ProwlarrConfig
from program.utils.request import SmartSession
from program.utils.torrent import extract_infohash, normalize_infohash
from schemas.prowlarr import (
    IndexerResource,
    IndexerStatusResource,
    MovieSearchParam,
    ReleaseResource,
    SearchParam,
    TvSearchParam,
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
    implementation: str | None  # "Torznab", "Newznab", or native type
    capabilities: Capabilities


class Params(BaseModel):
    model_config = ConfigDict(serialize_by_alias=True)

    query: str | None = None
    type: str | None = None
    indexer_ids: int | None = Field(serialization_alias="indexerIds", default=None)
    categories: list[int]
    limit: int | None = None
    season: int | None = None
    ep: int | None = None
    imdbid: str | None = None  # lowercase to match Prowlarr/Torznab API


class ScrapeResponse(BaseModel):
    items: list[ReleaseResource]


class ScrapeErrorResponse(BaseModel):
    message: str | None = None


ANIME_ONLY_INDEXERS = ("Nyaa.si", "SubsPlease", "Anidub", "Anidex")


class Prowlarr(ScraperService[ProwlarrConfig]):
    """Scraper for `Prowlarr`"""

    def __init__(self):
        super().__init__()

        self.settings = settings_manager.settings.scraping.prowlarr
        self.api_key = ""  # Will be set during validation from first working instance
        self.indexers = []
        self.headers = {
            "Content-Type": "application/json",
        }
        self.timeout = self.settings.timeout
        self.session = None
        self.base_url = ""  # Store base URL for Newznab endpoint access
        self.last_indexer_scan = None
        self._initialize()

    def _create_session(self, base_url: str) -> SmartSession:
        """Create a session for Prowlarr"""
        self.base_url = base_url.rstrip('/')

        return SmartSession(
            base_url=f"{self.base_url}/api/v1",
            retries=self.settings.retries,
            backoff_factor=0.3,
        )

    def validate(self) -> bool:
        """Validate Prowlarr settings."""

        if not self.settings.enabled:
            return False

        if not self.settings.instances or not any(
            inst.url and inst.api_key for inst in self.settings.instances
        ):
            logger.warning(
                "No valid Prowlarr instances configured (need URL + API key). Will not be used."
            )
            return False

        if self.timeout <= 0:
            logger.error("Prowlarr timeout must be a positive integer.")
            return False

        # Try to find a working instance
        for instance in self.settings.instances:
            if not instance.url or not instance.api_key:
                continue
            try:
                self.api_key = instance.api_key
                self.headers["X-Api-Key"] = self.api_key
                self.session = self._create_session(instance.url)
                self.indexers = self.get_indexers()

                if not self.indexers:
                    logger.warning(
                        f"No Prowlarr indexers found for {instance.url}, trying next..."
                    )
                    continue

                return True
            except ReadTimeout:
                logger.warning(
                    f"Prowlarr request timed out for {instance.url}. Trying next instance..."
                )
                continue
            except Exception as e:
                logger.warning(f"Prowlarr failed to initialize with {instance.url}: {e}")
                continue

        logger.error("Prowlarr failed to initialize: all instances failed")
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
                    and status.disabled_till > datetime.now(timezone.utc)
                ):
                    disabled_until = status.disabled_till.strftime("%Y-%m-%d %H:%M")

                    logger.debug(
                        f"Indexer {indexer_data.name} is disabled until {disabled_until}, skipping"
                    )

                    continue

            name = indexer_data.name
            enable = indexer_data.enable
            implementation = indexer_data.implementation

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
                    implementation=implementation,
                    capabilities=capabilities,
                )
            )

        self.last_indexer_scan = datetime.now(timezone.utc)

        return indexers

    def _periodic_indexer_scan(self):
        """Scan indexers every 30 minutes"""

        previous_count = len(self.indexers)

        if (
            self.last_indexer_scan is None
            or (datetime.now(timezone.utc) - self.last_indexer_scan).total_seconds()
            > 1800
        ):
            self.indexers = self.get_indexers()
            self.last_indexer_scan = datetime.now(timezone.utc)

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

        search_query = None
        search_type = None
        season = None
        episode = None
        imdbid = None

        item_title = item.top_title

        search_params = indexer.capabilities.search_params

        def set_query_and_type(
            _query: str | None, _type: str, _imdbid: str | None = None
        ):
            nonlocal search_query, search_type, imdbid

            search_query = _query
            search_type = _type
            imdbid = _imdbid

        if isinstance(item, Movie):
            if "imdbId" in search_params.movie and item.imdb_id:
                # Prowlarr expects type='movie' and imdbid as a separate parameter (without 'tt' prefix)
                imdb_numeric = item.imdb_id.lstrip("t")
                set_query_and_type(None, "movie", imdb_numeric)
            elif "q" in search_params.movie:
                set_query_and_type(item_title, "movie-search")
            elif "q" in search_params.search:
                set_query_and_type(item_title, "search")
            else:
                raise ValueError(
                    f"Indexer {indexer.name} does not support movie search"
                )

        elif isinstance(item, Show):
            if "imdbId" in search_params.tv and item.imdb_id:
                # Prowlarr expects type='tvsearch' and imdbid as a separate parameter
                imdb_numeric = item.imdb_id.lstrip("t")
                set_query_and_type(None, "tvsearch", imdb_numeric)
            elif "q" in search_params.tv:
                set_query_and_type(item_title, "tv-search")
            elif "q" in search_params.search:
                set_query_and_type(item_title, "search")
            else:
                raise ValueError(f"Indexer {indexer.name} does not support show search")

        elif isinstance(item, Season):
            show_imdb_id = item.parent.imdb_id if item.parent else None
            logger.debug(f"Show IMDB ID for {item.log_string}: {show_imdb_id}")
            if "imdbId" in search_params.tv and show_imdb_id:
                imdb_numeric = show_imdb_id.lstrip("t")
                set_query_and_type(None, "tvsearch", imdb_numeric)
                season = item.number
            elif "q" in search_params.tv:
                set_query_and_type(f"{item_title} S{item.number}", "tv-search")
                if "season" in search_params.tv:
                    season = item.number
            elif "q" in search_params.search:
                query = f"{item_title} S{item.number}"
                set_query_and_type(query, "search")
            else:
                raise ValueError(
                    f"Indexer {indexer.name} does not support season search"
                )

        elif isinstance(item, Episode):
            show_imdb_id = item.parent.parent.imdb_id if item.parent and item.parent.parent else None
            logger.debug(f"Show IMDB ID for {item.log_string}: {show_imdb_id}")
            if "imdbId" in search_params.tv and show_imdb_id:
                imdb_numeric = show_imdb_id.lstrip("t")
                set_query_and_type(None, "tvsearch", imdb_numeric)
                season = item.parent.number
                episode = item.number
            elif "q" in search_params.tv:
                if "ep" in search_params.tv:
                    query = f"{item_title}"
                    season = item.parent.number
                    episode = item.number
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

        indexer_ids = indexer.id
        limit = 1000

        return Params(
            season=season,
            ep=episode,
            query=search_query,
            type=search_type,
            categories=list(categories),
            indexer_ids=indexer_ids,
            limit=limit,
            imdbid=imdbid,
        )

    def _parse_newznab_response(self, xml_text: str) -> list[ReleaseResource]:
        """Parse Newznab XML (RSS) response into ReleaseResource objects."""
        releases = []
        try:
            root = ET.fromstring(xml_text)
            # Newznab RSS format: /rss/channel/item
            channel = root.find("channel")
            if channel is None:
                logger.debug("No channel found in Newznab response")
                return releases

            for item in channel.findall("item"):
                title = item.findtext("title", "")
                link = item.findtext("link", "")
                guid = item.findtext("guid", "")

                # Extract infohash from torznab:attr elements
                info_hash = None
                magnet_url = None
                download_url = None

                # Handle namespaced attributes (torznab:attr)
                for attr in item.findall(".//{http://torznab.com/schemas/2015/feed}attr"):
                    name = attr.get("name", "")
                    value = attr.get("value", "")
                    if name == "infohash":
                        info_hash = value
                    elif name == "magneturl":
                        magnet_url = value

                # Also check for enclosure (download URL)
                enclosure = item.find("enclosure")
                if enclosure is not None:
                    download_url = enclosure.get("url", "")

                # Use link as fallback for download URL
                if not download_url and link:
                    download_url = link

                releases.append(ReleaseResource(
                    title=title,
                    guid=guid or magnet_url,
                    info_hash=info_hash,
                    download_url=download_url,
                    magnet_url=magnet_url,
                ))

        except ET.ParseError as e:
            logger.error(f"Failed to parse Newznab XML response: {e}")
        except Exception as e:
            logger.error(f"Error processing Newznab response: {e}")

        return releases

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

        request_params = params.model_dump(by_alias=True, exclude_none=True)

        # Use Newznab proxy endpoint when searching by IMDB ID on Torznab indexers
        # The /api/v1/search endpoint doesn't support imdbid parameter
        # Only Torznab indexers support the /{id}/api proxy endpoint for IMDB searches
        is_torznab = indexer.implementation and indexer.implementation.lower() == "torznab"
        use_newznab = params.imdbid and indexer.id and is_torznab
        if use_newznab:
            # Build Newznab-style params for the /{id}/api endpoint
            newznab_params = {
                "t": params.type,
                "imdbid": params.imdbid,
                "limit": params.limit,
                "extended": 1,
                "apikey": self.api_key,
            }
            if params.categories:
                newznab_params["cat"] = ",".join(str(c) for c in params.categories)
            if params.season:
                newznab_params["season"] = params.season
            if params.ep:
                newznab_params["ep"] = params.ep

            # Make request to Newznab proxy endpoint (outside /api/v1)
            response = http_requests.get(
                f"{self.base_url}/{indexer.id}/api",
                params=newznab_params,
                timeout=self.timeout,
                headers=self.headers,
            )
        else:
            response = self.session.get(
                "/search",
                params=request_params,
                timeout=self.timeout,
                headers=self.headers,
            )

        if not response.ok:
            try:
                data = ScrapeErrorResponse.model_validate(response.json())
                message = data.message or "Unknown error"
            except Exception:
                message = response.text or "Unknown error"

            logger.debug(
                f"Failed to scrape {indexer.name}: [{response.status_code}] {message}"
            )

            self.indexers.remove(indexer)

            logger.debug(
                f"Removed indexer {indexer.name} from the list of usable indexers"
            )

            return {}

        if use_newznab:
            # Newznab returns XML (RSS format), parse it
            data = self._parse_newznab_response(response.text)
        else:
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
