"""Program main module"""
from typing import Optional
from pydantic import BaseModel, HttpUrl, Field
from utils.logger import logger
from utils.settings import settings_manager
from program.media import MediaItemContainer
from program.libraries.plex import Library as Plex
from program.debrid.realdebrid import Debrid as RealDebrid
import importlib
import inspect
import os
import sys


# Pydantic models for configuration
class PlexConfig(BaseModel):
    user: str
    token: str
    url: HttpUrl
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
    plex: PlexConfig
    mdblist: MdblistConfig
    overseerr: OverseerrConfig
    scraper_torrentio: TorrentioConfig
    realdebrid: RealDebridConfig


class Program:
    """Program class"""
    def __init__(self):
        self.settings = settings_manager.get_all()
        self.plex = Plex()
        self.debrid = RealDebrid()
        self.media_items = MediaItemContainer(items=[])
        self.content_services = self.__import_modules("backend/program/content")
        self.scraping_services = self.__import_modules("backend/program/scrapers")

        if not os.path.exists("data"):
            os.mkdir("data")

    def run(self):
        """Run the program"""
        if self._validate_modules():
            return
        
        self.media_items.load("data/media.pkl")
        self.plex.update_sections(self.media_items)

        for content_service in self.content_services:
            content_service.update_items(self.media_items)

        self.plex.update_items(self.media_items)
        
        for scraper in self.scraping_services:
            scraper.scrape(self.media_items)
        
        self.debrid.download(self.media_items)
        self.media_items.save("data/media.pkl")

    def _validate_modules(self):
        if len(self.content_services) == 0:
            logger.error("No content services configured, skipping cycle!")
            return True
        if len(self.scraping_services) == 0:
            logger.error("No scraping services configured, skipping cycle!")
            return True
        return False

    def __import_modules(self, folder_path: str) -> list[object]:
        if os.path.exists('/iceberg'):
            folder_path = os.path.join('/iceberg', folder_path)
        else:
            folder_path = folder_path
        file_list = [
            f[:-3]
            for f in os.listdir(folder_path)
            if f.endswith(".py") and f != "__init__.py"
        ]
        module_path_name = folder_path.split("/")[-1]
        modules = []
        for module_name in file_list:
            module = importlib.import_module(
                f"..{module_name}", f"program.{module_path_name}.{module_name}"
            )
            sys.modules[module_name] = module
            clsmembers = inspect.getmembers(module, inspect.isclass)
            wanted_classes = ["Content", "Scraper"]
            for name, obj in clsmembers:
                if name in wanted_classes:
                    module = obj()
                    if module.initialized:
                        try:
                            modules.append(module)
                        except TypeError as exception:
                            logger.error(exception)
                            raise KeyboardInterrupt from exception
        return modules
