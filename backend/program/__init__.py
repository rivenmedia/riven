"""Program main module"""
import threading
import time
from typing import Optional
from pydantic import BaseModel, HttpUrl, Field
from program.media.container import MediaItemContainer
from utils.logger import logger, get_data_path
from utils.settings import settings_manager
from program.libraries.plex import Library as Plex
from program.libraries.plex import PlexConfig
from program.content import Content
from utils.utils import Pickly
import concurrent.futures


class MdblistConfig(BaseModel):
    lists: list[str] = Field(default_factory=list)
    api_key: Optional[str]
    update_interval: int = 80


class OverseerrConfig(BaseModel):
    url: Optional[HttpUrl]
    api_key: Optional[str]


class RealDebridConfig(BaseModel):
    api_key: Optional[str]


class TorrentioConfig(BaseModel):
    filter: str


class Settings(BaseModel):
    version: str
    debug: bool
    log: bool
    plex: PlexConfig
    mdblist: MdblistConfig
    overseerr: OverseerrConfig
    scraper_torrentio: TorrentioConfig
    realdebrid: RealDebridConfig


class Program(threading.Thread):
    """Program class"""

    def __init__(self):
        logger.info("Iceberg initializing...")
        super().__init__()
        self.running = False
        self.settings = settings_manager.get_all()
        self.media_items = MediaItemContainer(items=[])
        self.data_path = get_data_path()
        self.pickly = Pickly(self.media_items, self.data_path)
        self.pickly.start()
        self.threads = [
            Content(self.media_items),  # Content must be first
            Plex(self.media_items),
        ]
        logger.info("Iceberg initialized!")

    def run(self):
        while self.running:
            with concurrent.futures.ThreadPoolExecutor(max_workers=10, thread_name_prefix="Worker") as executor:
                { executor.submit(item.perform_action) for item in self.media_items }
            time.sleep(1)

    def start(self):
        self.running = True
        super().start()
        for thread in self.threads:
            thread.start()

    def stop(self):
        for thread in self.threads:
            thread.stop()
        self.pickly.stop()
        self.running = False
        super().join()

