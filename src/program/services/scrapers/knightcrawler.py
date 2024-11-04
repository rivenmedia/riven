""" Knightcrawler scraper module """
from typing import Dict

from loguru import logger
from requests import ConnectTimeout, ReadTimeout
from requests.exceptions import RequestException

from program.media.item import MediaItem
from program.services.scrapers.shared import _get_stremio_identifier
from program.settings.manager import settings_manager
from program.utils.request import get, ping, create_service_session, get_rate_limit_params, RateLimitExceeded

class Knightcrawler:
    """Scraper for `Knightcrawler`"""

    def __init__(self):
        self.key = "knightcrawler"
        self.settings = settings_manager.settings.scraping.knightcrawler
        self.timeout = self.settings.timeout
        rate_limit_params = get_rate_limit_params(max_calls=1, period=5) if self.settings.ratelimit else None
        self.session = create_service_session(rate_limit_params=rate_limit_params,use_cache=False)
        self.initialized = self.validate()
        if not self.initialized:
            return
        logger.success("Knightcrawler initialized!")

    def validate(self) -> bool:
        """Validate the Knightcrawler settings."""
        if not self.settings.enabled:
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
            response = ping(session=self.session, url=url, timeout=self.timeout)
            if response.is_ok:
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
            logger.warning(f"Knightcrawler rate limit exceeded for item: {item.log_string}")
        except ConnectTimeout:
            logger.warning(f"Knightcrawler connection timeout for item: {item.log_string}")
        except ReadTimeout:
            logger.warning(f"Knightcrawler read timeout for item: {item.log_string}")
        except RequestException as e:
            if e.response.status_code == 429:
                logger.warning(f"Knightcrawler ratelimit exceeded for item: {item.log_string}")
            else:
                logger.error(f"Knightcrawler request exception: {e}")
        except Exception as e:
            logger.error(f"Knightcrawler exception thrown: {e}")
        return {}

    def scrape(self, item: MediaItem) -> Dict[str, str]:
        """Wrapper for `Knightcrawler` scrape method"""
        identifier, scrape_type, imdb_id = _get_stremio_identifier(item)

        url = f"{self.settings.url}/{self.settings.filter}/stream/{scrape_type}/{imdb_id}"
        if identifier:
            url += identifier

        response = get(session=self.session, url=f"{url}.json", timeout=self.timeout)

        if not response.is_ok or len(response.data.streams) <= 0:
            return {}

        torrents = {
            stream.infoHash: "\n".join(stream.title.split("\n")[:-1]).split("\n")[0]
            for stream in response.data.streams
            if stream.infoHash
        }

        if torrents:
            logger.log("SCRAPER", f"Found {len(torrents)} streams for {item.log_string}")
        else:
            logger.log("NOT_FOUND", f"No streams found for {item.log_string}")

        return torrents