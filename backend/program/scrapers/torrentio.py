""" Torrentio scraper module """
import os
from typing import Optional
from pydantic import BaseModel
from requests import ConnectTimeout, ReadTimeout
from requests.exceptions import RequestException
from utils.logger import logger
from utils.request import RateLimitExceeded, get, RateLimiter, ping
from utils.settings import settings_manager
from utils.parser import parser


class TorrentioConfig(BaseModel):
    enabled: bool
    url: Optional[str]
    filter: Optional[str]


class Torrentio:
    """Scraper for `Torrentio`"""

    def __init__(self, _):
        self.key = "torrentio"
        self.settings = TorrentioConfig(**settings_manager.get(f"scraping.{self.key}"))
        self.minute_limiter = RateLimiter(max_calls=60, period=60, raise_on_limit=True)
        self.second_limiter = RateLimiter(max_calls=1, period=10)
        self.initialized = self.validate_settings()
        if not self.initialized:
            return
        self.parse_logging = False
        logger.info("Torrentio initialized!")

    def validate_settings(self) -> bool:
        """Validate the Torrentio settings."""
        if not self.settings.enabled:
            logger.debug("Torrentio is set to disabled.")
            return False
        if not self.settings.url:
            logger.error("Torrentio URL is not configured and will not be used.")
            return False
        try:
            url = f"{self.settings.url}/{self.settings.filter}/stream/movie/tt0068646.json"
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
        if item is None or not self.initialized:
            return
        try:
            self._scrape_item(item)
        except RateLimitExceeded:
            self.minute_limiter.limit_hit()
            logger.warn("Torrentio rate limit hit for item: %s", item.log_string)
            return
        except ConnectTimeout:
            self.minute_limiter.limit_hit()
            logger.warn("Torrentio connection timeout for item: %s", item.log_string)
            return
        except ReadTimeout:
            self.minute_limiter.limit_hit()
            return
        except RequestException as e:
            self.minute_limiter.limit_hit()
            logger.warn("Torrentio request exception: %s", e)
            return
        except AttributeError:
            # TODO: will fix later
            self.minute_limiter.limit_hit()
            return
        except Exception as e:
            self.minute_limiter.limit_hit()
            logger.warn("Torrentio failed to scrape item: %s", e)
            return

    def _scrape_item(self, item):
        """Scrape torrentio for the given media item"""
        data, stream_count = self.api_scrape(item)
        if len(data) > 0:
            item.streams.update(data)
            logger.info("Found %s streams out of %s for %s", len(data), stream_count, item.log_string)
        else:
            if stream_count > 0:
                logger.debug("Could not find good streams for %s out of %s", item.log_string, stream_count)

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
                f"{self.settings.url}/{self.settings.filter}"
                + f"/stream/{scrape_type}/{imdb_id}"
            )
            if identifier:
                url += identifier
            with self.second_limiter:
                response = get(f"{url}.json", retry_if_failed=False, timeout=60)
            if response.is_ok and len(response.data.streams) > 0:
                parsed_data_list = [
                    parser.parse(item, stream.title.split("\n👤")[0].split("\n")[0]) for stream in response.data.streams
                ]
                data = {
                    stream.infoHash: {"name": stream.title.split("\n👤")[0].split("\n")[0]}
                    for stream, parsed_data in zip(response.data.streams, parsed_data_list)
                    if parsed_data.get("fetch", False) and parsed_data.get("string", False)
                }
                if self.parse_logging:
                    for parsed_data in parsed_data_list:
                        logger.debug("Torrentio Fetch: %s - Parsed item: %s", parsed_data["fetch"], parsed_data["string"])
                if data:
                    item.parsed_data.extend(parsed_data_list)
                    return data, len(response.data.streams)
            return {}, 0
