""" TorBox scraper module """
from pydantic import BaseModel
from requests import ReadTimeout, RequestException
from utils.request import RateLimitExceeded, RateLimiter, get, put
from utils.settings import settings_manager
from utils.logger import logger
from utils.parser import parser


class TorBoxConfig(BaseModel):
    enabled: bool

class TorBox:
    """Scraper for `TorBox`"""

    def __init__(self, _):
        self.key = "torbox"
        self.url = "https://api.torbox.app/v1/api/torrents"
        self.settings = TorBoxConfig(**settings_manager.get(f"scraping.{self.key}"))
        self.initialized = self.validate_settings()
        if not self.initialized:
            return
        self.minute_limiter = RateLimiter(max_calls=60, period=60, raise_on_limit=True)
        self.second_limiter = RateLimiter(max_calls=1, period=7)
        logger.info("TorBox initialized!")

    def validate_settings(self) -> bool:
        """Validate the TorBox settings."""
        if not self.settings.enabled:
            logger.debug("TorBox is set to disabled.")
            return False
        try:
            url = "https://api.torbox.app"
            response = get(url=url, retry_if_failed=False, timeout=60)
            if response.is_ok:
                if response.data.detail == "API is up and running.":
                    return True
        except ReadTimeout:
            return True
        except Exception:
            return False
        logger.info("TorBox is not configured and will not be used.")
        return False

    def run(self, item):
        """Scrape the TorBox API for the given media items
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
        """Wrapper for TorBox scrape method"""
        with self.minute_limiter:
            if item.type == "season":
                keyword_query = f"{item.parent.title}"
            elif item.type == "episode":
                keyword_query = f"{item.parent.parent.title}"
            elif item.type == "movie":
                keyword_query = f"{item.title} {item.year}"
            else:
                keyword_query = None

            if keyword_query:
                # Start search on server to get server to cache results
                put(f"{self.url}/storesearch?query={keyword_query}", retry_if_failed=False, timeout=30)
                with self.second_limiter:
                    # Fetch results from server
                    response = get(f"{self.url}/search?query={keyword_query}", retry_if_failed=False, timeout=30)
                if response.is_ok:
                    data = {}
                    if len(response.data.data) == 0:
                        return data
                    for stream in response.data.data:
                        if parser.check_for_title_match(item, stream.name):
                            if parser.parse(stream.name):
                                data[stream.hash] = {"name": stream.name}
                    if len(data) > 0:
                        return parser.sort_streams(data)
                return {}
