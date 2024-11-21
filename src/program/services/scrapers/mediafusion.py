""" Mediafusion scraper module """
import json
import re
from typing import Dict

from loguru import logger
from requests import ConnectTimeout, ReadTimeout
from requests.exceptions import RequestException

from program.media.item import MediaItem
from program.services.scrapers.shared import (
    ScraperRequestHandler,
    _get_stremio_identifier,
)
from program.settings.manager import settings_manager
from program.settings.models import AppModel
from program.utils.request import (
    HttpMethod,
    RateLimitExceeded,
    ResponseType,
    create_service_session,
    get_rate_limit_params,
)


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
        # https://github.com/elfhosted/infra/blob/ci/mediafusion/middleware-ratelimit-stream.yaml
        rate_limit_params = get_rate_limit_params(max_calls=1, period=10) if self.settings.ratelimit else None
        session = create_service_session(rate_limit_params=rate_limit_params)
        self.request_handler = ScraperRequestHandler(session)
        self.initialized = self.validate()
        if not self.initialized:
            return
        logger.success("Mediafusion initialized!")

    def validate(self) -> bool:
        """Validate the Mediafusion settings."""
        if not self.settings.enabled:
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
            "sp": {
                "sv": self.downloader,
                "tk": self.api_key,
                "ewc": False
            },
            "sc": self.settings.catalogs,
            "sr": ["4k", "2160p", "1440p", "1080p", "720p", "480p", None],
            "ec": False,
            "eim": False,
            "sftn": True,
            "tsp": ["cached"],  # sort order, but this doesnt matter as we sort later
            "nf": ["Disable"],  # nudity filter
            "cf": ["Disable"]   # certification filter
        }

        url = f"{self.settings.url}/encrypt-user-data"
        headers = {"Content-Type": "application/json"}

        try:
            response = self.request_handler.execute(HttpMethod.POST, url, overriden_response_type=ResponseType.DICT, json=payload, headers=headers)
            if not response.data or response.data["status"] != "success":
                logger.error(f"Failed to encrypt user data: {response.data['message']}")
                return False
            self.encrypted_string = response.data["encrypted_str"]
        except Exception as e:
            logger.error(f"Failed to encrypt user data: {e}")
            return False

        try:
            url = f"{self.settings.url}/manifest.json"
            response = self.request_handler.execute(HttpMethod.GET, url, timeout=self.timeout)
            return response.is_ok
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
            logger.debug(f"Mediafusion ratelimit exceeded for item: {item.log_string}")
        except ConnectTimeout:
            logger.warning(f"Mediafusion connection timeout for item: {item.log_string}")
        except ReadTimeout:
            logger.warning(f"Mediafusion read timeout for item: {item.log_string}")
        except RequestException as e:
            logger.error(f"Mediafusion request exception: {e}")
        except Exception as e:
            logger.exception(f"Mediafusion exception thrown: {e}")
        return {}

    def scrape(self, item: MediaItem) -> tuple[Dict[str, str], int]:
        """Wrapper for `Mediafusion` scrape method"""
        identifier, scrape_type, imdb_id = _get_stremio_identifier(item)

        url = f"{self.settings.url}/{self.encrypted_string}/stream/{scrape_type}/{imdb_id}"
        if identifier:
            url += identifier

        response = self.request_handler.execute(HttpMethod.GET, f"{url}.json", timeout=self.timeout)
        if not response.is_ok or len(response.data.streams) <= 0:
            logger.log("NOT_FOUND", f"No streams found for {item.log_string}")
            return {}

        torrents: Dict[str, str] = {}

        for stream in response.data.streams:
            if not hasattr(stream, "description") and hasattr(stream, "title") and "rate-limit exceeded" in stream.title:
                raise RateLimitExceeded(f"Mediafusion rate-limit exceeded for item: {item.log_string}")
            description_split = stream.description.replace("📂 ", "")
            raw_title = description_split.split("/")[0] or description_split.split("\n")[0]  # we want the torrent name if possible
            info_hash = re.search(r"info_hash=([A-Za-z0-9]+)", stream.url).group(1)
            if info_hash and info_hash not in torrents:
                torrents[info_hash] = raw_title

        if torrents:
            logger.log("SCRAPER", f"Found {len(torrents)} streams for {item.log_string}")
        else:
            logger.log("NOT_FOUND", f"No streams found for {item.log_string}")

        return torrents