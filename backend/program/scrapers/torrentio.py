""" Torrentio scraper module """

from program.media.item import Episode, Season, Show
from program.settings.manager import settings_manager
from program.versions.parser import ParsedTorrents, Torrent, check_title_match
from program.versions.rank_models import models
from requests import ConnectTimeout, ReadTimeout
from requests.exceptions import RequestException
from utils.logger import logger
from utils.request import RateLimiter, RateLimitExceeded, get, ping


class Torrentio:
    """Scraper for `Torrentio`"""

    def __init__(self):
        self.key = "torrentio"
        self.settings = settings_manager.settings.scraping.torrentio
        self.rank_profile = settings_manager.settings.ranking.profile
        self.ranking_model = None
        self.initialized = self.validate()
        if not self.initialized:
            return
        self.minute_limiter = RateLimiter(
            max_calls=300, period=3600, raise_on_limit=True
        )
        self.second_limiter = RateLimiter(max_calls=1, period=1)
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
            self.ranking_model = models.get(self.rank_profile)
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
        if item is None or isinstance(item, Show):
            yield item
        try:
            yield self._scrape_item(item)
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
            logger.warn("Torrentio exception thrown: %s", e)

    def _scrape_item(self, item):
        """Scrape the given media item"""
        data, stream_count = self.api_scrape(item)
        if len(data) > 0:
            item.streams.update(data.torrents)
            logger.debug(
                "Found %s streams out of %s for %s",
                len(data),
                stream_count,
                item.log_string,
            )
        elif stream_count > 0:
            logger.debug(
                "Could not find good streams for %s out of %s",
                item.log_string,
                stream_count,
            )
        else:
            logger.debug("No streams found for %s", item.log_string)
        return item

    def api_scrape(self, item) -> tuple[ParsedTorrents, int]:
        """Wrapper for `Torrentio` scrape method"""
        with self.minute_limiter:
            if isinstance(item, Season):
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
                f"{self.settings.url}/{self.settings.filter}"
                + f"/stream/{scrape_type}/{imdb_id}"
            )
            if identifier:
                url += identifier
            with self.second_limiter:
                response = get(f"{url}.json", retry_if_failed=False, timeout=60)
            if not response.is_ok or len(response.data.streams) <= 0:
                return {}, 0
            scraped_torrents = ParsedTorrents()
            for stream in response.data.streams:
                raw_title: str = stream.title.split("\n👤")[0].split("\n")[0]
                if not stream.infoHash or check_title_match(item, raw_title):
                    continue
                torrent: Torrent = Torrent(
                    self.ranking_model, raw_title=raw_title, infohash=stream.infoHash
                )
                if torrent and torrent.parsed_data.fetch:
                    scraped_torrents.add(torrent)
            scraped_torrents.sort()
            return scraped_torrents, len(response.data.streams)
