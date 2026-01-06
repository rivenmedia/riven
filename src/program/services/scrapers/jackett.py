"""Jackett scraper module"""

import concurrent.futures

from loguru import logger
from pydantic import BaseModel, Field
from requests import ReadTimeout

from program.media.item import MediaItem, Movie
from program.services.scrapers.base import ScraperService
from program.settings import settings_manager
from program.utils.request import SmartSession, get_hostname_from_url
from program.utils.torrent import extract_infohash, normalize_infohash
from program.settings.models import JackettConfig


class JackettScrapeResponse(BaseModel):
    """Model for Jackett scrape response"""

    class JackettTorrentResult(BaseModel):
        """Model for a single Jackett torrent result"""

        title: str = Field(alias="Title")
        link: str | None = Field(alias="Link")
        info_hash: str | None = Field(alias="InfoHash")
        magnet_uri: str | None = Field(alias="MagnetUri")

    results: list[JackettTorrentResult] = Field(alias="Results")


class Jackett(ScraperService[JackettConfig]):
    """Scraper for `Jackett`"""

    def __init__(self):
        super().__init__()

        self.api_key = None
        self.indexers = None
        self.settings = settings_manager.settings.scraping.jackett
        self.request_handler = None
        self._initialize()

    def validate(self) -> bool:
        """Validate Jackett settings."""

        if not self.settings.enabled:
            return False

        if not self.settings.instances or not any(
            inst.url and inst.api_key for inst in self.settings.instances
        ):
            logger.warning(
                "No valid Jackett instances configured (need URL + API key). Will not be used."
            )
            return False

        if self.settings.timeout <= 0:
            logger.error("Jackett timeout must be a positive integer")
            return False

        # Build rate limits for all configured URLs
        rate_limits = None
        if self.settings.ratelimit:
            rate_limits = {
                get_hostname_from_url(inst.url): {
                    "rate": 300 / 60,
                    "capacity": 300,
                }
                for inst in self.settings.instances
                if inst.url
            }

        # Try to find a working instance
        for instance in self.settings.instances:
            if not instance.url or not instance.api_key:
                continue
            try:
                self.api_key = instance.api_key
                self.session = SmartSession(
                    base_url=f"{instance.url.rstrip('/')}/api/v2.0",
                    rate_limits=rate_limits,
                    retries=self.settings.retries,
                    backoff_factor=0.3,
                )
                return True
            except ReadTimeout:
                logger.debug(
                    f"Jackett request timed out for {instance.url}. Trying next instance..."
                )
                continue
            except Exception as e:
                logger.debug(f"Jackett failed to initialize with {instance.url}: {e}")
                continue

        logger.error("Jackett failed to initialize: all instances failed")
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

        torrents = dict[str, str]()
        query = item.log_string

        if isinstance(item, Movie) and item.aired_at:
            query = f"{query} ({item.aired_at.year})"

        logger.debug(f"Searching for '{query}' in Jackett")

        response = f"/indexers/test:passed/results?apikey={self.api_key}&Query={query}"
        response = self.session.get(response, timeout=self.settings.timeout)

        if not response.ok:
            return torrents

        data = JackettScrapeResponse.model_validate(response.json())

        if data.results:
            # list of (result, title) tuples that need URL fetching
            urls_to_fetch = list[
                tuple[JackettScrapeResponse.JackettTorrentResult, str]
            ]()

            # First pass: extract infohashes from available fields and collect URLs that need fetching
            for result in data.results:
                infohash = None

                # Priority 1: Use InfoHash field directly if available (normalize to handle base32)
                if result.info_hash:
                    infohash = normalize_infohash(result.info_hash)

                # Priority 2: Check if MagnetUri is available and extract from it
                if not infohash and result.magnet_uri:
                    infohash = extract_infohash(result.magnet_uri)

                # Priority 3: Collect URLs that need fetching
                if not infohash and result.link:
                    urls_to_fetch.append((result, result.title))

                elif infohash:
                    # We already have an infohash, add it directly
                    torrents[infohash] = result.title

            # Fetch URLs in parallel
            if urls_to_fetch:
                with concurrent.futures.ThreadPoolExecutor(
                    thread_name_prefix="JackettHashExtract", max_workers=10
                ) as executor:
                    future_to_result = {
                        executor.submit(self.get_infohash_from_url, result.link): (
                            result,
                            title,
                        )
                        for result, title in urls_to_fetch
                        if result.link
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
