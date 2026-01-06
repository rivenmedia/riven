"""Comet scraper module"""

import base64
import json

from loguru import logger
from pydantic import BaseModel, Field

from program.media.item import MediaItem
from program.services.scrapers.base import ScraperService
from program.settings import settings_manager
from program.utils.request import SmartSession, get_hostname_from_url
from program.settings.models import CometConfig


class CometScrapeResponse(BaseModel):
    """Represents a response from the Comet scraper."""

    class CometStream(BaseModel):
        """Represents a single stream in the Comet response."""

        info_hash: str | None = Field(alias="infoHash", default=None)
        description: str

    streams: list[CometStream]


class Comet(ScraperService[CometConfig]):
    """Scraper for `Comet`"""

    # This service requires an IMDb id
    requires_imdb_id = True

    def __init__(self):
        super().__init__()

        self.settings = settings_manager.settings.scraping.comet
        self.timeout = self.settings.timeout or 15
        self.encoded_string = base64.b64encode(
            json.dumps(
                {
                    "maxResultsPerResolution": 0,
                    "maxSize": 0,
                    "cachedOnly": False,
                    "removeTrash": True,
                    "resultFormat": ["title", "metadata", "size", "languages"],
                    "debridService": "torrent",
                    "debridApiKey": "",
                    "debridStreamProxyPassword": "",
                    "languages": {"required": [], "exclude": [], "preferred": []},
                    "resolutions": {},
                    "options": {},
                }
            ).encode("utf-8")
        ).decode("utf-8")

        # Build rate limits for all configured URLs
        rate_limits = None
        if self.settings.ratelimit and self.settings.urls:
            rate_limits = {
                get_hostname_from_url(url): {
                    "rate": 300 / 60,
                    "capacity": 300,
                }  # 300 calls per minute
                for url in self.settings.urls
                if url
            }

        self.session = SmartSession(
            rate_limits=rate_limits,
            retries=self.settings.retries,
            backoff_factor=0.3,
        )
        self._initialize()

    def validate(self) -> bool:
        """Validate the Comet settings."""

        if not self.settings.enabled:
            return False

        if not self.settings.urls or not any(self.settings.urls):
            logger.error("Comet URLs are not configured and will not be used.")
            return False

        # Check for elfhosted in any URL
        for url in self.settings.urls:
            if url and "elfhosted" in url.lower():
                logger.warning(
                    "Elfhosted Comet instance is no longer supported. Please use a different instance."
                )
                return False

        # Try to validate at least one URL works
        for url in self.settings.urls:
            if not url:
                continue
            try:
                response = self.session.get(
                    f"{url.rstrip('/')}/manifest.json", timeout=self.timeout
                )
                if response.ok:
                    return True
            except Exception as e:
                logger.debug(f"Comet validation failed for {url}: {e}")
                continue

        logger.error("Comet failed to initialize: all URLs failed validation")
        return False

    def run(self, item: MediaItem) -> dict[str, str]:
        """
        Scrape the comet site for the given media items
        and update the object with scraped streams
        """

        try:
            return self.scrape(item)
        except Exception as e:
            if "rate limit" in str(e).lower() or "429" in str(e):
                logger.debug(f"Comet ratelimit exceeded for item: {item.log_string}")
            elif "timeout" in str(e).lower():
                logger.warning(f"Comet timeout for item: {item.log_string}")
            else:
                logger.error(f"Comet exception thrown: {str(e)}")

        return {}

    def scrape(self, item: MediaItem) -> dict[str, str]:
        """Wrapper for `Comet` scrape method"""

        identifier, scrape_type, imdb_id = self.get_stremio_identifier(item)

        if not imdb_id:
            return {}

        # Build path with encoded string and identifier
        path = f"{self.encoded_string}/stream/{scrape_type}/{imdb_id}{identifier or ''}.json"

        # Use failover across all configured URLs
        response = self.request_with_failover(
            self.session,
            self.settings.urls,
            path,
            timeout=self.timeout,
        )

        if not response or not response.ok:
            if response:
                logger.error(f"Comet scrape failed for {item.log_string}")
            return {}

        data = CometScrapeResponse.model_validate(response.json())

        if not data.streams:
            logger.log("NOT_FOUND", f"No streams found for {item.log_string}")
            return {}

        torrents = {
            stream.info_hash: stream.description.split("\n")[0].replace("📄 ", "")
            for stream in data.streams
            if stream.info_hash
        }

        if torrents:
            logger.log(
                "SCRAPER", f"Found {len(torrents)} streams for {item.log_string}"
            )
        else:
            logger.log("NOT_FOUND", f"No streams found for {item.log_string}")

        return torrents

