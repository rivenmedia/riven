""" Jackett scraper module """
from typing import Optional
from pydantic import BaseModel
from requests import RequestException
from utils.logger import logger
from utils.request import RateLimitExceeded, get
from utils.settings import settings_manager
from utils.utils import parser
from utils.request import get, RateLimiter


class JackettConfig(BaseModel):
    enabled: bool
    url: Optional[str]
    api_key: Optional[str]


class Jackett:
    """Scraper for `Jackett`"""

    def __init__(self, _):
        self.key = "jackett"
        self.settings = JackettConfig(**settings_manager.get(f"scraping.{self.key}"))
        self.initialized = self.validate_settings()
        if not self.initialized:
            return
        self.minute_limiter = RateLimiter(max_calls=60, period=60, raise_on_limit=True)
        self.second_limiter = RateLimiter(max_calls=1, period=1)
        logger.info("Jackett initialized!")

    def validate_settings(self) -> bool:
        """Validate the Jackett settings."""
        if not self.settings.enabled:
            logger.debug("Jackett is set to disabled.")
            return False
        if len(self.settings.api_key) == 32 and self.settings.url:
            try:
                response = get(
                    f"{self.settings.url}/api/v2.0/indexers/!status:failing,test:passed/results/torznab?apikey={self.settings.api_key}&t=search&q=test"
                    , timeout=30)
                if response.is_ok:
                    return True
            except Exception as e:
                logger.error(f"Jackett configuration error: {e}")
        else:
            logger.info("Jackett is not configured and will not be used.")

    def run(self, item):
        """Scrape the jackett site for the given media items
        and update the object with scraped streams"""
        try:
            self._scrape_item(item)
        except RequestException:
            self.minute_limiter.limit_hit()
            return
        except RateLimitExceeded:
            self.minute_limiter.limit_hit()
            return

    def _scrape_item(self, item):
        """Scrape the given media item"""
        data = self.api_scrape(item)
        if len(data) > 0:
            item.streams.update(data)
            logger.debug("Found %s streams for %s", len(data), item.log_string)
        else:
            logger.debug("Could not find streams for %s", item.log_string)

    def api_scrape(self, item):
        """Wrapper for torrentio scrape method"""
        query = ""
        if item.type == "movie":
            query = f"&t=movie&imdbid={item.imdb_id}"
        if item.type == "season":
            query = f"&t=tv-search&imdbid={item.parent.imdb_id}&season={item.number}"
        if item.type == "episode":
            query = f"&t=tv-search&imdbid={item.parent.parent.imdb_id}&season={item.parent.number}&ep={item.number}"

        url = (
            f"{self.settings.url}/api/v2.0/indexers/!status:failing,test:passed/results/torznab?apikey={self.settings.api_key}{query}"
        )
        response = get(url=url, retry_if_failed=False, timeout=30)
        if response.is_ok:
            data = {}
            if not hasattr(response.data['rss']['channel'], "item"):
                return {}
            for stream in response.data['rss']['channel']['item']:
                title = stream.get('title')
                for attr in stream.get('torznab:attr', []):
                    if attr.get('@name') == 'infohash':
                        infohash = attr.get('@value')
                if parser.parse(title) and infohash:
                    data[infohash] = {"name": title}
            if len(data) > 0:
                return data
        return {}