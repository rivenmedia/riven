from typing import Dict, Generator

from program.media.item import Episode, MediaItem, Movie, Season, Show
from program.settings.manager import settings_manager
from program.settings.versions import models
from requests import RequestException
from requests.exceptions import ConnectTimeout, ReadTimeout, RetryError
from RTN import RTN, Torrent, sort_torrents
from RTN.exceptions import GarbageTorrent
from utils.logger import logger
from utils.request import RateLimiter, RateLimitExceeded, get, ping


class TorBoxScraper:
    def __init__(self, hash_cache):
        self.key = "torbox"
        self.settings = settings_manager.settings.scraping.torbox_scraper
        self.settings_model = settings_manager.settings.ranking
        self.ranking_model = models.get(self.settings_model.profile)
        self.base_url = "http://search-api.torbox.app"
        self.user_plan = None
        self.initialized = self.validate()
        if not self.initialized:
            return
        self.minute_limiter = RateLimiter(max_calls=300, period=60, raise_on_limit=False)
        self.second_limiter = RateLimiter(max_calls=1, period=5, raise_on_limit=False)
        self.rtn = RTN(self.settings_model, self.ranking_model)
        self.hash_cache = hash_cache
        logger.success("TorBox Scraper is initialized")

    def validate(self) -> bool:
        """Validate the TorBox Scraper as a service"""
        if not self.settings.enabled:
            logger.warning("TorBox Scraper is set to disabled")
            return False

        try:
            response = ping(f"{self.base_url}/torrents/imdb:tt0944947?metadata=false&season=1&episode=1", timeout=60)
            return response.ok
        except Exception as e:
            logger.exception(f"Error validating TorBox Scraper: {e}")
            return False

    def run(self, item: MediaItem) -> Dict[str, Torrent]:
        """Scrape the TorBox site for the given media items
        and update the object with scraped streams"""
        if not item or isinstance(item, Show):
            return []

        try:
            return self.scrape(item)
        except Exception as e:
            self.minute_limiter.limit_hit()
            self.second_limiter.limit_hit()
            self.handle_exception(e, item)
        return []

    def handle_exception(self, e: Exception, item: MediaItem) -> None:
        """Handle exceptions during scraping"""
        if isinstance(e, RateLimitExceeded):
            logger.log("NOT_FOUND", f"TorBox is caching request for {item.log_string}, will retry later")
        elif isinstance(e, ConnectTimeout):
            logger.log("NOT_FOUND", f"TorBox is caching request for {item.log_string}, will retry later")
        elif isinstance(e, ReadTimeout):
            logger.warning(f"TorBox read timeout for item: {item.log_string}")
        elif isinstance(e, RetryError):
            logger.warning(f"TorBox retry error for item: {item.log_string}")
        elif isinstance(e, TimeoutError):
            logger.warning(f"TorBox timeout error for item: {item.log_string}")
        elif isinstance(e, RequestException):
            if e.response and e.response.status_code == 418:
                logger.log("NOT_FOUND", f"TorBox has no metadata for item: {item.log_string}, unable to scrape")
            elif e.response and e.response.status_code == 500:
                logger.log("NOT_FOUND", f"TorBox is caching request for {item.log_string}, will retry later")
        else:
            logger.error(f"TorBox exception thrown: {e}")
        

    def scrape(self, item: MediaItem) -> Dict[str, Torrent]:
        """Scrape the given item"""
        data, stream_count = self.api_scrape(item)
        if data:
            logger.log("SCRAPER", f"Found {len(data)} streams out of {stream_count} for {item.log_string}")
            return data
        elif stream_count > 0:
            logger.log("NOT_FOUND", f"Could not find good streams for {item.log_string} out of {stream_count}")
        else:
            logger.log("NOT_FOUND", f"No streams found for {item.log_string}")
        return []

    def api_scrape(self, item: MediaItem) -> tuple[Dict[str, Torrent], int]:
        """Wrapper for `Torbox` scrape method using Torbox API"""
        # Example URLs:
        # https://search-api.torbox.app/torrents/imdb:tt0080684?metadata=false
        # https://search-api.torbox.app/torrents/imdb:tt0080684?metadata=false&season=1
        # https://search-api.torbox.app/torrents/imdb:tt0080684?metadata=false&season=1&episode=1
        if isinstance(item, (Movie, Show)):
            url = f"{self.base_url}/torrents/imdb:{item.imdb_id}?metadata=false"
        elif isinstance(item, Season):
            url = f"{self.base_url}/torrents/imdb:{item.parent.imdb_id}?metadata=false&season={item.number}"
        elif isinstance(item, Episode):
            url = f"{self.base_url}/torrents/imdb:{item.parent.parent.imdb_id}?metadata=false&season={item.parent.number}&episode={item.number}"
        else:
            return {}, 0


        with self.minute_limiter:
            with self.second_limiter:
                response = get(url, timeout=60, retry_if_failed=False)
            if not response.is_ok or not response.data.data.torrents:
                return {}, 0

            correct_title = item.get_top_title()
            torrents = set()
            
            for torrent_data in response.data.data.torrents:
                raw_title = torrent_data.raw_title
                info_hash = torrent_data.hash
                if not info_hash or not raw_title:
                    continue
                if self.hash_cache.is_blacklisted(info_hash):
                    continue
                try:
                    torrent = self.rtn.rank(
                        raw_title=raw_title,
                        infohash=info_hash,
                        correct_title=correct_title,
                        remove_trash=True
                    )
                except GarbageTorrent:
                    continue
                if torrent and torrent.fetch:
                    torrents.add(torrent)
            if not torrents:
                return {}, 0
            scraped_torrents = sort_torrents(torrents)
            return scraped_torrents, len(response.data.data.torrents)
