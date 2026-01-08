"""Mediafusion scraper module"""

from loguru import logger
from pydantic import BaseModel, Field

from program.media.item import Episode, MediaItem
from program.services.scrapers.base import ScraperService
from program.settings import settings_manager
from program.settings.models import AppModel, MediafusionConfig
from program.utils.request import SmartSession, get_hostname_from_url


class MediaFusionEncryptUserDataResponse(BaseModel):
    status: str
    encrypted_str: str
    message: str | None = None


class MediaFusionScrapeResponse(BaseModel):
    class MediaFusionStream(BaseModel):
        name: str
        description: str
        info_hash: str | None = Field(alias="infoHash")

    streams: list[MediaFusionStream]


class Mediafusion(ScraperService[MediafusionConfig]):
    # This service requires an IMDb id
    requires_imdb_id = True

    """Scraper for `Mediafusion`"""

    def __init__(self):
        super().__init__()

        self.api_key = None
        self.downloader = None
        self.app_settings: AppModel = settings_manager.settings
        self.settings = self.app_settings.scraping.mediafusion
        self.timeout = self.settings.timeout
        self.encrypted_string = None

        self.session = SmartSession(
            base_url=self.settings.url.rstrip("/"),
            rate_limits=(
                {
                    # 1000 calls per minute
                    get_hostname_from_url(self.settings.url): {
                        "rate": 1000 / 60,
                        "capacity": 1000,
                    }
                }
                if self.settings.ratelimit
                else None
            ),
            retries=self.settings.retries,
            backoff_factor=0.3,
        )
        self._initialize()

    def validate(self) -> bool:
        """Validate the Mediafusion settings."""

        if not self.settings.enabled:
            return False

        if not self.settings.url:
            logger.error("Mediafusion URL is not configured and will not be used.")
            return False

        if "elfhosted" in self.settings.url.lower():
            logger.warning(
                "Elfhosted Mediafusion instance is no longer supported. Please use a different instance."
            )
            return False

        if self.timeout <= 0:
            logger.error("Mediafusion timeout is not set or invalid.")
            return False

        payload = {
            "max_streams_per_resolution": 100,
            "live_search_streams": True,
            "show_full_torrent_name": True,
            "torrent_sorting_priority": [],  # Disable sort order. This doesn't matter as we sort later.
            "nudity_filter": ["Disable"],
            "certification_filter": ["Disable"],
        }

        headers = {"Content-Type": "application/json"}

        try:
            response = self.session.post(
                "/encrypt-user-data", json=payload, headers=headers
            )

            if not response.ok:
                logger.error(
                    f"Mediafusion encrypt user data request failed with status code {response.status_code}"
                )
                return False

            data = MediaFusionEncryptUserDataResponse.model_validate(response.json())

            if data.status != "success":
                logger.error(f"Failed to encrypt user data: {data.message}")
                return False

            self.encrypted_string = data.encrypted_str
        except Exception as e:
            logger.error(f"Failed to encrypt user data: {e}")
            return False

        try:
            response = self.session.get("/manifest.json", timeout=self.timeout)

            return response.ok
        except Exception as e:
            logger.error(f"Mediafusion failed to initialize: {e}")
            return False

    def run(self, item: MediaItem) -> dict[str, str]:
        """
        Scrape the mediafusion site for the given media items
        and update the object with scraped streams
        """

        try:
            return self.scrape(item)
        except Exception as e:
            if "rate limit" in str(e).lower() or "429" in str(e):
                logger.debug(
                    f"Mediafusion ratelimit exceeded for item: {item.log_string}"
                )
            elif "timeout" in str(e).lower():
                logger.warning(f"Mediafusion timeout for item: {item.log_string}")
            else:
                logger.exception(f"Mediafusion exception thrown: {e}")

        return {}

    def scrape(self, item: MediaItem) -> dict[str, str]:
        """Wrapper for `Mediafusion` scrape method"""

        identifier, scrape_type, imdb_id = self.get_stremio_identifier(item)

        if not imdb_id:
            return {}

        url = f"/{self.encrypted_string}/stream/{scrape_type}/{imdb_id}"

        if identifier:
            url += identifier

        response = self.session.get(f"{url}.json", timeout=self.timeout)

        if not response.ok:
            logger.debug(
                f"Mediafusion scrape request failed with status code {response.status_code} for {item.log_string}"
            )
            return {}

        data = MediaFusionScrapeResponse.model_validate(response.json())

        if not data.streams:
            logger.log("NOT_FOUND", f"No streams found for {item.log_string}")
            return {}

        torrents = dict[str, str]()

        for stream in data.streams:
            if "rate-limit exceeded" in stream.name:
                raise Exception(
                    f"Mediafusion rate-limit exceeded for item: {item.log_string}"
                )

            if not all(stream.info_hash for stream in data.streams):
                logger.debug(
                    "Streams were found but were filtered due to your MediaFusion settings."
                )
                filtered_message = stream.description.replace(
                    "🚫 Streams Found\n⚙️ Filtered by your configuration preferences\n",
                    "",
                )
                filtered_message = (
                    filtered_message.replace("\n", ". ")
                    .replace(" ⚙️", "")
                    .replace("🚫", "")
                )
                logger.debug(filtered_message)

                return torrents

            description_split = stream.description.replace("📂 ", "")
            raw_title = description_split.split("\n")[0]

            if scrape_type == "series":
                if isinstance(item, Episode):
                    raw_title = raw_title.split(" ┈➤ ")[-1].strip()
                else:
                    raw_title = raw_title.split(" ┈➤ ")[0].strip()

            info_hash = stream.info_hash

            if info_hash and info_hash not in torrents:
                torrents[info_hash] = raw_title

        if torrents:
            logger.log(
                "SCRAPER", f"Found {len(torrents)} streams for {item.log_string}"
            )
        else:
            logger.log("NOT_FOUND", f"No streams found for {item.log_string}")

        return torrents
