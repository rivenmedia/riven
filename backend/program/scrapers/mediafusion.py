""" Mediafusion scraper module """
import json
from typing import Dict

import requests
from program.media.item import Episode, MediaItem, Movie, Season, Show
from program.scrapers.shared import _get_stremio_identifier
from program.settings.manager import settings_manager
from program.settings.models import AppModel
from requests import ConnectTimeout, ReadTimeout
from requests.exceptions import RequestException
from utils.logger import logger
from utils.request import RateLimiter, RateLimitExceeded, get, ping


class Mediafusion:
    """Scraper for `Mediafusion`"""

    def __init__(self):
        self.key = "mediafusion"
        self.api_key = None
        self.downloader = None
        self.app_settings: AppModel = settings_manager.settings
        self.settings = self.app_settings.scraping.mediafusion
        self.timeout = self.settings.timeout
        self.encrypted_string = None
        self.initialized = self.validate()
        if not self.initialized:
            return
        self.second_limiter = RateLimiter(max_calls=1, period=2) if self.settings.ratelimit else None
        logger.success("Mediafusion initialized!")

    def validate(self) -> bool:
        """Validate the Mediafusion settings."""
        if not self.settings.enabled:
            logger.warning("Mediafusion is set to disabled.")
            return False
        if not self.settings.url:
            logger.error("Mediafusion URL is not configured and will not be used.")
            return False
        if not isinstance(self.timeout, int) or self.timeout <= 0:
            logger.error("Mediafusion timeout is not set or invalid.")
            return False
        if not isinstance(self.settings.ratelimit, bool):
            logger.error("Mediafusion ratelimit must be a valid boolean.")
            return False
        if not self.settings.catalogs:
            logger.error("Configure at least one Mediafusion catalog.")
            return False

        if self.app_settings.downloaders.real_debrid.enabled:
            self.api_key = self.app_settings.downloaders.real_debrid.api_key
            self.downloader = "realdebrid"
        elif self.app_settings.downloaders.torbox.enabled:
            self.api_key = self.app_settings.downloaders.torbox.api_key
            self.downloader = "torbox"
        else:
            logger.error("No downloader enabled, please enable at least one.")
            return False

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

        url = f"{self.settings.url}/encrypt-user-data"
        headers = {"Content-Type": "application/json"}

        try:
            response = requests.request("POST", url, json=payload, headers=headers)
            self.encrypted_string = json.loads(response.content)['encrypted_str']
        except Exception as e:
            logger.error(f"Failed to encrypt user data: {e}")
            return False

        try:
            url = f"{self.settings.url}/manifest.json"
            response = ping(url=url, timeout=self.timeout)
            return response.ok
        except Exception as e:
            logger.error(f"Mediafusion failed to initialize: {e}")
            return False

    def run(self, item: MediaItem) -> Dict[str, str]:
        """Scrape the mediafusion site for the given media items
        and update the object with scraped streams"""
        if not item:
            return {}

        try:
            return self.scrape(item)
        except RateLimitExceeded:
            if self.second_limiter:
                self.second_limiter.limit_hit()
            else:
                logger.warning(f"Mediafusion ratelimit exceeded for item: {item.log_string}")
        except ConnectTimeout:
            logger.warning(f"Mediafusion connection timeout for item: {item.log_string}")
        except ReadTimeout:
            logger.warning(f"Mediafusion read timeout for item: {item.log_string}")
        except RequestException as e:
            logger.error(f"Mediafusion request exception: {e}")
        except Exception as e:
            logger.error(f"Mediafusion exception thrown: {e}")
        return {}

    def scrape(self, item: MediaItem) -> Dict[str, str]:
        """Scrape the given media item"""
        data, stream_count = self.api_scrape(item)
        if data:
            logger.log("SCRAPER", f"Found {len(data)} streams out of {stream_count} for {item.log_string}")
        else:
            logger.log("NOT_FOUND", f"No streams found for {item.log_string}")
        return data

    def api_scrape(self, item: MediaItem) -> tuple[Dict[str, str], int]:
        """Wrapper for `Mediafusion` scrape method"""
        identifier, scrape_type, imdb_id = _get_stremio_identifier(item)

        url = f"{self.settings.url}/{self.encrypted_string}/stream/{scrape_type}/{imdb_id}"
        if identifier:
            url += identifier

        if self.second_limiter:
            with self.second_limiter:
                response = get(f"{url}.json", timeout=self.timeout)
        else:
            response = get(f"{url}.json", timeout=self.timeout)

        if not response.is_ok or len(response.data.streams) <= 0:
            return {}, 0

        torrents: Dict[str, str] = {}

        for stream in response.data.streams:
            raw_title = stream.description.split("\n💾")[0].replace("📂 ", "")
            info_hash = stream.url.split("?info_hash=")[1]
            if not info_hash or not raw_title:
                continue

            torrents[info_hash] = raw_title

        return torrents, len(response.data.streams)
