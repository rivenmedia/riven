from program.media.item import MediaItem
from utils.logger import logger

from .alldebrid import AllDebridDownloader
from .realdebrid import RealDebridDownloader
from .torbox import TorBoxDownloader


class Downloader:
    failed_items = []

    def __init__(self):
        self.key = "downloader"
        self.initialized = False
        self.services = {
            RealDebridDownloader: RealDebridDownloader(),
            TorBoxDownloader: TorBoxDownloader(),
            AllDebridDownloader: AllDebridDownloader(),
        }
        self.initialized = self.validate()
        
    @property
    def service(self):
        return next(service for service in self.services.values() if service.initialized)

    def validate(self):
        initialized_services = [service for service in self.services.values() if service.initialized]
        if len(initialized_services) > 1:
            logger.error("More than one downloader service is initialized. Only one downloader can be initialized at a time.")
            return False
        return len(initialized_services) == 1

    def run(self, item: MediaItem):
        if not self.service.run(item):
            self.failed_items.append(item)
        yield item

    @staticmethod
    def should_submit(item: MediaItem) -> bool:
        return item not in Downloader.failed_items