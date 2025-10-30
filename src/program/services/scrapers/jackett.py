"""Jackett scraper module"""

from types import SimpleNamespace
from typing import Dict, List, Optional

from loguru import logger
from pydantic import BaseModel
from requests import ReadTimeout

from program.media.item import MediaItem
from program.services.scrapers.base import ScraperService
from program.settings.manager import settings_manager
from program.utils.request import SmartSession, get_hostname_from_url
from program.utils.torrent import extract_infohash, normalize_infohash


class JackettIndexer(BaseModel):
    """Indexer model for Jackett"""

    title: Optional[str] = None
    id: Optional[str] = None
    link: Optional[str] = None
    type: Optional[str] = None
    language: Optional[str] = None
    tv_search_capabilities: Optional[List[str]] = None
    movie_search_capabilities: Optional[List[str]] = None


class Jackett(ScraperService):
    """Scraper for `Jackett`"""

    def __init__(self):
        super().__init__("jackett")
        self.api_key = None
        self.indexers = None
        self.settings = settings_manager.settings.scraping.jackett
        self.request_handler = None
        self._initialize()

    def validate(self) -> bool:
        """Validate Jackett settings."""
        if not self.settings.enabled:
            return False
        if self.settings.url and self.settings.api_key:
            self.api_key = self.settings.api_key
            try:
                if (
                    not isinstance(self.settings.timeout, int)
                    or self.settings.timeout <= 0
                ):
                    logger.error("Jackett timeout is not set or invalid.")
                    return False
                if not isinstance(self.settings.ratelimit, bool):
                    logger.error("Jackett ratelimit must be a valid boolean.")
                    return False

                if self.settings.ratelimit:
                    rate_limits = {
                        get_hostname_from_url(self.settings.url): {
                            "rate": 300 / 60,
                            "capacity": 300,
                        }
                    }
                else:
                    rate_limits = {}

                self.session = SmartSession(
                    base_url=f"{self.settings.url.rstrip('/')}/api/v2.0",
                    rate_limits=rate_limits,
                    retries=3,
                    backoff_factor=0.3,
                )

                return True
            except ReadTimeout:
                logger.error(
                    "Jackett request timed out. Check your indexers, they may be too slow to respond."
                )
                return False
            except Exception as e:
                logger.error(f"Jackett failed to initialize with API Key: {e}")
                return False
        logger.warning("Jackett is not configured and will not be used.")
        return False

    def run(self, item: MediaItem) -> Dict[str, str]:
        """Scrape the Jackett site for the given media items
        and update the object with scraped streams"""
        try:
            return self.scrape(item)
        except Exception as e:
            if "rate limit" in str(e).lower() or "429" in str(e):
                logger.debug(f"Jackett ratelimit exceeded for item: {item.log_string}")
            else:
                logger.error(f"Jackett failed to scrape item with error: {e}")
        return {}

    def scrape(self, item: MediaItem) -> Dict[str, str]:
        """Scrape the given media item"""

        torrents: Dict[str, str] = {}
        query = item.log_string
        if item.type == "movie":
            query = f"{query} ({item.aired_at.year})"

        logger.debug(f"Searching for '{query}' in Jackett")
        response = f"/indexers/test:passed/results?apikey={self.api_key}&Query={query}"
        response = self.session.get(response, timeout=self.settings.timeout)
        if not response.ok or not hasattr(response, "data"):
            return torrents

        if hasattr(response.data, "Results"):
            for result in response.data.Results:
                infohash = self._get_infohash_from_result(result)
                if infohash:
                    torrents[infohash] = result.Title

        if torrents:
            logger.log(
                "SCRAPER", f"Found {len(torrents)} streams for {item.log_string}"
            )
        else:
            logger.log("NOT_FOUND", f"No streams found for {item.log_string}")
        return torrents

    def _get_infohash_from_result(self, result: SimpleNamespace) -> Optional[str]:
        """Try to get the infohash from the result"""
        infohash = None

        # Priority 1: Use InfoHash field directly if available (normalize to handle base32)
        if hasattr(result, "InfoHash") and result.InfoHash:
            return normalize_infohash(result.InfoHash)

        # Priority 2: Check if MagnetUri is available and extract from it
        if hasattr(result, "MagnetUri") and result.MagnetUri:
            infohash = extract_infohash(result.MagnetUri)
            if infohash:
                return infohash

        # Priority 3: Try to extract from Guid field
        if hasattr(result, "Guid") and result.Guid:
            infohash = extract_infohash(result.Guid)
            if infohash:
                return infohash

        # Priority 4: Try to extract from Details field
        if hasattr(result, "Details") and result.Details:
            infohash = extract_infohash(result.Details)
            if infohash:
                return infohash

        # Priority 5: Try Link field as last resort
        if hasattr(result, "Link") and result.Link:
            try:
                infohash = self.get_infohash_from_url(result.Link)
                if infohash:
                    return infohash
            except Exception as e:
                logger.debug(f"Failed to get infohash from Link: {e}")

        return None
