"""Zilean scraper module"""

from loguru import logger
from pydantic import BaseModel, ConfigDict, Field

from program.media.item import Episode, MediaItem, Season, Show
from program.services.scrapers.base import ScraperService
from program.settings import settings_manager
from program.utils.request import SmartSession, get_hostname_from_url
from program.settings.models import ZileanConfig


class Params(BaseModel):
    model_config = ConfigDict(serialize_by_alias=True)

    query: str = Field(serialization_alias="Query")
    season: int | None = Field(default=None, serialization_alias="Season")
    episode: int | None = Field(default=None, serialization_alias="Episode")


class ZileanScrapeResponse(BaseModel):
    class ResultItem(BaseModel):
        raw_title: str | None
        info_hash: str | None

    data: list[ResultItem]


class Zilean(ScraperService[ZileanConfig]):
    """Scraper for `Zilean`"""

    def __init__(self):
        super().__init__()

        self.settings = settings_manager.settings.scraping.zilean
        self.timeout = self.settings.timeout

        # Build rate limits for all configured URLs
        rate_limits = None
        if self.settings.ratelimit and self.settings.urls:
            rate_limits = {
                get_hostname_from_url(url): {
                    "rate": 500 / 60,
                    "capacity": 500,
                }
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
        """Validate the Zilean settings."""

        if not self.settings.enabled:
            return False

        if not self.settings.urls or not any(self.settings.urls):
            logger.error("Zilean URLs are not configured and will not be used.")
            return False

        if self.timeout <= 0:
            logger.error("Zilean timeout must be a positive integer.")
            return False

        # Try to validate at least one URL works
        for url in self.settings.urls:
            if not url:
                continue
            try:
                response = self.session.get(
                    f"{url}/healthchecks/ping", timeout=self.timeout
                )
                if response.ok:
                    return True
            except Exception as e:
                logger.debug(f"Zilean validation failed for {url}: {e}")
                continue

        logger.error("Zilean failed to initialize: all URLs failed validation")
        return False

    def run(self, item: MediaItem) -> dict[str, str]:
        """Scrape the Zilean site for the given media items and update the object with scraped items"""

        try:
            return self.scrape(item)
        except Exception as e:
            if "rate limit" in str(e).lower() or "429" in str(e):
                logger.debug(f"Zilean rate limit exceeded for item: {item.log_string}")
            else:
                logger.exception(f"Zilean exception thrown: {e}")

        return {}

    def _build_query_params(self, item: MediaItem) -> Params:
        """Build the query params for the Zilean API"""

        query = item.top_title
        season = None
        episode = None

        if isinstance(item, Show):
            season = 1
        elif isinstance(item, Season):
            season = item.number
        elif isinstance(item, Episode):
            season = item.parent.number
            episode = item.number

        return Params(
            query=query,
            season=season,
            episode=episode,
        )

    def scrape(self, item: MediaItem) -> dict[str, str]:
        """Wrapper for `Zilean` scrape method"""

        params = self._build_query_params(item)

        # Use failover across all configured URLs
        response = self.request_with_failover(
            self.session,
            self.settings.urls,
            "dmm/filtered",
            params=params.model_dump(exclude_none=True),
            timeout=self.timeout,
        )

        if not response or not response.ok:
            if response:
                logger.error(
                    f"Zilean responded with status code {response.status_code} for {item.log_string}: {response.text}"
                )
            return {}

        data = ZileanScrapeResponse.model_validate({"data": response.json()}).data

        if not data:
            logger.log("NOT_FOUND", f"No streams found for {item.log_string}")
            return {}

        torrents = dict[str, str]()

        for result in data:
            if not result.raw_title or not result.info_hash:
                continue

            torrents[result.info_hash] = result.raw_title

        if torrents:
            logger.log(
                "SCRAPER", f"Found {len(torrents)} streams for {item.log_string}"
            )
        else:
            logger.log("NOT_FOUND", f"No streams found for {item.log_string}")

        return torrents

