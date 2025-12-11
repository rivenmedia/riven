"""Torrentio scraper module"""

from loguru import logger
from pydantic import BaseModel, Field
from requests import HTTPError

from program.media.item import MediaItem
from program.services.scrapers.base import ScraperService
from program.settings import settings_manager
from program.settings.models import TorrentioConfig
from program.utils.request import SmartSession


class TorrentioScrapeResponse(BaseModel):
    """Model for Torrentio scrape response"""

    class Stream(BaseModel):
        title: str
        info_hash: str = Field(alias="infoHash")

    streams: list[Stream]


class Torrentio(ScraperService[TorrentioConfig]):
    """Scraper for `Torrentio`"""

    requires_imdb_id = True

    def __init__(self):
        super().__init__()

        self.settings = settings_manager.settings.scraping.torrentio
        self.timeout = self.settings.timeout or 15

        self.session = SmartSession(
            rate_limits=(
                {
                    "torrentio.strem.fun": {
                        "rate": 150 / 60,
                        "capacity": 150,
                    }  # 150 calls per minute
                }
                if self.settings.ratelimit
                else None
            ),
            retries=self.settings.retries,
            backoff_factor=0.3,
        )
        self.headers = {"User-Agent": "Mozilla/5.0"}
        self.proxies = (
            {"http": self.settings.proxy_url, "https": self.settings.proxy_url}
            if self.settings.proxy_url
            else None
        )

        self._initialize()

    def validate(self) -> bool:
        """Validate the Torrentio settings."""

        if not self.settings.enabled:
            return False

        if not self.settings.url:
            logger.error("Torrentio URL is not configured and will not be used.")
            return False

        if self.timeout <= 0:
            logger.error("Torrentio timeout must be a positive integer.")
            return False

        try:
            url = f"{self.settings.url}/{self.settings.filter}/manifest.json"

            response = self.session.get(
                url, timeout=10, headers=self.headers, proxies=self.proxies
            )

            return response.ok
        except Exception as e:
            logger.error(f"Torrentio failed to initialize: {e}")

            return False

    async def run(self, item: MediaItem) -> dict[str, str]:
        """Scrape Torrentio with the given media item for streams"""

        try:
            return self.scrape(item)
        except HTTPError as http_err:
            if http_err.response.status_code == 429:
                logger.debug(
                    f"Torrentio rate limit exceeded for item: {item.log_string}"
                )
            else:
                logger.error(
                    f"Torrentio HTTP error for {item.log_string}: {str(http_err)}"
                )
        except Exception as e:
            logger.exception(f"Torrentio exception thrown: {str(e)}")

        return {}

    def scrape(self, item: MediaItem) -> dict[str, str]:
        """Wrapper for `Torrentio` scrape method"""

        identifier, scrape_type, imdb_id = self.get_stremio_identifier(item)

        if not imdb_id:
            return {}

        url = (
            f"{self.settings.url}/{self.settings.filter}/stream/{scrape_type}/{imdb_id}"
        )

        if identifier:
            url += identifier

        response = self.session.get(
            f"{url}.json",
            timeout=self.timeout,
            headers=self.headers,
            proxies=self.proxies,
        )

        if not response.ok:
            response.raise_for_status()
            logger.error(
                f"Torrentio request failed for {item.log_string}: {response.text}"
            )
            return {}

        data = TorrentioScrapeResponse.model_validate(response.json())

        if not data.streams:
            logger.log("NOT_FOUND", f"No streams found for {item.log_string}")
            return {}

        torrents = dict[str, str]()

        for stream in data.streams:
            if not stream.info_hash:
                continue

            stream_title = stream.title.split("\n👤")[0]
            raw_title = stream_title.split("\n")[0]
            torrents[stream.info_hash] = raw_title

        if torrents:
            logger.log(
                "SCRAPER", f"Found {len(torrents)} streams for {item.log_string}"
            )
        else:
            logger.log("NOT_FOUND", f"No streams found for {item.log_string}")

        return torrents
