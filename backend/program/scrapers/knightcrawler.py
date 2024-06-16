""" Knightcrawler scraper module """
from typing import Dict, Generator

from program.media.item import Episode, MediaItem, Season, Show
from program.settings.manager import settings_manager
from program.settings.versions import models
from requests import ConnectTimeout, ReadTimeout
from requests.exceptions import RequestException
from RTN import RTN, Torrent, sort_torrents
from RTN.exceptions import GarbageTorrent
from utils.logger import logger
from utils.request import RateLimiter, RateLimitExceeded, get, ping


class Knightcrawler:
    """Scraper for `Knightcrawler`"""

    def __init__(self, hash_cache):
        self.key = "knightcrawler"
        self.settings = settings_manager.settings.scraping.knightcrawler
        self.settings_model = settings_manager.settings.ranking
        self.ranking_model = models.get(self.settings_model.profile)
        self.timeout = self.settings.timeout
        self.initialized = self.validate()
        if not self.initialized:
            return
        self.second_limiter = RateLimiter(max_calls=1, period=2) if self.settings.ratelimit else None
        self.rtn = RTN(self.settings_model, self.ranking_model)
        self.hash_cache = hash_cache
        logger.success("Knightcrawler initialized!")

    def validate(self) -> bool:
        """Validate the Knightcrawler settings."""
        if not self.settings.enabled:
            logger.warning("Knightcrawler is set to disabled.")
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
            response = ping(url=url, timeout=self.timeout)
            if response.ok:
                return True
        except Exception as e:
            logger.error(f"Knightcrawler failed to initialize: {e}", )
            return False
        return True

    def run(self, item: MediaItem) -> Generator[MediaItem, None, None]:
        """Scrape the knightcrawler site for the given media items
        and update the object with scraped streams"""
        if not item or isinstance(item, Show):
            yield item
            return

        try:
            yield self.scrape(item)
        except RateLimitExceeded:
            if self.second_limiter:
                self.second_limiter.limit_hit()
            else:
                logger.warning(f"Knightcrawler ratelimit exceeded for item: {item.log_string}")
        except ConnectTimeout:
            logger.warning(f"Knightcrawler connection timeout for item: {item.log_string}")
        except ReadTimeout:
            logger.warning(f"Knightcrawler read timeout for item: {item.log_string}")
        except RequestException as e:
            logger.error(f"Knightcrawler request exception: {e}")
        except Exception as e:
            logger.error(f"Knightcrawler exception thrown: {e}")
        yield item

    def scrape(self, item: MediaItem) -> MediaItem:
        """Scrape the given media item"""
        data, stream_count = self.api_scrape(item)
        if data:
            item.streams.update(data)
            logger.log("SCRAPER", f"Found {len(data)} streams out of {stream_count} for {item.log_string}")
        elif stream_count > 0:
            logger.log("NOT_FOUND", f"Could not find good streams for {item.log_string} out of {stream_count}")
        else:
            logger.log("NOT_FOUND", f"No streams found for {item.log_string}")
        return item

    def api_scrape(self, item: MediaItem) -> tuple[Dict[str, Torrent], int]:
        """Wrapper for `Knightcrawler` scrape method"""
        identifier, scrape_type, imdb_id = None, "movie", item.imdb_id
        if isinstance(item, Season):
            identifier, scrape_type, imdb_id = f":{item.number}:1", "series", item.parent.imdb_id
        elif isinstance(item, Episode):
            identifier, scrape_type, imdb_id = f":{item.parent.number}:{item.number}", "series", item.parent.parent.imdb_id

        url = f"{self.settings.url}/{self.settings.filter}/stream/{scrape_type}/{imdb_id}"
        if identifier:
            url += identifier

        if self.second_limiter:
            with self.second_limiter:
                response = get(f"{url}.json", timeout=self.timeout)
        else:
            response = get(f"{url}.json", timeout=self.timeout)

        if not response.is_ok or len(response.data.streams) <= 0:
            return {}, 0

        torrents = set()
        correct_title = item.get_top_title()
        if not correct_title:
            logger.scraper(f"Correct title not found for {item.log_string}")
            return {}, 0

        for stream in response.data.streams:
            raw_title = stream.title.split("\n👤")[0].split("\n")[0]
            if not stream.infoHash or not raw_title:
                continue
            if self.hash_cache and self.hash_cache.is_blacklisted(stream.infoHash):
                continue
            try:
                torrent = self.rtn.rank(raw_title=raw_title, infohash=stream.infoHash, correct_title=correct_title, remove_trash=True)
            except GarbageTorrent:
                continue
            if torrent and torrent.fetch:
                torrents.add(torrent)
        scraped_torrents = sort_torrents(torrents)
        return scraped_torrents, len(response.data.streams)
