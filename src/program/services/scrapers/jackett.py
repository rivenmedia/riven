""" Jackett scraper module """

import queue
import threading
import time
import xml.etree.ElementTree as ET
from typing import Dict, Generator, List, Optional, Tuple

import requests
from loguru import logger
from pydantic import BaseModel
from requests import HTTPError, ReadTimeout, RequestException, Timeout

from program.media.item import Episode, MediaItem, Movie, Season, Show
from program.services.scrapers.shared import ScraperRequestHandler
from program.settings.manager import settings_manager
from program.utils.request import (
    HttpMethod,
    RateLimitExceeded,
    ResponseType,
    create_service_session,
    get_http_adapter,
    get_rate_limit_params,
)


class JackettIndexer(BaseModel):
    """Indexer model for Jackett"""
    title: Optional[str] = None
    id: Optional[str] = None
    link: Optional[str] = None
    type: Optional[str] = None
    language: Optional[str] = None
    tv_search_capabilities: Optional[List[str]] = None
    movie_search_capabilities: Optional[List[str]] = None


class Jackett:
    """Scraper for `Jackett`"""

    def __init__(self):
        self.key = "jackett"
        self.api_key = None
        self.indexers = None
        self.settings = settings_manager.settings.scraping.jackett
        self.request_handler = None
        self.initialized = self.validate()
        if not self.initialized and not self.api_key:
            return
        logger.success("Jackett initialized!")

    def validate(self) -> bool:
        """Validate Jackett settings."""
        if not self.settings.enabled:
            return False
        if self.settings.url and self.settings.api_key:
            self.api_key = self.settings.api_key
            try:
                if not isinstance(self.settings.timeout, int) or self.settings.timeout <= 0:
                    logger.error("Jackett timeout is not set or invalid.")
                    return False
                if not isinstance(self.settings.ratelimit, bool):
                    logger.error("Jackett ratelimit must be a valid boolean.")
                    return False
                indexers = self._get_indexers()
                if not indexers:
                    logger.error("No Jackett indexers configured.")
                    return False
                self.indexers = indexers
                rate_limit_params = get_rate_limit_params(max_calls=len(self.indexers),
                                                          period=2) if self.settings.ratelimit else None
                http_adapter = get_http_adapter(pool_connections=len(self.indexers), pool_maxsize=len(self.indexers))
                session = create_service_session(rate_limit_params=rate_limit_params, session_adapter=http_adapter)
                self.request_handler = ScraperRequestHandler(session)
                self._log_indexers()
                return True
            except ReadTimeout:
                logger.error("Jackett request timed out. Check your indexers, they may be too slow to respond.")
                return False
            except Exception as e:
                logger.error(f"Jackett failed to initialize with API Key: {e}")
                return False
        logger.warning("Jackett is not configured and will not be used.")
        return False

    def run(self, item: MediaItem) -> Generator[MediaItem, None, None]:
        """Scrape the Jackett site for the given media items
        and update the object with scraped streams"""
        try:
            return self.scrape(item)
        except RateLimitExceeded:
            logger.debug(f"Jackett ratelimit exceeded for item: {item.log_string}")
        except RequestException as e:
            logger.error(f"Jackett request exception: {e}")
        except Exception as e:
            logger.error(f"Jackett failed to scrape item with error: {e}")
        return {}

    def scrape(self, item: MediaItem) -> Dict[str, str]:
        """Scrape the given media item"""
        results_queue = queue.Queue()
        threads = [
            threading.Thread(target=self._thread_target, args=(item, indexer, results_queue))
            for indexer in self.indexers
        ]

        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        results = []
        while not results_queue.empty():
            results.extend(results_queue.get())

        torrents: Dict[str, str] = {}
        for result in results:
            if result[1] is None:
                continue
            # infohash: raw_title
            torrents[result[1]] = result[0]

        if torrents:
            logger.log("SCRAPER", f"Found {len(torrents)} streams for {item.log_string}")
        else:
            logger.log("NOT_FOUND", f"No streams found for {item.log_string}")
        return torrents

    def _thread_target(self, item: MediaItem, indexer: JackettIndexer, results_queue: queue.Queue):
        """Thread target for searching indexers"""
        try:
            start_time = time.perf_counter()
            result = self._search_indexer(item, indexer)
            search_duration = time.perf_counter() - start_time
        except TypeError as e:
            logger.error(f"Invalid Type for {item.log_string}: {e}")
            result = []
            search_duration = 0
        item_title = item.log_string
        logger.debug(f"Scraped {item_title} from {indexer.title} in {search_duration:.2f} seconds with {len(result)} results")
        results_queue.put(result)

    def _search_indexer(self, item: MediaItem, indexer: JackettIndexer) -> List[Tuple[str, str]]:
        """Search for the given item on the given indexer"""
        if isinstance(item, Movie):
            return self._search_movie_indexer(item, indexer)
        elif isinstance(item, (Show, Season, Episode)):
            return self._search_series_indexer(item, indexer)
        else:
            raise TypeError("Only Movie and Series is allowed!")

    def _search_movie_indexer(self, item: MediaItem, indexer: JackettIndexer) -> List[Tuple[str, str]]:
        """Search for movies on the given indexer"""
        if indexer.movie_search_capabilities is None:
            return []
        params = {
            "apikey": self.api_key,
            "t": "movie",
            "cat": "2000",
            "q": item.title,
        }
        if indexer.movie_search_capabilities and "year" in indexer.movie_search_capabilities:
            if hasattr(item.aired_at, "year") and item.aired_at.year: params["year"] = item.aired_at.year
        if indexer.movie_search_capabilities and "imdbid" in indexer.movie_search_capabilities:
            params["imdbid"] = item.imdb_id

        url = f"{self.settings.url}/api/v2.0/indexers/{indexer.id}/results/torznab/api"
        return self._fetch_results(url, params, indexer.title, "movie")

    def _search_series_indexer(self, item: MediaItem, indexer: JackettIndexer) -> List[Tuple[str, str]]:
        """Search for series on the given indexer"""
        if indexer.tv_search_capabilities is None:
            return []
        q, season, ep = self._get_series_search_params(item)

        if not q:
            logger.debug(f"No search query found for {item.log_string}")
            return []

        params = {
            "apikey": self.api_key,
            "t": "tvsearch",
            "cat": "5000",
            "q": q
        }
        if ep and indexer.tv_search_capabilities and "ep" in indexer.tv_search_capabilities: params["ep"] = ep 
        if season and indexer.tv_search_capabilities and "season" in indexer.tv_search_capabilities: params["season"] = season
        if indexer.tv_search_capabilities and "imdbid" in indexer.tv_search_capabilities:
            params["imdbid"] = item.imdb_id if isinstance(item, (Episode, Show)) else item.parent.imdb_id

        url = f"{self.settings.url}/api/v2.0/indexers/{indexer.id}/results/torznab/api"
        return self._fetch_results(url, params, indexer.title, "series")

    def _get_series_search_params(self, item: MediaItem) -> Tuple[str, int, Optional[int]]:
        """Get search parameters for series"""
        title = item.get_top_title()
        if isinstance(item, Show):
            return title, None, None
        elif isinstance(item, Season):
            return title, item.number, None
        elif isinstance(item, Episode):
            return title, item.parent.number, item.number
        return title, None, None

    def _get_indexers(self) -> List[JackettIndexer]:
        """Get the indexers from Jackett"""
        url = f"{self.settings.url}/api/v2.0/indexers/all/results/torznab/api?apikey={self.api_key}&t=indexers&configured=true"
        try:
            response = requests.get(url)
            response.raise_for_status()
            return self._get_indexer_from_xml(response.text)
        except Exception as e:
            logger.error(f"Exception while getting indexers from Jackett: {e}")
            return []

    def _get_indexer_from_xml(self, xml_content: str) -> list[JackettIndexer]:
        """Parse the indexers from the XML content"""
        xml_root = ET.fromstring(xml_content)

        indexer_list = []
        for item in xml_root.findall(".//indexer"):
            indexer_data = {
                "title": item.find("title").text,
                "id": item.attrib["id"],
                "link": item.find("link").text,
                "type": item.find("type").text,
                "language": item.find("language").text.split("-")[0],
                "movie_search_capabilities": None,
                "tv_search_capabilities": None
            }
            movie_search = item.find(".//searching/movie-search[@available='yes']")
            tv_search = item.find(".//searching/tv-search[@available='yes']")
            if movie_search is not None:
                indexer_data["movie_search_capabilities"] = movie_search.attrib["supportedParams"].split(",")
            if tv_search is not None:
                indexer_data["tv_search_capabilities"] = tv_search.attrib["supportedParams"].split(",")
            indexer = JackettIndexer(**indexer_data)
            indexer_list.append(indexer)
        return indexer_list

    def _fetch_results(self, url: str, params: Dict[str, str], indexer_title: str, search_type: str) -> List[Tuple[str, str]]:
        """Fetch results from the given indexer"""
        try:
            response = self.request_handler.execute(HttpMethod.GET, url, params=params, timeout=self.settings.timeout)
            return self._parse_xml(response.response.text)
        except RateLimitExceeded:
            logger.warning(f"Rate limit exceeded while fetching results for {search_type}: {indexer_title}")
            return []
        except (HTTPError, ConnectionError, Timeout):
            logger.debug(f"Indexer failed to fetch results for {search_type}: {indexer_title}")
        except Exception as e:
            if "Jackett.Common.IndexerException" in str(e):
                logger.error(f"Indexer exception while fetching results from {indexer_title} ({search_type}): {e}")
            else:
                logger.error(f"Exception while fetching results from {indexer_title} ({search_type}): {e}")
        return []

    def _parse_xml(self, xml_content: str) -> list[tuple[str, str]]:
        """Parse the torrents from the XML content"""
        xml_root = ET.fromstring(xml_content)
        result_list = []
        for item in xml_root.findall(".//item"):
            infoHash = item.find(
                ".//torznab:attr[@name='infohash']",
                namespaces={"torznab": "http://torznab.com/schemas/2015/feed"}
            )
            if infoHash is None or len(infoHash.attrib["value"]) != 40:
                continue
            result_list.append((item.find(".//title").text, infoHash.attrib["value"]))
        return result_list

    def _log_indexers(self) -> None:
        """Log the indexers information"""
        for indexer in self.indexers:
            # logger.debug(f"Indexer: {indexer.title} - {indexer.link} - {indexer.type}")
            if not indexer.movie_search_capabilities:
                logger.debug(f"Movie search not available for {indexer.title}")
            if not indexer.tv_search_capabilities:
                logger.debug(f"TV search not available for {indexer.title}")