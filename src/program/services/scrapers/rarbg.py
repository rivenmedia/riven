"""Rarbg scraper module"""

from loguru import logger
from pydantic import BaseModel

from program.media.item import MediaItem, Movie
from program.services.scrapers.base import ScraperService
from program.settings import settings_manager
from program.settings.models import RarbgConfig
from program.utils.request import SmartSession, get_hostname_from_url


class RarbgScrapeResponse(BaseModel):
    class Result(BaseModel):
        h: str  # infoHash
        n: str  # title

    class Links(BaseModel):
        next: str | None

    results: list[Result]
    links: Links


class Rarbg(ScraperService[RarbgConfig]):
    """Scraper for `TheRARBG`"""

    def __init__(self):
        super().__init__("therarbg")

        self.settings = settings_manager.settings.scraping.rarbg
        self.timeout: int = self.settings.timeout

        self.session = SmartSession(
            base_url=self.settings.url,
            rate_limits=(
                {
                    get_hostname_from_url(self.settings.url): {
                        "rate": 350 / 60,
                        "capacity": 350,
                    }  # 350 calls per minute
                }
                if self.settings.ratelimit
                else None
            ),
            retries=self.settings.retries,
            backoff_factor=0.3,
        )

        self._initialize()

    def validate(self) -> bool:
        """Validate the TheRARBG settings."""

        if not self.settings.enabled:
            return False

        if not self.settings.url:
            logger.error("TheRARBG URL is not configured and will not be used.")
            return False

        if self.timeout <= 0:
            logger.error("TheRARBG timeout must be a positive integer.")
            return False

        try:
            url = "/get-posts/keywords:Game%20of%20Thrones:category:Movies:category:TV:category:Anime:ncategory:XXX/?format=json"
            response = self.session.get(url, timeout=10)
            if response.ok:
                return True
        except Exception as e:
            logger.error(f"TheRARBG failed to initialize: {e}", exc_info=True)
            return False
        return True

    def run(self, item: MediaItem) -> dict[str, str]:
        """Scrape TheRARBG with the given media item for streams"""

        try:
            return self.scrape(item)
        except Exception as e:
            if "rate limit" in str(e).lower() or "429" in str(e):
                logger.debug(
                    f"TheRARBG rate limit exceeded for item: {item.log_string}"
                )
            else:
                logger.exception(f"TheRARBG exception thrown: {str(e)}")
        return {}

    def scrape(self, item: MediaItem) -> dict[str, str]:
        """Wrapper for `TheRARBG` scrape method"""

        search_string = (
            item.log_string
            if not (isinstance(item, Movie) and item.aired_at)
            else f"{item.log_string} ({item.aired_at.year})"
        )

        url = f"/get-posts/keywords:{search_string}:category:Movies:category:TV:category:Anime:ncategory:XXX/?format=json"

        torrents: dict[str, str] = {}
        current_url = url
        page = 1

        while current_url:
            response = self.session.get(current_url, timeout=self.timeout)

            if not response.ok or not response.data:
                break

            data = RarbgScrapeResponse.model_validate(response.json())

            if data.results:
                for result in data.results:
                    if not result.h:  # h is the infoHash
                        continue

                    info_hash = result.h.lower()
                    title = result.n  # n is the title
                    torrents[info_hash] = title

            if page == 4:  # 50 results per page, 400 results max
                break

            current_url = None

            if data.links and data.links.next:
                if next_url := data.links.next:
                    current_url = next_url
                    page += 1

        if torrents:
            logger.log(
                "SCRAPER", f"Found {len(torrents)} streams for {item.log_string}"
            )
        else:
            logger.log("NOT_FOUND", f"No streams found for {item.log_string}")

        return torrents
