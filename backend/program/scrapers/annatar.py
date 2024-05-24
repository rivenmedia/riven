""" Annatar scraper module """
from typing import Dict

from program.media.item import Episode, Season, Show
from program.settings.manager import settings_manager
from program.settings.versions import models
from requests import ConnectTimeout, ReadTimeout
from requests.exceptions import RequestException
from RTN import RTN, Torrent, sort_torrents
from RTN.exceptions import GarbageTorrent
from utils.logger import logger
from utils.request import RateLimiter, RateLimitExceeded, get, ping


class Annatar:
    """Scraper for `Annatar`"""

    def __init__(self):
        self.key = "annatar"
        self.settings = settings_manager.settings.scraping.annatar
        self.settings_model = settings_manager.settings.ranking
        self.ranking_model = models.get(self.settings_model.profile)
        self.query_limits = None
        self.initialized = self.validate()
        if not self.initialized:
            return
        self.minute_limiter = RateLimiter(
            max_calls=100, period=3600, raise_on_limit=True
        )
        self.second_limiter = RateLimiter(max_calls=1, period=1)
        self.rtn = RTN(self.settings_model, self.ranking_model)
        logger.info("Annatar initialized!")

    def validate(self) -> bool:
        """Validate the Annatar settings."""
        if not self.settings.enabled:
            logger.debug("Annatar is set to disabled.")
            return False
        if not isinstance(self.settings.url, str) or not self.settings.url:
            logger.error("Annatar URL is not configured and will not be used.")
            return False
        if not isinstance(self.settings.limit, int) or self.settings.limit <= 0:
            logger.error("Annatar limit is not set or invalid.")
            return False
        if not isinstance(self.settings.timeout, int) or self.settings.timeout <= 0:
            logger.error("Annatar timeout is not set or invalid.")
            return False
        try:
            url = self.settings.url + "/manifest.json"
            response = ping(url=url, timeout=60)
            if not response.ok:
                return False
            self.query_limits = (
                f"limit={self.settings.limit}&timeout={self.settings.timeout}"
            )
            return True
        except ReadTimeout:
            logger.debug("Annatar read timeout during initialization.")
            return False
        except Exception as e:
            logger.exception("Annatar failed to initialize: %s", e)
            return False

    def run(self, item):
        """Scrape the Annatar site for the given media items
        and update the object with scraped streams"""
        if not item or isinstance(item, Show):
            yield item
        try:
            yield self._scrape_item(item)
        except RateLimitExceeded:
            self.minute_limiter.limit_hit()
        except ConnectTimeout:
            self.minute_limiter.limit_hit()
            logger.exception("Annatar connection timeout for item: %s", item.log_string)
        except ReadTimeout:
            self.minute_limiter.limit_hit()
            logger.exception("Annatar read timeout for item: %s", item.log_string)
        except RequestException as e:
            self.minute_limiter.limit_hit()
            logger.exception("Annatar request exception: %s", e)
        except Exception as e:
            self.minute_limiter.limit_hit()
            logger.exception("Annatar exception thrown: %s", e)
        return item

    def _scrape_item(self, item):
        """Scrape the given media item"""
        data, stream_count = self.api_scrape(item)
        if len(data) > 0:
            item.streams.update(data)
            logger.info(
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

    def api_scrape(self, item) -> tuple[Dict, int]:
        """Wrapper for `Annatar` scrape method"""
        with self.minute_limiter:
            if isinstance(item, Season):
                scrape_type = "series"
                imdb_id = item.parent.imdb_id
                identifier = f"season={item.number}"
            elif isinstance(item, Episode):
                scrape_type = "series"
                imdb_id = item.parent.parent.imdb_id
                identifier = f"season={item.parent.number}&episode={item.number}"
            else:
                identifier = None
                scrape_type = "movie"
                imdb_id = item.imdb_id

            if identifier is not None:
                url = (
                    f"{self.settings.url}/search/imdb/{scrape_type}/{imdb_id}?"
                    + f"{identifier}&{self.query_limits}"
                )
            else:
                url = (
                    f"{self.settings.url}/search/imdb/{scrape_type}/{imdb_id}?"
                    + f"{self.query_limits}"
                )

            with self.second_limiter:
                response = get(url, retry_if_failed=False, timeout=60)
            if not response.is_ok or len(response.data.media) <= 0:
                return {}, 0
            torrents = set()
            correct_title = item.get_top_title()
            if not correct_title:
                logger.error("Correct title not found for %s", item.log_string)
                return {}, 0
            for stream in response.data.media:
                if not stream.hash:
                    continue
                try:
                    torrent: Torrent = self.rtn.rank(
                        raw_title=stream.title, infohash=stream.hash, correct_title=correct_title, remove_trash=True
                    )
                except GarbageTorrent:
                    continue
                if torrent and torrent.fetch:
                    torrents.add(torrent)
            scraped_torrents = sort_torrents(torrents)
            return scraped_torrents, len(response.data.media)
