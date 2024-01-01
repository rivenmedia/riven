""" Torrentio scraper module """
from requests import RequestException
from utils.request import RateLimitExceeded, get, RateLimiter
from utils.settings import settings_manager
from utils.utils import parser
from utils.logger import logger
from .common import BaseScraper


class Torrentio(BaseScraper):
    """Scraper for Torrentio"""

    def __init__(self):
        self.settings = "torrentio"
        self.class_settings = settings_manager.get(self.settings)
        self.last_scrape = 0
        self.filters = self.class_settings["filter"]
        self.minute_limiter = RateLimiter(max_calls=60, period=60, raise_on_limit=True)
        self.second_limiter = RateLimiter(max_calls=1, period=1)
        self.initialized = True

    def validate_settings(self) -> bool:
        """Since Torrentio is a public scraper, we don't need to validate settings"""
        return True

    def run(self, item):
        """Scrape the torrentio site for the given media items
        and update the object with scraped streams"""
        if self._can_we_scrape(item):
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
        log_string = self._build_log_string(item)
        if len(data) > 0:
            item.set("streams", data)
            logger.debug("Found %s streams for %s", len(data), log_string)
        else:
            logger.debug("Could not find streams for %s", log_string)

    def api_scrape(self, item):
        """Wrapper for torrentio scrape method"""
        with self.minute_limiter:
            if item.type == "season":
                identifier = f":{item.number}:1"
                scrape_type = "series"
                imdb_id = item.parent.imdb_id
            elif item.type == "episode":
                identifier = f":{item.parent.number}:{item.number}"
                scrape_type = "series"
                imdb_id = item.parent.parent.imdb_id
            else:
                identifier = None
                scrape_type = "movie"
                imdb_id = item.imdb_id

            url = (
                f"https://torrentio.strem.fun/{self.filters}"
                + f"/stream/{scrape_type}/{imdb_id}"
            )
            if identifier:
                url += f"{identifier}"
            with self.second_limiter:
                response = get(f"{url}.json", retry_if_failed=False)
            if response.is_ok:
                data = {}
                for stream in response.data.streams:
                    if parser.parse(stream.title):
                        data[stream.infoHash] = {
                            "name": stream.title.split("\n👤")[0],
                        }
                if len(data) > 0:
                    return data
            return {}
