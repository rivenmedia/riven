""" Torrentio scraper module """
from typing import Optional
from pydantic import BaseModel
from requests.exceptions import RequestException
from utils.logger import logger
from utils.request import RateLimitExceeded, get, RateLimiter
from utils.settings import settings_manager
from utils.parser import parser


class TorrentioConfig(BaseModel):
    enabled: bool
    filter: Optional[str]


class Torrentio:
    """Scraper for `Torrentio`"""

    def __init__(self, _):
        self.key = "torrentio"
        self.settings = TorrentioConfig(**settings_manager.get(f"scraping.{self.key}"))
        self.minute_limiter = RateLimiter(max_calls=60, period=60, raise_on_limit=True)
        self.second_limiter = RateLimiter(max_calls=1, period=1)
        self.initialized = self.validate_settings()
        if not self.initialized:
            return
        logger.info("Torrentio initialized!")

    def validate_settings(self) -> bool:
        """Validate the Torrentio settings."""
        if not self.settings.enabled:
            logger.debug("Torrentio is set to disabled.")
            return False
        return True

    def run(self, item) -> None:
        """Scrape the torrentio site for the given media items
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
        data = self.api_scrape(item)
        if len(data) > 0:
            item.streams.update(data)
            logger.debug("Found %s streams for %s", len(data), item.log_string)
        else:
            logger.debug("Could not find streams for %s", item.log_string)

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
                f"https://torrentio.strem.fun/{self.settings.filter}"
                + f"/stream/{scrape_type}/{imdb_id}"
            )
            if identifier:
                url += f"{identifier}"
            with self.second_limiter:
                response = get(f"{url}.json", retry_if_failed=False)
            if response.is_ok:
                data = {}
                for stream in response.data.streams:
                    title = stream.title.split("\n👤")[0]
                    if parser.parse(title):
                        data[stream.infoHash] = {
                            "name": title,
                        }
                    # TODO: Sort data using parser and user preferences
                if len(data) > 0:
                    return data
            return {}
