""" Torrentio scraper module """
from typing import Dict, Union

from requests import ConnectTimeout, ReadTimeout
from requests.exceptions import RequestException

from program.media.item import Episode, MediaItem, Movie, Season, Show
from program.settings.manager import settings_manager
from program.settings.models import TorrentioConfig
from utils.logger import logger
from utils.ratelimiter import RateLimiter, RateLimitExceeded
from utils.request import get, ping


class Torrentio:
    """Scraper for `Torrentio`"""

    def __init__(self):
        self.key = "torrentio"
        self.settings: TorrentioConfig = settings_manager.settings.scraping.torrentio
        self.timeout: int = self.settings.timeout
        self.initialized: bool = self.validate()
        if not self.initialized:
            return
        self.rate_limiter: RateLimiter = RateLimiter(max_calls=1, period=5)
        logger.success("Torrentio initialized!")

    def validate(self) -> bool:
        """Validate the Torrentio settings."""
        if not self.settings.enabled:
            return False
        if not self.settings.url:
            logger.error("Torrentio URL is not configured and will not be used.")
            return False
        if not isinstance(self.timeout, int) or self.timeout <= 0:
            logger.error("Torrentio timeout is not set or invalid.")
            return False
        try:
            url = f"{self.settings.url}/{self.settings.filter}/manifest.json"
            response = ping(url=url, timeout=10)
            if response.is_ok:
                return True
        except Exception as e:
            logger.error(f"Torrentio failed to initialize: {e}", )
            return False
        return True

    def run(self, item: MediaItem) -> Dict[str, str]:
        """Scrape the torrentio site for the given media items
        and update the object with scraped streams"""
        if not item:
            return {}

        try:
            # Returns a dict of {infoHash: raw_title}
            return self.scrape(item)
        except RateLimitExceeded:
            self.rate_limiter.limit_hit()
        except ConnectTimeout:
            logger.warning(f"Torrentio connection timeout for item: {item.log_string}")
        except ReadTimeout:
            logger.warning(f"Torrentio read timeout for item: {item.log_string}")
        except RequestException as e:
            logger.error(f"Torrentio request exception: {str(e)}")
        except Exception as e:
            logger.error(f"Torrentio exception thrown: {str(e)}")
        return {}

    def scrape(self, item: MediaItem) -> Dict[str, str]:
        """Scrape the given media item"""
        data, stream_count = self.api_scrape(item)
        if data:
            logger.log("SCRAPER", f"Found {len(data)} streams out of {stream_count} for {item.log_string}")
        else:
            logger.log("NOT_FOUND", f"No streams found for {item.log_string}")
        return data

    def _determine_scrape(self, item: Union[Show, Season, Episode, Movie]) -> tuple[str, str, str]:
        """Determine the scrape type and identifier for the given media item"""
        try:
            if isinstance(item, Show):
                identifier, scrape_type, imdb_id = f":{item.seasons[0].number}:1", "series", item.imdb_id
            elif isinstance(item, Season):
                identifier, scrape_type, imdb_id = f":{item.number}:1", "series", item.parent.imdb_id
            elif isinstance(item, Episode):
                identifier, scrape_type, imdb_id = f":{item.parent.number}:{item.number}", "series", item.parent.parent.imdb_id
            elif isinstance(item, Movie):
                identifier, scrape_type, imdb_id = None, "movie", item.imdb_id
            return identifier, scrape_type, imdb_id
        except Exception as e:
            logger.warning(f"Failed to determine scrape type or identifier for {item.log_string}: {e}")
            return None, None, None

    def api_scrape(self, item: MediaItem) -> tuple[Dict[str, str], int]:
        """Wrapper for `Torrentio` scrape method"""
        identifier, scrape_type, imdb_id = self._determine_scrape(item)
        if not imdb_id:
            return {}, 0

        url = f"{self.settings.url}/{self.settings.filter}/stream/{scrape_type}/{imdb_id}"
        if identifier:
            url += identifier

        response = get(f"{url}.json", timeout=self.timeout, specific_rate_limiter=self.rate_limiter)
        if not response.is_ok or not response.data.streams:
            return {}, 0

        torrents: Dict[str, str] = {}
        for stream in response.data.streams:
            if not stream.infoHash:
                continue

            stream_title = stream.title.split("\n👤")[0]
            raw_title = stream_title.split("\n")[0]
            torrents[stream.infoHash] = raw_title

        return torrents, len(response.data.streams)