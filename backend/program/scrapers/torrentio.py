""" Torrentio scraper module """
from datetime import datetime
from requests import ConnectTimeout, ReadTimeout
from requests.exceptions import RequestException
from utils.logger import logger
from utils.request import RateLimitExceeded, get, RateLimiter, ping
from program.settings.manager import settings_manager
from utils.parser import parser
from program.media.item import Show, Episode, Season
import traceback

class Torrentio:
    """Scraper for `Torrentio`"""

    def __init__(self):
        self.key = "torrentio"
        self.settings = settings_manager.settings.scraping.torrentio
        self.minute_limiter = RateLimiter(
            max_calls=300, period=3600, raise_on_limit=True
        )
        self.second_limiter = RateLimiter(max_calls=1, period=1)
        self.initialized = self.validate()
        if not self.initialized:
            return
        self.parse_logging = False
        logger.info("Torrentio initialized!")

    def validate(self) -> bool:
        """Validate the Torrentio settings."""
        if not self.settings.enabled:
            logger.debug("Torrentio is set to disabled.")
            return False
        if not self.settings.url:
            logger.error("Torrentio URL is not configured and will not be used.")
            return False
        try:
            url = f"{self.settings.url}/{self.settings.filter}/manifest.json"
            response = ping(url=url, timeout=10)
            if response.ok:
                return True
        except Exception as e:
            logger.exception("Torrentio failed to initialize: %s", e)
            return False
        return True

    def run(self, item):
        """Scrape the torrentio site for the given media items
        and update the object with scraped streams"""
        item.scraped_at = datetime.now()
        item.scraped_times += 1
        if item is None or isinstance(item, Show):
            yield item
        try:
            item = self._scrape_item(item)
        except RateLimitExceeded:
            self.minute_limiter.limit_hit()
        except ConnectTimeout:
            self.minute_limiter.limit_hit()
            logger.warn("Torrentio connection timeout for item: %s", item.log_string)
        except ReadTimeout:
            self.minute_limiter.limit_hit()
            logger.warn("Torrentio read timeout for item: %s", item.log_string)
        except RequestException as e:
            self.minute_limiter.limit_hit()
            logger.warn("Torrentio request exception: %s", e)
        except Exception as e:
            self.minute_limiter.limit_hit()
            logger.warn("Torrentio exception thrown: %s", traceback.format_exc())
        yield item

    def _scrape_item(self, item):
        """Scrape torrentio for the given media item"""
        data, stream_count = self.api_scrape(item)
        if len(data) > 0:
            item.streams.update(data)
            logger.debug(
                "Found %s streams out of %s for %s",
                len(data),
                stream_count,
                item.log_string,
            )
        else:
            if stream_count > 0:
                logger.debug(
                    "Could not find good streams for %s out of %s",
                    item.log_string,
                    stream_count,
                )
            else:
                logger.debug("No streams found for %s", item.log_string)
        return item

    def api_scrape(self, item):
        """Wrapper for torrentio scrape method"""
        with self.minute_limiter:
            # Torrentio can't scrape shows
            if isinstance(item, Show):
                return item
            elif isinstance(item, Season):
                identifier = f":{item.number}:1"
                scrape_type = "series"
                imdb_id = item.parent.imdb_id
            elif isinstance(item, Episode):
                identifier = f":{item.parent.number}:{item.number}"
                scrape_type = "series"
                imdb_id = item.parent.parent.imdb_id
            else:
                identifier = None
                scrape_type = "movie"
                imdb_id = item.imdb_id

            url = (
                f"{self.settings.url}{self.settings.filter}"
                + f"/stream/{scrape_type}/{imdb_id}"
            )
            if identifier:
                url += identifier
            with self.second_limiter:
                response = get(f"{url}.json", retry_if_failed=False, timeout=60)
            if response.is_ok and len(response.data.streams) > 0:
                parsed_data_list = [
                    parser.parse(item, stream.title.split("\n👤")[0].split("\n")[0])
                    for stream in response.data.streams
                ]
                data = {
                    stream.infoHash: {
                        "name": stream.title.split("\n👤")[0].split("\n")[0],
                        "cached": None
                    }
                    for stream, parsed_data in zip(
                        response.data.streams, parsed_data_list
                    )
                    if parsed_data.get("fetch", False)
                    and parsed_data.get("string", False)
                }
                if self.parse_logging:  # For debugging parser large data sets
                    for parsed_data in parsed_data_list:
                        logger.debug(
                            "Torrentio Fetch: %s - Parsed item: %s",
                            parsed_data["fetch"],
                            parsed_data["string"],
                        )
                if data:
                    item.parsed_data.extend(parsed_data_list)
                    return data, len(response.data.streams)
            return {}, 0
