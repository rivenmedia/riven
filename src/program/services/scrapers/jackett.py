"""Jackett scraper module"""

import concurrent.futures
from typing import Optional

from loguru import logger
from pydantic import BaseModel
from requests import ReadTimeout

from program.media.item import MediaItem
from program.services.scrapers.base import ScraperService
from program.settings.manager import settings_manager
from program.utils.request import SmartSession, get_hostname_from_url
from program.utils.torrent import extract_infohash, normalize_infohash
from program.settings.models import JackettConfig


class JackettIndexer(BaseModel):
    """Indexer model for Jackett"""

    title: Optional[str] = None
    id: Optional[str] = None
    link: Optional[str] = None
    type: Optional[str] = None
    language: Optional[str] = None
    tv_search_capabilities: Optional[list[str]] = None
    movie_search_capabilities: Optional[list[str]] = None


class Jackett(ScraperService[JackettConfig]):
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
                    retries=self.settings.retries,
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

    def run(self, item: MediaItem) -> dict[str, str]:
        """
        Scrape the Jackett site for the given media items
        and update the object with scraped streams
        """

        try:
            return self.scrape(item)
        except Exception as e:
            if "rate limit" in str(e).lower() or "429" in str(e):
                logger.debug(f"Jackett ratelimit exceeded for item: {item.log_string}")
            else:
                logger.error(f"Jackett failed to scrape item with error: {e}")

        return {}

    def scrape(self, item: MediaItem) -> dict[str, str]:
        """Scrape the given media item"""

        torrents: dict[str, str] = {}
        query = item.log_string
        if item.type == "movie":
            query = f"{query} ({item.aired_at.year})"

        logger.debug(f"Searching for '{query}' in Jackett")
        response = f"/indexers/test:passed/results?apikey={self.api_key}&Query={query}"
        response = self.session.get(response, timeout=self.settings.timeout)
        if not response.ok or not hasattr(response, "data"):
            return torrents

        if hasattr(response.data, "Results"):
            urls_to_fetch = []  # list of (result, title) tuples that need URL fetching

            # First pass: extract infohashes from available fields and collect URLs that need fetching
            for result in response.data.Results:
                infohash = None

                # Priority 1: Use InfoHash field directly if available (normalize to handle base32)
                if hasattr(result, "InfoHash") and result.InfoHash:
                    infohash = normalize_infohash(result.InfoHash)

                # Priority 2: Check if MagnetUri is available and extract from it
                if not infohash and hasattr(result, "MagnetUri") and result.MagnetUri:
                    infohash = extract_infohash(result.MagnetUri)

                # Priority 3: Collect URLs that need fetching
                if not infohash and hasattr(result, "Link") and result.Link:
                    urls_to_fetch.append((result, result.Title))
                elif infohash:
                    # We already have an infohash, add it directly
                    torrents[infohash] = result.Title

            # Fetch URLs in parallel
            if urls_to_fetch:
                with concurrent.futures.ThreadPoolExecutor(
                    thread_name_prefix="JackettHashExtract", max_workers=10
                ) as executor:
                    future_to_result = {
                        executor.submit(self.get_infohash_from_url, result.Link): (
                            result,
                            title,
                        )
                        for result, title in urls_to_fetch
                    }

                    done, pending = concurrent.futures.wait(
                        future_to_result.keys(),
                        timeout=self.settings.infohash_fetch_timeout,
                    )
                    # Process completed futures
                    for future in done:
                        result, title = future_to_result[future]
                        try:
                            infohash = future.result()
                            if infohash:
                                torrents[infohash] = title
                        except Exception as e:
                            logger.debug(
                                f"Failed to get infohash from Link for {title}: {e}"
                            )
                    # Cancel and log timeouts for pending futures
                    for future in pending:
                        result, title = future_to_result[future]
                        future.cancel()
                        logger.debug(f"Timeout getting infohash from Link for {title}")

        if torrents:
            logger.log(
                "SCRAPER", f"Found {len(torrents)} streams for {item.log_string}"
            )
        else:
            logger.log("NOT_FOUND", f"No streams found for {item.log_string}")
        return torrents
