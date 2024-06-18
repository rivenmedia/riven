"""Riven settings models"""
from pathlib import Path
from typing import Callable, Dict, List

from pydantic import BaseModel, field_validator
from RTN.models import CustomRank, SettingsModel
from utils import version_file_path


class Observable(BaseModel):
    class Config:
        arbitrary_types_allowed = True

    _notify_observers: Callable = None

    @classmethod
    def set_notify_observers(cls, notify_observers_callable):
        cls._notify_observers = notify_observers_callable

    def __setattr__(self, name, value):
        super().__setattr__(name, value)
        if self.__class__._notify_observers:
            with self._notify_observers_context():
                self.__class__._notify_observers()


# Download Services

class DebridModel(Observable):
    enabled: bool = False
    api_key: str = ""
    proxy_enabled: bool = False 
    proxy_url: str = "" 


class TorboxModel(Observable):
    enabled: bool = False
    api_key: str = ""


class DownloadersModel(Observable):
    movie_filesize_min: int = 200   # MB
    movie_filesize_max: int = -1    # MB (-1 is no limit)
    episode_filesize_min: int = 40  # MB
    episode_filesize_max: int = -1  # MB (-1 is no limit)
    real_debrid: DebridModel = DebridModel()
    torbox: TorboxModel = TorboxModel()


# Symlink Service


class SymlinkModel(Observable):
    rclone_path: Path = Path()
    library_path: Path = Path()
    separate_anime_dirs: bool = False


# Content Services


class Updatable(Observable):
    update_interval: int = 80

    @field_validator("update_interval")
    def check_update_interval(cls, v):
        if v < (limit := 5):
            raise ValueError(f"update_interval must be at least {limit} seconds")
        return v


class PlexLibraryModel(Updatable):
    update_interval: int = 120
    token: str = ""
    url: str = "http://localhost:32400"


class ListrrModel(Updatable):
    enabled: bool = False
    movie_lists: List[str] = []
    show_lists: List[str] = []
    api_key: str = ""
    update_interval: int = 300


class MdblistModel(Updatable):
    enabled: bool = False
    api_key: str = ""
    lists: List[int | str] = []
    update_interval: int = 300


class OverseerrModel(Updatable):
    enabled: bool = False
    url: str = "http://localhost:5055"
    api_key: str = ""
    use_webhook: bool = False
    update_interval: int = 60


class PlexWatchlistModel(Updatable):
    enabled: bool = False
    rss: List[str] = []
    update_interval: int = 60


class TraktModel(Updatable):
    enabled: bool = False
    api_key: str = ""
    watchlist: List[str] = []
    user_lists: List[str] = []
    collection: List[str] = []
    fetch_trending: bool = False
    trending_count: int = 10
    fetch_popular: bool = False
    popular_count: int = 10
    update_interval: int = 300


class TraktOauthModel(BaseModel):
    # This is for app settings to handle oauth with trakt
    oauth_client_id: str = ""
    oauth_client_secret: str = ""
    oauth_redirect_uri: str = ""
    access_token: str = ""
    refresh_token: str = ""


class ContentModel(Observable):
    overseerr: OverseerrModel = OverseerrModel()
    plex_watchlist: PlexWatchlistModel = PlexWatchlistModel()
    mdblist: MdblistModel = MdblistModel()
    listrr: ListrrModel = ListrrModel()
    trakt: TraktModel = TraktModel()


# Scraper Services


class TorrentioConfig(Observable):
    enabled: bool = False
    filter: str = "sort=qualitysize%7Cqualityfilter=480p,scr,cam"
    url: str = "http://torrentio.strem.fun"
    timeout: int = 30
    ratelimit: bool = True


class KnightcrawlerConfig(Observable):
    enabled: bool = False
    filter: str = "sort=qualitysize%7Cqualityfilter=480p,scr,cam"
    url: str = "https://knightcrawler.elfhosted.com"
    timeout: int = 30
    ratelimit: bool = True


