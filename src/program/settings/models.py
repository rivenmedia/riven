"""Riven settings models"""
from pathlib import Path
from typing import Any, Callable, List

from pydantic import BaseModel, Field, field_validator
from RTN.models import SettingsModel

from program.settings.migratable import MigratableBaseModel
from program.utils import generate_api_key, get_version

deprecation_warning = "This has been deprecated and will be removed in a future version."

class Observable(MigratableBaseModel):
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

    @staticmethod
    def _notify_observers_context():
        class NotifyContextManager:
            def __enter__(self_):
                pass

            def __exit__(self_, exc_type, exc_value, traceback):
                pass

        return NotifyContextManager()


# Download Services

class RealDebridModel(Observable):
    enabled: bool = False
    api_key: str = ""


class AllDebridModel(Observable):
    enabled: bool = False
    api_key: str = ""


class DownloadersModel(Observable):
    video_extensions: List[str] = ["mp4", "mkv", "avi"]
    movie_filesize_mb_min: int = 700
    movie_filesize_mb_max: int = -1 # -1 is no limit
    episode_filesize_mb_min: int = 100
    episode_filesize_mb_max: int = -1 # -1 is no limit
    proxy_url: str = ""
    real_debrid: RealDebridModel = RealDebridModel()
    all_debrid: AllDebridModel = AllDebridModel()


# Symlink Service


class SymlinkModel(Observable):
    rclone_path: Path = Path()
    library_path: Path = Path()
    separate_anime_dirs: bool = False
    repair_symlinks: bool = False
    repair_interval: float = 6 # hours


# Content Services


class Updatable(Observable):
    update_interval: int = 80

    @field_validator("update_interval")
    def check_update_interval(cls, v):
        if v < (limit := 5):
            raise ValueError(f"update_interval must be at least {limit} seconds")
        return v


# Updaters


class PlexLibraryModel(Observable):
    enabled: bool = False
    token: str = ""
    url: str = "http://localhost:32400"


class JellyfinLibraryModel(Observable):
    enabled: bool = False
    api_key: str = ""
    url: str = "http://localhost:8096"


class EmbyLibraryModel(Observable):
    enabled: bool = False
    api_key: str = ""
    url: str = "http://localhost:8096"


class UpdatersModel(Observable):
    updater_interval: int = 120
    plex: PlexLibraryModel = PlexLibraryModel()
    jellyfin: JellyfinLibraryModel = JellyfinLibraryModel()
    emby: EmbyLibraryModel = EmbyLibraryModel()


# Content Services


class ListrrModel(Updatable):
    enabled: bool = False
    movie_lists: List[str] = []
    show_lists: List[str] = []
    api_key: str = ""
    update_interval: int = 86400


class MdblistModel(Updatable):
    enabled: bool = False
    api_key: str = ""
    lists: List[int | str] = []
    update_interval: int = 86400


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


class TraktOauthModel(BaseModel):
    oauth_client_id: str = ""
    oauth_client_secret: str = ""
    oauth_redirect_uri: str = ""
    access_token: str = ""
    refresh_token: str = ""


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
    fetch_most_watched: bool = False
    most_watched_period: str = "weekly"
    most_watched_count: int = 10
    update_interval: int = 86400
    oauth: TraktOauthModel = TraktOauthModel()


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
    ratelimit: bool = Field(default=True, deprecated=deprecation_warning)
    proxy_url: str = ""


class KnightcrawlerConfig(Observable):
    enabled: bool = False
    filter: str = "sort=qualitysize%7Cqualityfilter=480p,scr,cam"
    url: str = "https://knightcrawler.elfhosted.com"
    timeout: int = 30
    ratelimit: bool = True


class CometConfig(Observable):
    enabled: bool = False
    url: str = "http://localhost:8000"
    indexers: List[str] = [
        "bitsearch",
        "eztv",
        "thepiratebay",
        "therarbg",
        "yts"
    ]
    timeout: int = 30
    ratelimit: bool = True


class ZileanConfig(Observable):
    enabled: bool = False
    url: str = "http://localhost:8181"
    timeout: int = 30
    ratelimit: bool = Field(default=True, deprecated=deprecation_warning)


class MediafusionConfig(Observable):
    enabled: bool = False
    url: str = "https://mediafusion.elfhosted.com"
    timeout: int = 30
    ratelimit: bool = True

class OrionoidConfig(Observable):
    enabled: bool = False
    api_key: str = ""
    cached_results_only: bool = False
    parameters: dict[str, Any] = {
        "video3d": "false",
        "videoquality": "sd_hd8k",
        "limitcount": 5
    }
    timeout: int = 30
    ratelimit: bool = Field(default=True, deprecated=deprecation_warning)


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


class ScraperModel(Observable):
    after_2: float = 2
    after_5: float = 6
    after_10: float = 24
    parse_debug: bool = False
    enable_aliases: bool = True
    bucket_limit: int = Field(default=5, ge=0, le=20)
    max_failed_attempts: int = Field(default=0, ge=0, le=10)
    dubbed_anime_only: bool = False
    torrentio: TorrentioConfig = TorrentioConfig()
    knightcrawler: KnightcrawlerConfig = KnightcrawlerConfig()
    jackett: JackettConfig = JackettConfig()
    prowlarr: ProwlarrConfig = ProwlarrConfig()
    orionoid: OrionoidConfig = OrionoidConfig()
    mediafusion: MediafusionConfig = MediafusionConfig()
    zilean: ZileanConfig = ZileanConfig()
    comet: CometConfig = CometConfig()


# Version Ranking Model (set application defaults here!)


class RTNSettingsModel(SettingsModel, Observable):
    ...


# Application Settings


class IndexerModel(Observable):
    update_interval: int = 60 * 60

class DatabaseModel(Observable):
    host: str = "postgresql+psycopg2://postgres:postgres@localhost/riven"

class NotificationsModel(Observable):
    enabled: bool = False
    title: str = "Riven completed something!"
    on_item_type: List[str] = ["movie", "show", "season"]
    service_urls: List[str] = []

class SubliminalConfig(Observable):
    enabled: bool = False
    languages: List[str] = ["eng"]
    providers: dict = {
        "opensubtitles": {
            "enabled": False,
            "username": "",
            "password": ""
        },
        "opensubtitlescom": {
            "enabled": False,
            "username": "",
            "password": ""
        }
    }

class PostProcessing(Observable):
    subliminal: SubliminalConfig = SubliminalConfig()

class AppModel(Observable):
    version: str = get_version()
    api_key: str = ""
    debug: bool = True
    debug_database: bool = False
    log: bool = True
    force_refresh: bool = False
    map_metadata: bool = True
    tracemalloc: bool = False
    symlink: SymlinkModel = SymlinkModel()
    updaters: UpdatersModel = UpdatersModel()
    downloaders: DownloadersModel = DownloadersModel()
    content: ContentModel = ContentModel()
    scraping: ScraperModel = ScraperModel()
    ranking: RTNSettingsModel = RTNSettingsModel()
    indexer: IndexerModel = IndexerModel()
    database: DatabaseModel = DatabaseModel()
    notifications: NotificationsModel = NotificationsModel()
    post_processing: PostProcessing = PostProcessing()

    def __init__(self, **data: Any):
        current_version = get_version()
        existing_version = data.get("version", current_version)
        super().__init__(**data)
        if existing_version < current_version:
            self.version = current_version

        if self.api_key == "":
            self.api_key = generate_api_key()
