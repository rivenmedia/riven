"""Program main module"""
import os
from typing import Optional
from pydantic import BaseModel, HttpUrl, Field
from program.symlink import Symlinker
from utils.logger import logger, get_data_path
from utils.settings import settings_manager
from program.media import MediaItemContainer
from program.libraries.plex import Library as Plex
from program.debrid.realdebrid import Debrid as RealDebrid
from program.content import Content
from program.scrapers import Scraping


# Pydantic models for configuration
class PlexConfig(BaseModel):
    user: str
    token: str
    address: HttpUrl
    watchlist: Optional[HttpUrl] = None


class MdblistConfig(BaseModel):
    lists: list[str] = Field(default_factory=list)
    api_key: str
    update_interval: int = 80


class OverseerrConfig(BaseModel):
    url: HttpUrl
    api_key: str


class RealDebridConfig(BaseModel):
    api_key: str


class TorrentioConfig(BaseModel):
    filter: str


class Settings(BaseModel):
    version: str
    debug: bool
    service_mode: bool
    log: bool
    menu_on_startup: bool
    plex: PlexConfig
    mdblist: MdblistConfig
    overseerr: OverseerrConfig
    scraper_torrentio: TorrentioConfig
    realdebrid: RealDebridConfig


class Program:
    """Program class"""

    def __init__(self):
        logger.info("Iceberg initializing...")
        self.settings = settings_manager.get_all()
        self.media_items = MediaItemContainer(items=[])
        self.data_path = get_data_path()
        self.media_items.load(os.path.join(self.data_path, "media.pkl"))
        self.threads = [
            Content(self.media_items),  # Content must be first
            Plex(self.media_items),
            RealDebrid(self.media_items),
            Symlinker(self.media_items),
            Scraping(self.media_items),
        ]
        logger.info("Iceberg initialized!")

    def start(self):
        for thread in self.threads:
            thread.start()

    def stop(self):
        for thread in self.threads:
            thread.stop()
        self.media_items.save(os.path.join(self.data_path, "media.pkl"))
