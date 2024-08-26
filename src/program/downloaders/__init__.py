from program.media.item import MediaItem
from utils.logger import logger

from .alldebrid import AllDebridDownloader
from .realdebrid import RealDebridDownloader
from .torbox import TorBoxDownloader


class Downloader:
    def __init__(self):
        self.key = "downloader"
        self.initialized = False
        self.service = next((service for service in [
            RealDebridDownloader(),
            #AllDebridDownloader(),
            #TorBoxDownloader()
            ] if service.initialized), None)

        self.initialized = self.validate()

    def validate(self):
        if self.service is None:
            logger.error("No downloader service is initialized. Please initialize a downloader service.")
            return False
        return True

    def run(self, item: MediaItem):
        logger.debug(f"Running downloader for {item.log_string}")
        if self.service.is_cached(item):
            self.service.download_cached(item)
            logger.log("DEBRID", f"Downloaded {item.log_string}")
        else:
            logger.log("DEBRID", f"No cached torrents found for {item.log_string}")
        yield item