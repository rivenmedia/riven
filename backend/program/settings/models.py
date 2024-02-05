"""Iceberg settings models"""

from typing import Optional
from pathlib import Path

from pydantic import BaseModel, root_validator


class NotifyingBaseModel(BaseModel):
    class Config:
        arbitrary_types_allowed = True
    
    # Assuming _notify_observers is a static method or class-level attribute
    _notify_observers = None

    # This method sets the change notifier on the class, not an instance
    @classmethod
    def set_notify_observers(cls, notify_observers_callable):
        cls._notify_observers = notify_observers_callable

    def __setattr__(self, name, value):
        super().__setattr__(name, value)
        if self.__class__._notify_observers:
            self.__class__._notify_observers()

class PlexModel(NotifyingBaseModel):
    user: str = ""
    token: str = ""
    url: str = "http://localhost:32400"

class DebridModel(NotifyingBaseModel):
    api_key: str = ""

class SymlinkModel(NotifyingBaseModel):
    host_path: Path = Path()
    container_path: Path = Path()

# Content Services
class ContentNotifyingBaseModel(NotifyingBaseModel):
    update_interval: int = 80

class ListrrModel(ContentNotifyingBaseModel):
    enabled: bool = False
    movie_lists: list[str] = [""]
    show_lists: list[str] = [""]
    api_key: str = ""

class MdblistModel(ContentNotifyingBaseModel):
    enabled: bool = False
    api_key: str = ""
    lists: list[str] = [""]

class OverseerrModel(ContentNotifyingBaseModel):
    enabled: bool = False
    url: str = "http://localhost:5055"
    api_key: str = ""

class PlexWatchlistModel(ContentNotifyingBaseModel):
    enabled: bool = False
    rss: str = ""

class ContentModel(NotifyingBaseModel):
    listrr: ListrrModel = ListrrModel()
    mdblist: MdblistModel = MdblistModel()
    overseerr: OverseerrModel = OverseerrModel()
    plex_watchlist: PlexWatchlistModel = PlexWatchlistModel()

# Scraper Services

class JackettConfig(NotifyingBaseModel):
    enabled: bool = False
    url: str = "http://localhost:9117"

class OrionoidConfig(NotifyingBaseModel):
    enabled: bool = False
    api_key: str = ""

class TorrentioConfig(NotifyingBaseModel):
    enabled: bool = False
    filter: str = "sort=qualitysize%7Cqualityfilter=480p,scr,cam,unknown"

class ScraperModel(NotifyingBaseModel):
    after_2: float = 0.5
    after_5: int = 2
    after_10: int = 24
    jackett: JackettConfig = JackettConfig()
    orionoid: OrionoidConfig = OrionoidConfig()
    torrentio: TorrentioConfig = TorrentioConfig()

class ParserModel(NotifyingBaseModel):
    highest_quality: bool = False
    include_4k: bool = False
    repack_proper:  bool = True
    language: list[str] = ["English"]


class AppModel(NotifyingBaseModel):
    version: str = "0.4.3"
    debug: bool = True
    log: bool = True
    plex: PlexModel = PlexModel()
    real_debrid: DebridModel = DebridModel()
    symlink: SymlinkModel = SymlinkModel()
    content: ContentModel = ContentModel()
    scraper: ScraperModel = ScraperModel()
    parser:  ParserModel = ParserModel()