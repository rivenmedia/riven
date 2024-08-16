""" Zilean scraper module """

from typing import Dict

from program.media.item import Episode, MediaItem, Season, Show
from program.settings.manager import settings_manager
from program.settings.models import AppModel
from requests import ConnectTimeout, ReadTimeout
from requests.exceptions import RequestException
from utils.logger import logger
from utils.ratelimiter import RateLimiter, RateLimitExceeded
from utils.request import get, ping


class Zilean:
    """Scraper for `Zilean`"""

    def __init__(self):
        self.key = "zilean"
        self.api_key = None
        self.downloader = None
        self.rate_limiter = None
        self.app_settings: AppModel = settings_manager.settings
        self.settings = self.app_settings.scraping.zilean
        self.timeout = self.settings.timeout
        self.initialized = self.validate()
        if not self.initialized:
            return
        if self.settings.ratelimit:
            self.rate_limiter = RateLimiter(max_calls=1, period=2)
        logger.success("Zilean initialized!")

    def validate(self) -> bool:
        """Validate the Zilean settings."""
        if not self.settings.enabled:
            logger.warning("Zilean is set to disabled.")
            return False
        if not self.settings.url:
            logger.error("Zilean URL is not configured and will not be used.")
            return False
        if not isinstance(self.timeout, int) or self.timeout <= 0:
            logger.error("Zilean timeout is not set or invalid.")
            return False
        if not isinstance(self.settings.ratelimit, bool):
            logger.error("Zilean ratelimit must be a valid boolean.")
            return False

        try:
            url = f"{self.settings.url}/healthchecks/ping"
            response = ping(url=url, timeout=self.timeout, specific_rate_limiter=self.rate_limiter)
            return response.is_ok
        except Exception as e:
            logger.error(f"Zilean failed to initialize: {e}")
            return False

    def run(self, item: MediaItem) -> Dict[str, str]:
        """Scrape the Zilean site for the given media items and update the object with scraped items"""
        if not item:
            return {}

        try:
            return self.scrape(item)
        except RateLimitExceeded:
            if self.rate_limiter:
                self.rate_limiter.limit_hit()
            else:
                logger.warning(f"Zilean ratelimit exceeded for item: {item.log_string}")
        except ConnectTimeout:
            logger.warning(f"Zilean connection timeout for item: {item.log_string}")
        except ReadTimeout:
            logger.warning(f"Zilean read timeout for item: {item.log_string}")
        except RequestException as e:
            logger.error(f"Zilean request exception: {e}")
        except Exception as e:
            logger.error(f"Zilean exception thrown: {e}")
        return {}

    def scrape(self, item: MediaItem) -> Dict[str, str]:
        """Scrape the given media item"""
        data, item_count = self.api_scrape(item)
        if data:
            logger.log("SCRAPER", f"Found {len(data)} entries out of {item_count} for {item.log_string}")
        else:
            logger.log("NOT_FOUND", f"No entries found for {item.log_string}")
        return data

    def api_scrape(self, item: MediaItem) -> tuple[Dict[str, str], int]:
        """Wrapper for `Zilean` scrape method"""
        title = item.get_top_title()
        if not title:
            return {}, 0

        url = f"{self.settings.url}/dmm/filtered"
        params = {"Query": title}

        if isinstance(item, MediaItem) and hasattr(item, "year"):
            params["Year"] = item.year

        if isinstance(item, Show):
            params["Season"] = 1
        elif isinstance(item, Season):
            params["Season"] = item.number
        elif isinstance(item, Episode):
            params["Season"] = item.parent.number
            params["Episode"] = item.number

        response = get(url, params=params, timeout=self.timeout, specific_rate_limiter=self.rate_limiter)

        if not response.is_ok or not response.data:
            return {}, 0

        torrents: Dict[str, str] = {}

        for result in response.data:
            if not result.raw_title or not result.info_hash:
                continue

            torrents[result.info_hash] = result.raw_title

        return torrents, len(response.data)