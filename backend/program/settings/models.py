"""Iceberg settings models"""
from pathlib import Path
from pydantic import BaseModel, HttpUrl
from utils import version_file_path


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
    token: str = ""
    url: str = "http://localhost:32400"


class DebridModel(NotifyingBaseModel):
    api_key: str = ""


class SymlinkModel(NotifyingBaseModel):
    rclone_path: Path = Path()
    library_path: Path = Path()


# Content Services


class ContentNotifyingBaseModel(NotifyingBaseModel):
    update_interval: int = 80

    @validator('refresh_interval')
    def check_refresh_interval(cls, v):
        if v < (limit := 5):
            raise ValueError(f"refresh_interval must be at least {limit} seconds")
        return v


class ListrrModel(ContentNotifyingBaseModel):
    enabled: bool = False
    movie_lists: list[str] = [""]
    show_lists: list[str] = [""]
    api_key: str = ""
    update_interval: int = 300


class MdblistModel(ContentNotifyingBaseModel):
    enabled: bool = False
    api_key: str = ""
    lists: list[str] = [""]
    update_interval: int = 300


class OverseerrModel(ContentNotifyingBaseModel):
    enabled: bool = False
    url: str = "http://localhost:5055"
    api_key: str = ""
    update_interval: int = 60


class PlexWatchlistModel(ContentNotifyingBaseModel):
    enabled: bool = False
    rss: str = ""
    update_interval: int = 60


class ContentModel(NotifyingBaseModel):
    listrr: ListrrModel = ListrrModel()
    mdblist: MdblistModel = MdblistModel()
    overseerr: OverseerrModel = OverseerrModel()
    plex_watchlist: PlexWatchlistModel = PlexWatchlistModel()


# Scraper Services


class JackettConfig(NotifyingBaseModel):
    enabled: bool = False
    url: str = "http://localhost:9117"
    api_key: str = ""


class OrionoidConfig(NotifyingBaseModel):
    enabled: bool = False
    api_key: str = ""
    limitcount: int = 5


class TorrentioConfig(NotifyingBaseModel):
    enabled: bool = False
    filter: str = "sort=qualitysize%7Cqualityfilter=480p,scr,cam"
    url: HttpUrl = "https://torrentio.strem.fun"


class ScraperModel(NotifyingBaseModel):
    after_2: float = 2
    after_5: int = 6
    after_10: int = 24
    jackett: JackettConfig = JackettConfig()
    orionoid: OrionoidConfig = OrionoidConfig()
    torrentio: TorrentioConfig = TorrentioConfig()


class ParserModel(NotifyingBaseModel):
    highest_quality: bool = False
    include_4k: bool = False
    repack_proper: bool = True
    language: list[str] = ["English"]


# Application Settings


def get_version() -> str:
    with open(version_file_path.resolve()) as file:
        return file.read()


class AppModel(NotifyingBaseModel):
    version: str = get_version()
    debug: bool = True
    log: bool = True
    plex: PlexModel = PlexModel()
    real_debrid: DebridModel = DebridModel()
    symlink: SymlinkModel = SymlinkModel()
    content: ContentModel = ContentModel()
    scraping: ScraperModel = ScraperModel()
    parser: ParserModel = ParserModel()
