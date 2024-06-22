""" Torrentio scraper module """
from typing import Dict, Union

from program.media.item import Episode, MediaItem, Movie, Season, Show
from program.settings.manager import settings_manager
from program.settings.models import TorrentioConfig
from requests import ConnectTimeout, ReadTimeout
from requests.exceptions import RequestException
from utils.logger import logger
from utils.request import RateLimiter, RateLimitExceeded, get, ping


class Torrentio:
    """Scraper for `Torrentio`"""

    def __init__(self):
        self.key = "torrentio"
        self.settings: TorrentioConfig = settings_manager.settings.scraping.torrentio
        self.timeout: int = self.settings.timeout
        self.ratelimit: bool = self.settings.ratelimit
        self.initialized: bool = self.validate()
        if not self.initialized:
            return
        self.hour_limiter: RateLimiter | None = RateLimiter(max_calls=1, period=5) if self.ratelimit else None
        self.running: bool = True
        logger.success("Torrentio initialized!")

    def validate(self) -> bool:
        """Validate the Torrentio settings."""
        if not self.settings.enabled:
            logger.warning("Torrentio is set to disabled.")
            return False
        if not self.settings.url:
            logger.error("Torrentio URL is not configured and will not be used.")
            return False
        if not isinstance(self.timeout, int) or self.timeout <= 0:
            logger.error("Torrentio timeout is not set or invalid.")
            return False
        if not isinstance(self.settings.ratelimit, bool):
            logger.error("Torrentio ratelimit must be a valid boolean.")
            return False
        try:
            url = f"{self.settings.url}/{self.settings.filter}/manifest.json"
            response = ping(url=url, timeout=10)
            if response.ok:
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
            if self.hour_limiter:
                self.hour_limiter.limit_hit()
            else:
                logger.warning(f"Torrentio ratelimit exceeded for item: {item.log_string}")
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
            else:
                logger.error(f"Invalid media item type")
                return None, None, None
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

        if self.hour_limiter:
            with self.hour_limiter:
                response = get(f"{url}.json", timeout=self.timeout)
        else:
            response = get(f"{url}.json", timeout=self.timeout)
        if not response.is_ok or not response.data.streams:
            return {}, 0

        torrents: Dict[str, str] = {}
        for stream in response.data.streams:
            if not stream.infoHash:
                continue

            # For Movies and Episodes, we want the file name instead of the torrent title
            # This should help with Special episodes and other misc. names
            stream_title = stream.title.split("\n👤")[0]
            raw_title = stream_title.split("\n")[-1].split("/")[-1] if isinstance(item, Episode) else stream_title.split("\n")[0]
            torrents[stream.infoHash] = raw_title

        return torrents, len(response.data.streams)
