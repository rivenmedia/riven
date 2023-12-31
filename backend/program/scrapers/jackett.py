""" Jackett scraper module """
from datetime import datetime
from typing import Optional
from pydantic import BaseModel
from utils.logger import logger
from utils.request import get
from utils.settings import settings_manager
from utils.utils import parser
from requests.exceptions import ReadTimeout
import xmltodict

class JackettConfig(BaseModel):
    url: Optional[str]
    api_key: Optional[str]


class Jackett:
    """Scraper for Jackett"""

    def __init__(self):
        self.settings = "jackett"
        self.class_settings = JackettConfig(**settings_manager.get(self.settings))
        self.last_scrape = 0
        self.initialized = False

        if self.validate_settings():
            self.initialized = True

    def validate_settings(self) -> bool:
        """Validate the Jackett class_settings."""
        if self.class_settings.api_key and self.class_settings.url:
            return True
        logger.info("Jackett is not configured and will not be used.")
        return False

    def run(self, item):
        """Scrape Jackett for the given media items
        and update the object with scraped streams"""
        if self._can_we_scrape(item):
            try:
                self._scrape_item(item)
            except ReadTimeout as e:
                logger.warning("Jackett timed out: %s", e)
                return

    def _can_we_scrape(self, item) -> bool:
        return self._is_released(item) and self._needs_new_scrape(item)

    def _is_released(self, item) -> bool:
        return item.aired_at is not None and item.aired_at < datetime.now()

    def _needs_new_scrape(self, item) -> bool:
        return (
            datetime.now().timestamp() - item.scraped_at
            > 60 * 30  # 30 minutes between scrapes
            or item.scraped_at == 0
        )

    def _scrape_item(self, item):
        data = self.api_scrape(item)
        log_string = item.title
        if item.type == "season":
            log_string = f"{item.parent.title} S{item.number}"
        if item.type == "episode":
            log_string = f"{item.parent.parent.title} S{item.parent.number}E{item.number}"
        if len(data) > 0:
            item.set("streams", data)
            logger.debug("Found %s streams for %s", len(data), log_string)
        else:
            logger.debug("Could not find streams for %s", log_string)

    def api_scrape(self, item):
        """Wrapper for torrentio scrape method"""
        query = ""
        if item.type == "movie":
            query = f"&t=movie&imdbid={item.imdb_id}"
        if item.type == "season":
            query = f"&t=tv-search&imdbid={item.parent.imdb_id}&season={item.number}"
        if item.type == "episode":
            query = f"&t=tv-search&imdbid={item.parent.parent.imdb_id}&season={item.parent.number}&ep={item.number}"

        url = (
            f"{self.class_settings.url}/api/v2.0/indexers/!status:failing,test:passed/results/torznab?apikey={self.class_settings.api_key}{query}"
        )
        response = get(url=url, retry_if_failed=False, timeout=60)
        if response.is_ok:
            data = {}
            for stream in response.data['rss']['channel']['item']:
                title = stream.get('title')
                infohash = None
                for attr in stream.get('torznab:attr', []):
                    if attr.get('@name') == 'infohash':
                        infohash = attr.get('@value')
                        break
                if parser.parse(title) and infohash:
                    data[infohash] = {"name": title}
            if len(data) > 0:
                return data
        return {}