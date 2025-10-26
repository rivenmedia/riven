"""AIOStreams scraper module"""

import re
from typing import Dict

from loguru import logger

from program.media.item import MediaItem
from program.settings.manager import settings_manager
from program.settings.models import AIOStreamsConfig
from program.utils.request import SmartSession
from .base import ScraperService


class AIOStreams(ScraperService):
    """Scraper for `AIOStreams`"""

    requires_imdb_id = True

    def __init__(self):
        super().__init__("aiostreams")
        self.settings: AIOStreamsConfig = settings_manager.settings.scraping.aiostreams
        self.timeout: int = self.settings.timeout or 30

        self.session = SmartSession(retries=3, backoff_factor=0.3)
        self.headers = {"User-Agent": "Mozilla/5.0"}
        self._initialize()

    def validate(self) -> bool:
        """Validate the AIOStreams settings."""
        if not self.settings.enabled:
            return False
        if not self.settings.manifest_url:
            logger.error(
                "AIOStreams manifest URL is not configured and will not be used."
            )
            return False
        if not isinstance(self.timeout, int) or self.timeout <= 0:
            logger.error("AIOStreams timeout is not set or invalid.")
            return False
        try:
            # Validate manifest URL
            response = self.session.get(
                self.settings.manifest_url, timeout=10, headers=self.headers
            )
            if response.ok:
                return True
        except Exception as e:
            logger.error(
                f"AIOStreams failed to initialize: {e}",
            )
            return False
        return True

    def run(self, item: MediaItem) -> Dict[str, str]:
        """Scrape AIOStreams with the given media item for streams"""
        try:
            return self.scrape(item)
        except Exception as e:
            if "rate limit" in str(e).lower() or "429" in str(e):
                logger.debug(
                    f"AIOStreams rate limit exceeded for item: {item.log_string}"
                )
            else:
                logger.exception(f"AIOStreams exception thrown: {str(e)}")
        return {}

    def scrape(self, item: MediaItem) -> Dict[str, str]:
        """Wrapper for `AIOStreams` scrape method"""
        identifier, scrape_type, imdb_id = self.get_stremio_identifier(item)
        if not imdb_id:
            return {}

        # Extract base URL from manifest URL
        # manifest_url format: https://aiostreams.viren070.me/stremio/{user_id}/{token}/manifest.json
        # stream URL format: https://aiostreams.viren070.me/stremio/{user_id}/{token}/stream/{type}/{imdb_id}[:{season}:{episode}].json
        base_url = self.settings.manifest_url.replace("/manifest.json", "")

        url = f"{base_url}/stream/{scrape_type}/{imdb_id}"
        if identifier:
            url += identifier

        response = self.session.get(
            f"{url}.json",
            timeout=self.timeout,
            headers=self.headers,
        )
        if (
            not response.ok
            or not hasattr(response.data, "streams")
            or not response.data.streams
        ):
            logger.log("NOT_FOUND", f"No streams found for {item.log_string}")
            return {}

        torrents: Dict[str, str] = {}
        for stream in response.data.streams:
            # Extract infohash from stream URL
            # AIOStreams URL format: .../strem/{imdb_id}/{service}/{infohash}/{fileIdx}/{filename}
            infohash = None
            if hasattr(stream, "url") and stream.url:
                # Extract 40-character hex infohash from URL path
                match = re.search(r"/([a-fA-F0-9]{40})/", stream.url)
                if match:
                    infohash = match.group(1)

            if not infohash:
                continue

            # Build title from filename in behaviorHints
            stream_title = ""
            if (
                hasattr(stream, "behaviorHints")
                and hasattr(stream.behaviorHints, "filename")
                and stream.behaviorHints.filename
            ):
                stream_title = stream.behaviorHints.filename
            else:
                stream_title = f"AIOStreams - {infohash[:8]}"

            torrents[infohash] = stream_title

        if torrents:
            logger.log(
                "SCRAPER", f"Found {len(torrents)} streams for {item.log_string}"
            )
        else:
            logger.log("NOT_FOUND", f"No streams found for {item.log_string}")

        return torrents
