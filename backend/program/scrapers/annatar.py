""" Annatar scraper module """
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


class Annatar:
    """Scraper for `Annatar`"""

    def __init__(self, hash_cache):
        self.key = "annatar"
        self.url = None
        self.settings = settings_manager.settings.scraping.annatar
        self.settings_model = settings_manager.settings.ranking
        self.ranking_model = models.get(self.settings_model.profile)
        self.query_limits = "limit=2000&timeout=10"
        self.initialized = self.validate()
        if not self.initialized:
            return
        self.minute_limiter = RateLimiter(
            max_calls=3456, period=3600, raise_on_limit=True
        )
        self.second_limiter = RateLimiter(max_calls=1, period=5)
        self.rtn = RTN(self.settings_model, self.ranking_model)
        self.hash_cache = hash_cache
        logger.success("Annatar initialized!")

    def validate(self) -> bool:
        """Validate the Annatar settings."""
        if not self.settings.enabled:
            logger.warning("Annatar is set to disabled.")
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
            url = self.settings.url if self.settings.url.endswith("/manifest.json") else self.settings.url + "/manifest.json"
            response = ping(url=url, timeout=60)
            if not response.ok:
                return False
            return True
        except ReadTimeout:
            logger.debug("Annatar read timeout during initialization.")
            return False
        except Exception as e:
            logger.exception(f"Annatar failed to initialize: {e}")
            return False

    def run(self, item: MediaItem) -> Generator[MediaItem, None, None]:
        """Scrape the Annatar site for the given media items
        and update the object with scraped streams"""
        if not item:
            yield item
            return

        try:
            yield self.scrape(item)
        except RateLimitExceeded:
            self.minute_limiter.limit_hit()
            self.second_limiter.limit_hit()
            logger.warning(f"Annatar rate limit hit for item: {item.log_string}")
        except ConnectTimeout:
            self.minute_limiter.limit_hit()
            self.second_limiter.limit_hit()
        except ReadTimeout:
            self.second_limiter.limit_hit()
            logger.warning(f"Annatar read timeout for item: {item.log_string}")
        except RequestException as e:
            if e.response.status_code == 525:
                logger.error(f"Annatar SSL handshake failed for item: {item.log_string}")
            elif e.response.status_code == 429:
                self.minute_limiter.limit_hit()
                self.second_limiter.limit_hit()
            else:
                self.second_limiter.limit_hit()
                logger.exception(f"Annatar request exception: {e}")
        except Exception as e:
            self.second_limiter.limit_hit()
            logger.exception(f"Annatar failed to scrape item with error: {e}")
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
        """Wrapper for `Annatar` scrape method"""
        with self.minute_limiter:
            if(isinstance(item, Show)):
                identifier, scrape_type, imdb_id = None, "series", item.imdb_id
            elif isinstance(item, Season):
                identifier, scrape_type, imdb_id = f"season={item.number}", "series", item.parent.imdb_id
            elif isinstance(item, Episode):
                identifier, scrape_type, imdb_id = f"season={item.parent.number}&episode={item.number}", "series", item.parent.parent.imdb_id
            else:
                identifier, scrape_type, imdb_id = None, "movie", item.imdb_id

            if identifier is not None:
                url = f"{self.settings.url}/search/imdb/{scrape_type}/{imdb_id}?{identifier}&{self.query_limits}"
            else:
                url = f"{self.settings.url}/search/imdb/{scrape_type}/{imdb_id}?{self.query_limits}"

            with self.second_limiter:
                response = get(url, retry_if_failed=False, timeout=60)
            
            if not response.is_ok or len(response.data.media) <= 0:
                return {}, 0

            torrents = set()
            correct_title = item.get_top_title()
            if not correct_title:
                return {}, 0
            for stream in response.data.media:
                if not stream.hash:
                    continue

                if self.hash_cache.is_blacklisted(stream.hash):
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
