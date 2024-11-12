from typing import Dict

from loguru import logger
from requests import RequestException
from requests.exceptions import ConnectTimeout

from program.media.item import MediaItem
from program.services.scrapers.shared import ScraperRequestHandler
from program.settings.manager import settings_manager
from program.utils.request import HttpMethod, RateLimitExceeded, create_service_session


class TorBoxScraper:
    def __init__(self):
        self.key = "torbox"
        self.settings = settings_manager.settings.scraping.torbox_scraper
        self.base_url = "http://search-api.torbox.app"
        self.headers = {"Authorization": f"Bearer {self.settings.api_key}"}
        self.timeout = self.settings.timeout
        session = create_service_session()
        self.request_handler = ScraperRequestHandler(session)
        self.initialized = self.validate()
        if not self.initialized:
            return
        logger.success("TorBox Scraper is initialized")

    def validate(self) -> bool:
        """Validate the TorBox Scraper as a service"""
        if not self.settings.enabled:
            return False
        if not self.settings.api_key:
            logger.error("TorBox API key is not set.")
            return False
        if not isinstance(self.timeout, int) or self.timeout <= 0:
            logger.error("TorBox timeout is not set or invalid.")
            return False
        try:
            response = self.request_handler.execute(HttpMethod.GET, f"{self.base_url}/torrents/imdb:tt0944947?metadata=false&season=1&episode=1", headers=self.headers, timeout=self.timeout)
            return response.is_ok
        except Exception as e:
            logger.exception(f"Error validating TorBox Scraper: {e}")
            return False

    def run(self, item: MediaItem) -> Dict[str, str]:
        """Scrape Torbox with the given media item for streams"""
        try:
            return self.scrape(item)
        except RateLimitExceeded:
            logger.debug(f"TorBox rate limit exceeded for item: {item.log_string}")
        except ConnectTimeout:
            logger.log("NOT_FOUND", f"TorBox is caching request for {item.log_string}, will retry later")
        except RequestException as e:
            if e.response and e.response.status_code == 418:
                logger.log("NOT_FOUND", f"TorBox has no metadata for item: {item.log_string}, unable to scrape")
            elif e.response and e.response.status_code == 500:
                logger.log("NOT_FOUND", f"TorBox is caching request for {item.log_string}, will retry later")
        except Exception as e:
            if "418 Client Error" in str(e):
                logger.log("NOT_FOUND", f"TorBox has no metadata for item: {item.log_string}, unable to scrape")
            else:
                logger.exception(f"TorBox exception thrown: {e}")
        return {}

    def _build_query_params(self, item: MediaItem) -> str:
        """Build the query params for the TorBox API"""
        imdb_id = item.get_top_imdb_id()
        if item.type == "movie":
            return f"torrents/imdb:{imdb_id}"
        elif item.type == "show":
            return f"torrents/imdb:{imdb_id}?season=1&episode=1"
        elif item.type == "season":
            return f"torrents/imdb:{imdb_id}?season={item.number}&episode=1"
        elif item.type == "episode":
            return f"torrents/imdb:{imdb_id}?season={item.parent.number}&episode={item.number}"
        return ""

    def scrape(self, item: MediaItem) -> Dict[str, str]:
        """Wrapper for `Torbox` scrape method using Torbox API"""
        query_params = self._build_query_params(item)
        url = f"{self.base_url}/{query_params}&metadata=false"

        response = self.request_handler.execute(HttpMethod.GET, url, headers=self.headers, timeout=self.timeout)
        if not response.is_ok or not response.data.data.torrents:
            logger.log("NOT_FOUND", f"No streams found for {item.log_string}")
            return {}

        torrents = {}
        for torrent_data in response.data.data.torrents:
            raw_title = torrent_data.raw_title
            info_hash = torrent_data.hash
            if not info_hash or not raw_title:
                continue

            torrents[info_hash] = raw_title

        if torrents:
            logger.log("SCRAPER", f"Found {len(torrents)} streams for {item.log_string}")
        else:
            logger.log("NOT_FOUND", f"No streams found for {item.log_string}")

        return torrents