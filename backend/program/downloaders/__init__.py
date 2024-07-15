from .realdebrid import RealDebridDownloader
from .alldebrid import AllDebridDownloader
from .torbox import TorBoxDownloader
from .localdownloader import LocalDownloader
from program.media.item import MediaItem

class Downloader:
    def __init__(self, hash_cache):
        self.key = "downloader"
        self.initialized = False
        self.services = [
            RealDebridDownloader(hash_cache),
            TorBoxDownloader(hash_cache),
            AllDebridDownloader(hash_cache),
            LocalDownloader(hash_cache),
        ]
        self.initialized = self.validate()

    def validate(self):
        return any(service.initialized for service in self.services)

    def run(self, item: MediaItem):
        for service in self.services:
            if service.initialized:
                yield from service.run(item)