class MediafusionConfig(Observable):
    enabled: bool = False
    url: str = "https://mediafusion.elfhosted.com"
    timeout: int = 30
    ratelimit: bool = True
    catalogs: List[str] = [
        "prowlarr_streams",
        "torrentio_streams"
    ]


class OrionoidConfig(Observable):
    enabled: bool = False
    api_key: str = ""
    limitcount: int = 5
    timeout: int = 30
    ratelimit: bool = True


class JackettConfig(Observable):
    enabled: bool = False
    url: str = "http://localhost:9117"
    api_key: str = ""
    timeout: int = 30
    ratelimit: bool = True


class ProwlarrConfig(Observable):
    enabled: bool = False
    url: str = "http://localhost:9696"
    api_key: str = ""
    timeout: int = 30
    ratelimit: bool = True
    limiter_seconds: int = 60


class AnnatarConfig(Observable):
    enabled: bool = False
    url: str = "http://annatar.elfhosted.com"
    limit: int = 2000
    timeout: int = 30
    ratelimit: bool = True


class TorBoxScraperConfig(Observable):
    enabled: bool = False
    timeout: int = 30
    ratelimit: bool = True


class ScraperModel(Observable):
    after_2: float = 2
    after_5: int = 6
    after_10: int = 24
    torrentio: TorrentioConfig = TorrentioConfig()
    knightcrawler: KnightcrawlerConfig = KnightcrawlerConfig()
    jackett: JackettConfig = JackettConfig()
    prowlarr: ProwlarrConfig = ProwlarrConfig()
    orionoid: OrionoidConfig = OrionoidConfig()
    annatar: AnnatarConfig = AnnatarConfig()
    torbox_scraper: TorBoxScraperConfig = TorBoxScraperConfig()
    mediafusion: MediafusionConfig = MediafusionConfig()


# Version Ranking Model (set application defaults here!)


class RTNSettingsModel(SettingsModel, Observable):
    profile: str = "default"
    custom_ranks: Dict[str, CustomRank] = {
        "uhd": CustomRank(fetch=False, rank=120),
        "fhd": CustomRank(fetch=True, rank=100),
        "hd": CustomRank(fetch=True, rank=80),
        "sd": CustomRank(fetch=False, rank=-120),
        "bluray": CustomRank(fetch=True, rank=80),
        "hdr": CustomRank(fetch=False, rank=80),
        "hdr10": CustomRank(fetch=False, rank=90),
        "dolby_video": CustomRank(fetch=False, rank=-100),
        "dts_x": CustomRank(fetch=False, rank=0),
        "dts_hd": CustomRank(fetch=False, rank=0),
        "dts_hd_ma": CustomRank(fetch=False, rank=0),
        "atmos": CustomRank(fetch=False, rank=0),
        "truehd": CustomRank(fetch=False, rank=0),
        "ddplus": CustomRank(fetch=False, rank=0),
        "aac": CustomRank(fetch=True, rank=70),
        "ac3": CustomRank(fetch=True, rank=50),
        "remux": CustomRank(fetch=False, rank=-1000),
        "webdl": CustomRank(fetch=True, rank=90),
        "repack": CustomRank(fetch=True, rank=5),
        "proper": CustomRank(fetch=True, rank=4),
        "dubbed": CustomRank(fetch=True, rank=1),
        "subbed": CustomRank(fetch=True, rank=4),
        "av1": CustomRank(fetch=False, rank=0),
    }


# Application Settings


class IndexerModel(Observable):
    update_interval: int = 60 * 60


def get_version() -> str:
    with open(version_file_path.resolve()) as file:
        return file.read() or "x.x.x"


class AppModel(Observable):
    version: str = get_version()
    debug: bool = True
    log: bool = True
    symlink_monitor: bool = True
    force_refresh: bool = False
    local_only: bool = False
    plex: PlexLibraryModel = PlexLibraryModel()
    symlink: SymlinkModel = SymlinkModel()
    downloaders: DownloadersModel = DownloadersModel()
    content: ContentModel = ContentModel()
    scraping: ScraperModel = ScraperModel()
    ranking: RTNSettingsModel = RTNSettingsModel()
    indexer: IndexerModel = IndexerModel()
