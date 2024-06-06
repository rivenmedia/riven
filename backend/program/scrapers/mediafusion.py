""" Mediafusion scraper module """
from typing import Dict, Generator
import json
import requests

from program.media.item import Episode, MediaItem, Season, Show
from program.settings.manager import settings_manager
from program.settings.versions import models
from requests import ConnectTimeout, ReadTimeout
from requests.exceptions import RequestException
from RTN import RTN, Torrent, sort_torrents
from RTN.exceptions import GarbageTorrent
from utils.logger import logger
from utils.request import RateLimiter, RateLimitExceeded, get, post, ping


class Mediafusion:
    """Scraper for `Mediafusion`"""

    def __init__(self, hash_cache):
        self.key = "mediafusion"
        self.settings = settings_manager.settings.scraping.mediafusion
        self.settings_model = settings_manager.settings.ranking
        self.ranking_model = models.get(self.settings_model.profile)
        self.initialized = self.validate()
        if not self.initialized:
            return
        self.minute_limiter = RateLimiter(
            max_calls=300, period=3600, raise_on_limit=True
        )
        self.second_limiter = RateLimiter(max_calls=1, period=5)
        self.rtn = RTN(self.settings_model, self.ranking_model)
        self.hash_cache = hash_cache
        self.running = True

        if settings_manager.settings.downloaders.real_debrid.enabled:
            self.api_key = settings_manager.settings.downloaders.real_debrid.api_key
            self.downloader = "realdebrid"
        elif settings_manager.settings.downloaders.torbox.enabled:
            self.api_key = settings_manager.settings.downloaders.torbox.api_key
            self.downloader = "torbox"

        url = f"{self.settings.url}/encrypt-user-data"

        payload = {
            "streaming_provider": {
                "token": self.api_key,
                "service": self.downloader,
                "enable_watchlist_catalogs": False
            },
            "selected_catalogs": self.settings.catalogs,
            "selected_resolutions": ["4K", "2160p", "1440p", "1080p", "720p"],
            "enable_catalogs": False,
            "max_size": "inf",
            "max_streams_per_resolution": "10",
            "torrent_sorting_priority": ["cached", "resolution", "size", "seeders", "created_at"],
            "show_full_torrent_name": True,
            "api_password": None
        }
        headers = {"Content-Type": "application/json"}

        response = requests.request("POST", url, json=payload, headers=headers)

        self.encrypted_string = json.loads(response.content)['encrypted_str']

        logger.success("Mediafusion initialized!")

    def validate(self) -> bool:
        """Validate the Mediafusion settings."""
        if not self.settings.enabled:
            logger.warning("Mediafusion is set to disabled.")
            return False
        if not self.settings.url:
            logger.error("Mediafusion URL is not configured and will not be used.")
            return False
        if len(self.settings.catalogs) == 0:
            logger.error("Configure at least one Mediafusion catalog.")
            return False
        try:
            url = f"{self.settings.url}/manifest.json"
            response = ping(url=url, timeout=10)
            if response.ok:
                return True
        except Exception as e:
            logger.error(f"Mediafusion failed to initialize: {e}", )
            return False
        return True

    def run(self, item: MediaItem) -> Generator[MediaItem, None, None]:
        """Scrape the mediafusion site for the given media items
        and update the object with scraped streams"""
        if not item or isinstance(item, Show):
            yield item
            return

        try:
            yield self.scrape(item)
        except RateLimitExceeded:
            logger.warning(f"Rate limit exceeded for item: {item.log_string}")
        except ConnectTimeout:
            logger.warning(f"Mediafusion connection timeout for item: {item.log_string}")
        except ReadTimeout:
            logger.warning(f"Mediafusion read timeout for item: {item.log_string}")
        except RequestException as e:
            logger.error(f"Mediafusion request exception: {e}")
        except Exception as e:
            logger.exception(f"Mediafusion exception thrown: {e}")
        self.minute_limiter.limit_hit()
        self.second_limiter.limit_hit()
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
        """Wrapper for `Mediafusion` scrape method"""
        with self.minute_limiter:
            identifier, scrape_type, imdb_id = None, "movie", item.imdb_id
            if isinstance(item, Season):
                identifier, scrape_type, imdb_id = f":{item.number}:1", "series", item.parent.imdb_id
            elif isinstance(item, Episode):
                identifier, scrape_type, imdb_id = f":{item.parent.number}:{item.number}", "series", item.parent.parent.imdb_id

            url = f"{self.settings.url}/{self.encrypted_string}/stream/{scrape_type}/{imdb_id}"
            if identifier:
                url += identifier
            with self.second_limiter:
                response = get(f"{url}.json", retry_if_failed=True, timeout=30)
            if not response.is_ok or len(response.data.streams) <= 0:
                return {}, 0

            torrents = set()
            correct_title = item.get_top_title()
            if not correct_title:
                logger.scraper(f"Correct title not found for {item.log_string}")
                return {}, 0

            for stream in response.data.streams:
                raw_title = stream.description.split("\n💾")[0].replace("📂 ", "")
                info_hash = stream.url.split("?info_hash=")[1]
                if not info_hash or not raw_title:
                    continue
                if self.hash_cache and self.hash_cache.is_blacklisted(info_hash):
                    continue
                try:
                    torrent = self.rtn.rank(raw_title=raw_title, infohash=info_hash, correct_title=correct_title, remove_trash=True)
                except GarbageTorrent:
                    continue
                if torrent and torrent.fetch:
                    torrents.add(torrent)
            scraped_torrents = sort_torrents(torrents)
            return scraped_torrents, len(response.data.streams)
