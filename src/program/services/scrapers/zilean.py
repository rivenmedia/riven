""" Zilean scraper module """

from typing import Dict

from loguru import logger

from program.media.item import Episode, MediaItem, Season, Show
from program.services.scrapers.base import ScraperService
from program.settings.manager import settings_manager
from program.utils.request import SmartSession, get_hostname_from_url


class Zilean(ScraperService):
    """Scraper for `Zilean`"""

    def __init__(self):
        super().__init__("zilean")
        self.settings = settings_manager.settings.scraping.zilean
        self.timeout = self.settings.timeout
        if self.settings.ratelimit:
            rate_limits = {get_hostname_from_url(self.settings.url): {"rate": 500/60, "capacity": 500}}
        else:
            rate_limits = None
        self.session = SmartSession(rate_limits=rate_limits, retries=3, backoff_factor=0.3)
        self._initialize()

    def validate(self) -> bool:
        """Validate the Zilean settings."""
        if not self.settings.enabled:
            return False
        if not self.settings.url:
            logger.error("Zilean URL is not configured and will not be used.")
            return False
        if not isinstance(self.timeout, int) or self.timeout <= 0:
            logger.error("Zilean timeout is not set or invalid.")
            return False
        try:
            url = f"{self.settings.url}/healthchecks/ping"
            response = self.session.get(url, timeout=self.timeout)
            return response.ok
        except Exception as e:
            logger.error(f"Zilean failed to initialize: {e}")
            return False

    def run(self, item: MediaItem) -> Dict[str, str]:
        """Scrape the Zilean site for the given media items and update the object with scraped items"""
        try:
            return self.scrape(item)
        except Exception as e:
            if "rate limit" in str(e).lower() or "429" in str(e):
                logger.debug(f"Zilean rate limit exceeded for item: {item.log_string}")
            else:
                logger.exception(f"Zilean exception thrown: {e}")
        return {}

    def _build_query_params(self, item: MediaItem) -> Dict[str, str]:
        """Build the query params for the Zilean API"""
        params = {"Query": item.get_top_title()}
        if isinstance(item, Show):
            params["Season"] = 1
        elif isinstance(item, Season):
            params["Season"] = item.number
        elif isinstance(item, Episode):
            params["Season"] = item.parent.number
            params["Episode"] = item.number
        return params

    def scrape(self, item: MediaItem) -> Dict[str, str]:
        """Wrapper for `Zilean` scrape method"""
        url = f"{self.settings.url}/dmm/filtered"
        params = self._build_query_params(item)

        response = self.session.get(url, params=params, timeout=self.timeout)
        if not response.ok or not response.data:
            logger.log("NOT_FOUND", f"No streams found for {item.log_string}")
            return {}

        torrents: Dict[str, str] = {}
        for result in response.data:
            if not result.raw_title or not result.info_hash:
                continue
            torrents[result.info_hash] = result.raw_title

        if torrents:
            logger.log("SCRAPER", f"Found {len(torrents)} streams for {item.log_string}")
        else:
            logger.log("NOT_FOUND", f"No streams found for {item.log_string}")

        return torrents