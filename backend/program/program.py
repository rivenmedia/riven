"""Program main module"""
import importlib
import inspect
import os
import sys
import requests
from pydantic import BaseModel, HttpUrl, Field
from utils.logger import logger
from utils.settings import settings_manager
from program.media import MediaItemContainer
from program.libraries.plex import Library as Plex
from program.debrid.realdebrid import Debrid as RealDebrid
from program.scrapers.torrentio import Scraper as Torrentio

# Pydantic models for configuration
class PlexConfig(BaseModel):
    user: str
    token: str
    address: HttpUrl

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
    library_plex: PlexConfig
    content_mdblist: MdblistConfig
    content_overseerr: OverseerrConfig
    scraper_torrentio: TorrentioConfig
    debrid_realdebrid: RealDebridConfig


class Program:
    """Program class"""
    def __init__(self):
        self.settings = settings_manager.get_all()
        self.plex = Plex()
        self.debrid = RealDebrid()
        self.torrentio = Torrentio()
        self.media_items = MediaItemContainer(items=[])
        self.content_services = []
        mdblist_settings = self.settings.get("content_mdblist")
        overseerr_settings = self.settings.get("content_overseerr")

        if mdblist_settings and mdblist_settings.get("api_key"):
            self.content_services += self.__import_modules("mdblist")
        else:
            logger.info("mdblist is not configured and will not be used.")

        if overseerr_settings and overseerr_settings.get("api_key") and overseerr_settings.get("url"):
            self.content_services += self.__import_modules("overseerr")
        else:
            logger.info("Overseerr is not configured and will not be used.")

        self.scraping_services = self.__import_modules("backend/program/scrapers")
        self.debrid_services = self.__import_modules("backend/program/debrid")

        if not os.path.exists("data"):
            os.mkdir("data")

    def run(self):
        """Run the program"""
        self.media_items.load("data/media.pkl")

        self.plex.update_sections(self.media_items)

        # Update content lists
        for content_service in self.content_services:
            content_service.update_items(self.media_items)

        self.plex.update_items(self.media_items)

        self.torrentio.scrape(self.media_items)
        self.debrid.download(self.media_items)

        self.media_items.save("data/media.pkl")

    def __import_modules(self, service_name: str) -> list[object]:
        folder_path = "backend/program/content"
        modules = []
        if os.path.exists(folder_path):
            for f in os.listdir(folder_path):
                if f.endswith(".py") and f != "__init__.py" and service_name in f:
                    module_name = f[:-3]
                    module = importlib.import_module(
                        f"..{module_name}", f"program.content.{module_name}"
                    )
                    sys.modules[module_name] = module
                    clsmembers = inspect.getmembers(module, inspect.isclass)
                    for name, obj in clsmembers:
                        if name == "Content":
                            module_instance = obj()
                            modules.append(module_instance)
        else:
            logger.error(f"Directory not found: {folder_path}")
        return modules