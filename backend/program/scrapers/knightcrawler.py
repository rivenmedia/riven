""" Knightcrawler scraper module """
from typing import Dict

from program.media.item import Episode, MediaItem
from program.scrapers.shared import _get_stremio_identifier
from program.settings.manager import settings_manager
from requests import ConnectTimeout, ReadTimeout
from requests.exceptions import RequestException
from utils.logger import logger
from utils.request import RateLimiter, RateLimitExceeded, get, ping


class Knightcrawler:
    """Scraper for `Knightcrawler`"""

    def __init__(self):
        self.key = "knightcrawler"
        self.settings = settings_manager.settings.scraping.knightcrawler
        self.timeout = self.settings.timeout
        self.initialized = self.validate()
        if not self.initialized:
            return
        self.second_limiter = RateLimiter(max_calls=1, period=5) if self.settings.ratelimit else None
        logger.success("Knightcrawler initialized!")

    def validate(self) -> bool:
        """Validate the Knightcrawler settings."""
        if not self.settings.enabled:
            logger.warning("Knightcrawler is set to disabled.")
            return False
        if not self.settings.url:
            logger.error("Knightcrawler URL is not configured and will not be used.")
            return False
        if not isinstance(self.timeout, int) or self.timeout <= 0:
            logger.error("Knightcrawler timeout is not set or invalid.")
            return False
        if not isinstance(self.settings.ratelimit, bool):
            logger.error("Knightcrawler ratelimit must be a valid boolean.")
            return False
        try:
            url = f"{self.settings.url}/{self.settings.filter}/manifest.json"
            response = ping(url=url, timeout=self.timeout)
            if response.ok:
                return True
        except Exception as e:
            logger.error(f"Knightcrawler failed to initialize: {e}", )
            return False
        return True

    def run(self, item: MediaItem) -> Dict[str, str]:
        """Scrape the knightcrawler site for the given media items
        and update the object with scraped streams"""
        if not item:
            return {}

        try:
            return self.scrape(item)
        except RateLimitExceeded:
            if self.second_limiter:
                self.second_limiter.limit_hit()
        except ConnectTimeout:
            logger.warning(f"Knightcrawler connection timeout for item: {item.log_string}")
        except ReadTimeout:
            logger.warning(f"Knightcrawler read timeout for item: {item.log_string}")
        except RequestException as e:
            if e.response.status_code == 429:
                if self.second_limiter:
                    self.second_limiter.limit_hit()
                else:
                    logger.warning(f"Knightcrawler ratelimit exceeded for item: {item.log_string}")
            else:
                logger.error(f"Knightcrawler request exception: {e}")
        except Exception as e:
            logger.error(f"Knightcrawler exception thrown: {e}")
        return {}

    def scrape(self, item: MediaItem) -> Dict[str, str]:
        """Scrape the given media item"""
        data, stream_count = self.api_scrape(item)
        if data:
            logger.log("SCRAPER", f"Found {len(data)} streams out of {stream_count} for {item.log_string}")
        else:
            logger.log("NOT_FOUND", f"No streams found for {item.log_string}")
        return data

    def api_scrape(self, item: MediaItem) -> tuple[Dict[str, str], int]:
        """Wrapper for `Knightcrawler` scrape method"""
        identifier, scrape_type, imdb_id = _get_stremio_identifier(item)

        url = f"{self.settings.url}/{self.settings.filter}/stream/{scrape_type}/{imdb_id}"
        if identifier:
            url += identifier

        if self.second_limiter:
            with self.second_limiter:
                response = get(f"{url}.json", timeout=self.timeout)
        else:
            response = get(f"{url}.json", timeout=self.timeout)

        if not response.is_ok or len(response.data.streams) <= 0:
            return {}, 0

        torrents: Dict[str, str] = {}

        for stream in response.data.streams:
            if not stream.infoHash:
                continue

            # For Movies and Episodes, we want the file name instead of the torrent title
            # This should help with Special episodes and other misc. names
            stream_title = stream.title.split("\n")[:-1]
            joined_title = "\n".join(stream_title)
            raw_title = joined_title.split("/")[-1] if isinstance(item, Episode) else joined_title.split("\n")[0]

            torrents[stream.infoHash] = raw_title

        return torrents, len(response.data.streams)
