""" Jackett scraper module """
from typing import Optional
from pydantic import BaseModel
from requests import ReadTimeout, RequestException
from utils.logger import logger
from utils.settings import settings_manager
from utils.parser import parser
from utils.request import RateLimitExceeded, get, RateLimiter


class JackettConfig(BaseModel):
    enabled: bool
    url: Optional[str]


class Jackett:
    """Scraper for `Jackett`"""

    def __init__(self, _):
        self.key = "jackett"
        self.api_key = None
        self.settings = JackettConfig(**settings_manager.get(f"scraping.{self.key}"))
        self.initialized = self.validate_settings()
        if not self.initialized and not self.api_key:
            return
        self.minute_limiter = RateLimiter(max_calls=60, period=60, raise_on_limit=True)
        self.second_limiter = RateLimiter(max_calls=1, period=3)
        logger.info("Jackett initialized!")

    def validate_settings(self) -> bool:
        """Validate Jackett settings."""
        if not self.settings.enabled:
            logger.debug("Jackett is set to disabled.")
            return False
        if self.settings.url:
            try:
                url = f"{self.settings.url}/api/v2.0/server/config"
                response = get(url=url, retry_if_failed=False, timeout=60)
                if response.is_ok and response.data.api_key is not None:
                    self.api_key = response.data.api_key
                    return True
            except ReadTimeout:
                return True
            except Exception:
                return False
        logger.info("Jackett is not configured and will not be used.")
        return False

    def run(self, item):
        """Scrape Jackett for the given media items"""
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
        """Wrapper for `Jackett` scrape method"""
        # https://github.com/Jackett/Jackett/wiki/Jackett-Categories
        with self.minute_limiter:
            query = ""
            if item.type == "movie":
                query = f"&cat=2000,2010,2020,2030,2040,2045,2050,2080&t=movie&q={item.title}&year{item.aired_at.year}"
            if item.type == "season":
                query = f"&cat=5000,5010,5020,5030,5040,5045,5050,5060,5070,5080&t=tvsearch&q={item.parent.title}&season={item.number}"
            if item.type == "episode":
                query = f"&cat=5000,5010,5020,5030,5040,5045,5050,5060,5070,5080&t=tvsearch&q={item.parent.parent.title}&season={item.parent.number}&ep={item.number}"
            url = (f"{self.settings.url}/api/v2.0/indexers/!status:failing,test:passed/results/torznab?apikey={self.api_key}{query}")
            with self.second_limiter:
                response = get(url=url, retry_if_failed=False, timeout=60)
            if response.is_ok:
                data = {}
                streams = response.data["rss"]["channel"].get("item", [])
                parsed_data_list = [parser.parse(item, stream.get("title")) for stream in streams]
                for stream, parsed_data in zip(streams, parsed_data_list):
                    if parsed_data.get("fetch", True) and parsed_data.get("title_match", False):
                        attr = stream.get("torznab:attr", [])
                        infohash_attr = next((a for a in attr if a.get("@name") == "infohash"), None)
                        if infohash_attr:
                            infohash = infohash_attr.get("@value")
                            data[infohash] = {"name": stream.get("title")}
                if data:
                    item.parsed_data = parsed_data_list
                    return data
                return {}
