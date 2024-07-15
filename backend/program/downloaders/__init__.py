from .realdebrid import RealDebridDownloader
from .alldebrid import AllDebridDownloader
from .torbox import TorBoxDownloader
from program.media.item import MediaItem


class Downloader:
    def __init__(self, hash_cache):
        self.key = "downloader"
        self.initialized = False
        self.services = [
            RealDebridDownloader(hash_cache),
            TorBoxDownloader(hash_cache),
            AllDebridDownloader(hash_cache),
        ]
        self.initialized = self.validate()

    def validate(self):
        return any(service.initialized for service in self.services)

    def run(self, item: MediaItem):
        yield next(self.service.run(item))