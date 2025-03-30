""" Comet scraper module """
import base64
import json
from typing import Dict

import regex
from loguru import logger
from requests import ConnectTimeout, ReadTimeout
from requests.exceptions import RequestException

from program.media.item import MediaItem, Show
from program.services.scrapers.shared import (
    ScraperRequestHandler,
    _get_stremio_identifier,
)
from program.settings.manager import settings_manager
from program.utils.request import (
    HttpMethod,
    RateLimitExceeded,
    create_service_session,
    get_rate_limit_params,
)


class Comet:
    """Scraper for `Comet`"""

    def __init__(self):
        self.key = "comet"
        self.settings = settings_manager.settings.scraping.comet
        self.timeout = self.settings.timeout or 15
        self.encoded_string = base64.b64encode(json.dumps({
            "maxResultsPerResolution": 0,
            "maxSize": 0,
            "cachedOnly": False,
            "removeTrash": True,
            "resultFormat": [
                "title",
                "metadata",
                "size",
                "languages"
            ],
            "debridService": "torrent",
            "debridApiKey": "",
            "debridStreamProxyPassword": "",
            "languages": {
                "required": [],
                "exclude": [],
                "preferred": []
            },
            "resolutions": {},
            "options": {}
        }).encode("utf-8")).decode("utf-8")
        rate_limit_params = get_rate_limit_params(per_hour=300) if self.settings.ratelimit else None
        session = create_service_session(rate_limit_params=rate_limit_params)
        self.request_handler = ScraperRequestHandler(session)
        self.initialized = self.validate()
        if not self.initialized:
            return
        logger.success("Comet initialized!")

    def validate(self) -> bool:
        """Validate the Comet settings."""
        if not self.settings.enabled:
            return False
        if not self.settings.url:
            logger.error("Comet URL is not configured and will not be used.")
            return False
        if not isinstance(self.settings.ratelimit, bool):
            logger.error("Comet ratelimit must be a valid boolean.")
            return False
        try:
            url = f"{self.settings.url}/manifest.json"
            response = self.request_handler.execute(HttpMethod.GET, url, timeout=self.timeout)
            if response.is_ok:
                return True
        except Exception as e:
            logger.error(f"Comet failed to initialize: {e}", )
        return False

    def run(self, item: MediaItem) -> Dict[str, str]:
        """Scrape the comet site for the given media items
        and update the object with scraped streams"""
        try:
            return self.scrape(item)
        except RateLimitExceeded:
            logger.debug(f"Comet ratelimit exceeded for item: {item.log_string}")
        except ConnectTimeout:
            logger.warning(f"Comet connection timeout for item: {item.log_string}")
        except ReadTimeout:
            logger.warning(f"Comet read timeout for item: {item.log_string}")
        except RequestException as e:
            logger.error(f"Comet request exception: {str(e)}")
        except Exception as e:
            logger.error(f"Comet exception thrown: {str(e)}")
        return {}

    def scrape(self, item: MediaItem) -> tuple[Dict[str, str], int]:
        """Wrapper for `Comet` scrape method"""
        identifier, scrape_type, imdb_id = _get_stremio_identifier(item)
        url = f"{self.settings.url}/{self.encoded_string}/stream/{scrape_type}/{imdb_id}{identifier or ''}.json"

        response = self.request_handler.execute(HttpMethod.GET, url, timeout=self.timeout)
        if not response.is_ok or not getattr(response.data, "streams", None):
            logger.log("NOT_FOUND", f"No streams found for {item.log_string}")
            return {}

        torrents = {
            stream.infoHash: stream.description.split("\n")[0] 
            for stream in response.data.streams if stream.infoHash
        }

        if torrents:
            logger.log("SCRAPER", f"Found {len(torrents)} streams for {item.log_string}")
        else:
            logger.log("NOT_FOUND", f"No streams found for {item.log_string}")

        return torrents
