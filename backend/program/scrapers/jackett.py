""" Torrentio scraper module """
from datetime import datetime
from utils.logger import logger
from utils.request import get
from utils.settings import settings_manager
from utils.utils import parser

class Jackett:
    """Scraper for torrentio"""

    def __init__(self):
        self.settings = "jackett"
        self.url = settings_manager.get("jackett.url")
        self.api_key = settings_manager.get("jackett.api_key")
        self.initialized = True

    def run(self, item):
        """Scrape the torrentio site for the given media items
        and update the object with scraped streams"""
        self._scrape_item(item)

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
            query = f"&t=movie&q={item.title}.{item.aired_at.year}"
        if item.type == "season":
            query = f"&t=tvsearch&q={item.parent.title}.{item.parent.aired_at.year}&season={item.number}"
        if item.type == "episode":
            query = f"&t=tvsearch&q={item.parent.parent.title}.{item.parent.parent.aired_at.year}&season={item.parent.number}&ep={item.number}"

        url = (
            f"{self.url}/api/v2.0/indexers/!status:failing,test:passed/results/torznab?apikey={self.api_key}{query}"
        )
        response = get(url=url, retry_if_failed=False)
        if response.is_ok:
            data = {}
            for stream in response.data.Results:
                if parser.parse(stream.Title):
                    data[stream.InfoHash.lower()] = {
                        "name": stream.Title
                    }
            if len(data) > 0:
                return data
        return {}