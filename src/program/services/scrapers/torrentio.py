""" Torrentio scraper module """
from typing import Dict

from loguru import logger

from program.media.item import MediaItem
from program.services.scrapers.shared import (
    ScraperRequestHandler,
    _get_stremio_identifier,
)
from program.settings.manager import settings_manager
from program.settings.models import TorrentioConfig
from program.utils.request import (
    HttpMethod,
    RateLimitExceeded,
    create_service_session,
    get_rate_limit_params,
)


class Torrentio:
    """Scraper for `Torrentio`"""

    def __init__(self):
        self.key = "torrentio"
        self.settings: TorrentioConfig = settings_manager.settings.scraping.torrentio
        self.timeout: int = self.settings.timeout
        rate_limit_params = get_rate_limit_params(max_calls=1, period=5) if self.settings.ratelimit else None
        session = create_service_session(rate_limit_params=rate_limit_params)
        self.request_handler = ScraperRequestHandler(session)
        self.headers = {"User-Agent": "Mozilla/5.0"}
        self.proxies = {"http": self.settings.proxy_url, "https": self.settings.proxy_url} if self.settings.proxy_url else None
        self.initialized: bool = self.validate()
        if not self.initialized:
            return
        logger.success("Torrentio initialized!")

    def validate(self) -> bool:
        """Validate the Torrentio settings."""
        if not self.settings.enabled:
            return False
        if not self.settings.url:
            logger.error("Torrentio URL is not configured and will not be used.")
            return False
        if not isinstance(self.timeout, int) or self.timeout <= 0:
            logger.error("Torrentio timeout is not set or invalid.")
            return False
        try:
            url = f"{self.settings.url}/{self.settings.filter}/manifest.json"
            response = self.request_handler.execute(HttpMethod.GET, url, timeout=10, headers=self.headers, proxies=self.proxies)
            if response.is_ok:
                return True
        except Exception as e:
            logger.error(f"Torrentio failed to initialize: {e}", )
            return False
        return True

    def run(self, item: MediaItem) -> Dict[str, str]:
        """Scrape Torrentio with the given media item for streams"""
        try:
            return self.scrape(item)
        except RateLimitExceeded:
            logger.debug(f"Torrentio rate limit exceeded for item: {item.log_string}")
        except Exception as e:
            logger.exception(f"Torrentio exception thrown: {str(e)}")
        return {}

    def scrape(self, item: MediaItem) -> tuple[Dict[str, str], int]:
        """Wrapper for `Torrentio` scrape method"""
        identifier, scrape_type, imdb_id = _get_stremio_identifier(item)
        if not imdb_id:
            return {}

        url = f"{self.settings.url}/{self.settings.filter}/stream/{scrape_type}/{imdb_id}"
        if identifier:
            url += identifier

        response = self.request_handler.execute(HttpMethod.GET, f"{url}.json", timeout=self.timeout, headers=self.headers, proxies=self.proxies)
        if not response.is_ok or not hasattr(response.data, 'streams') or not response.data.streams:
            logger.log("NOT_FOUND", f"No streams found for {item.log_string}")
            return {}

        torrents: Dict[str, str] = {}
        for stream in response.data.streams:
            if not stream.infoHash:
                continue

            stream_title = stream.title.split("\n👤")[0]
            raw_title = stream_title.split("\n")[0]
            torrents[stream.infoHash] = raw_title

        if torrents:
            logger.log("SCRAPER", f"Found {len(torrents)} streams for {item.log_string}")
        else:
            logger.log("NOT_FOUND", f"No streams found for {item.log_string}")

        return torrents
