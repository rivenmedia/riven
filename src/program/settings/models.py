"""Riven settings models"""

from pathlib import Path
from typing import Any, Callable, List, Literal, Annotated

from pydantic import BaseModel, Field, field_validator, BeforeValidator, TypeAdapter
from pydantic.networks import PostgresDsn
from RTN.models import SettingsModel

from program.settings.migratable import MigratableBaseModel
from program.utils import generate_api_key, get_version

deprecation_warning = (
    "This has been deprecated and will be removed in a future version."
)


def validate_empty_or_url(v: Any) -> str:
    if isinstance(v, str):
        if v == "":
            return v
        if not v.lower().startswith(("http://", "https://", "socks5://", "socks5h://")):
            raise ValueError("Must be a valid URL or empty string")
        return v
    raise ValueError("Must be a string")


EmptyOrUrl = Annotated[str, BeforeValidator(validate_empty_or_url)]


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
    enabled: bool = Field(default=False, description="Enable Real-Debrid")
    api_key: str = Field(default="", description="Real-Debrid API key")


class TorBoxModel(Observable):
    enabled: bool = Field(default=False, description="Enable TorBox")
    api_key: str = Field(default="", description="TorBox API key")


class DownloadersModel(Observable):
    video_extensions: List[str] = Field(
        default_factory=lambda: ["mp4", "mkv", "avi"],
        description="List of video file extensions to consider for downloads",
    )
    movie_filesize_mb_min: int = Field(
        default=700, ge=1, description="Minimum file size in MB for movies"
    )
    movie_filesize_mb_max: int = Field(
        default=-1,
        ge=-1,
        description="Maximum file size in MB for movies (-1 for no limit)",
    )
    episode_filesize_mb_min: int = Field(
        default=100, ge=1, description="Minimum file size in MB for episodes"
    )
    episode_filesize_mb_max: int = Field(
        default=-1,
        ge=-1,
        description="Maximum file size in MB for episodes (-1 for no limit)",
    )
    proxy_url: EmptyOrUrl = Field(
        default="", description="Proxy URL for downloaders (optional)"
    )
    real_debrid: RealDebridModel = Field(
        default_factory=lambda: RealDebridModel(),
        description="Real-Debrid downloader configuration",
    )
    torbox: TorBoxModel = Field(
        default_factory=lambda: TorBoxModel(),
        description="TorBox downloader configuration",
    )


# Filesystem Service


class FilesystemModel(Observable):
    mount_path: Path = Field(
        default=Path("/path/to/riven/mount"),
        description="Path where Riven will mount the virtual filesystem",
    )
    separate_anime_dirs: bool = Field(
        default=False, description="Create separate directories for anime content"
    )
    cache_dir: Path = Field(
        default=Path("/dev/shm/riven-cache"),
        description="Directory for caching downloaded chunks",
    )
    cache_max_size_mb: int = Field(
        default=10240, ge=0, description="Maximum cache size in MB (10 GiB default)"
    )
    cache_ttl_seconds: int = Field(
        default=2 * 60 * 60,
        description="Cache time-to-live in seconds (2 hours default)",
    )
    cache_eviction: Literal["LRU", "TTL"] = Field(
        default="LRU", description="Cache eviction policy (LRU or TTL)"
    )
    cache_metrics: bool = Field(
        default=True, description="Enable cache metrics logging"
    )
    chunk_size_mb: int = Field(
        default=8, ge=1, description="Size of a single fetch chunk in MB"
    )
    fetch_ahead_chunks: int = Field(
        default=4, ge=0, description="Number of chunks to fetch ahead when streaming"
    )


# Content Services


class Updatable(Observable):
    update_interval: int = Field(default=80, description="Update interval in seconds")

    @field_validator("update_interval")
    def check_update_interval(cls, v):
        if v < (limit := 5):
            raise ValueError(f"update_interval must be at least {limit} seconds")
        return v


# Updaters


class PlexLibraryModel(Observable):
    enabled: bool = Field(default=False, description="Enable Plex library updates")
    token: str = Field(default="", description="Plex authentication token")
    url: EmptyOrUrl = Field(
        default="http://localhost:32400", description="Plex server URL"
    )


class JellyfinLibraryModel(Observable):
    enabled: bool = Field(default=False, description="Enable Jellyfin library updates")
    api_key: str = Field(default="", description="Jellyfin API key")
    url: EmptyOrUrl = Field(
        default="http://localhost:8096", description="Jellyfin server URL"
    )


class EmbyLibraryModel(Observable):
    enabled: bool = Field(default=False, description="Enable Emby library updates")
    api_key: str = Field(default="", description="Emby API key")
    url: EmptyOrUrl = Field(
        default="http://localhost:8096", description="Emby server URL"
    )


class UpdatersModel(Observable):
    updater_interval: int = Field(
        default=120, ge=1, description="Interval in seconds between library updates"
    )
    library_path: Path = Field(
        default=Path("/path/to/library/mount"),
        description="Path to which your media library mount point",
    )
    plex: PlexLibraryModel = Field(
        default_factory=lambda: PlexLibraryModel(),
        description="Plex library configuration",
    )
    jellyfin: JellyfinLibraryModel = Field(
        default_factory=lambda: JellyfinLibraryModel(),
        description="Jellyfin library configuration",
    )
    emby: EmbyLibraryModel = Field(
        default_factory=lambda: EmbyLibraryModel(),
        description="Emby library configuration",
    )


# Content Services


class ListrrModel(Updatable):
    enabled: bool = Field(default=False, description="Enable Listrr integration")
    movie_lists: List[str] = Field(
        default_factory=list, description="Listrr movie list IDs"
    )
    show_lists: List[str] = Field(
        default_factory=list, description="Listrr TV show list IDs"
    )
    api_key: str = Field(default="", description="Listrr API key")
    update_interval: int = Field(
        default=86400, ge=1, description="Update interval in seconds (24 hours default)"
    )


class MdblistModel(Updatable):
    enabled: bool = Field(default=False, description="Enable MDBList integration")
    api_key: str = Field(default="", description="MDBList API key")
    lists: List[int | str] = Field(
        default_factory=list, description="MDBList list IDs to monitor"
    )
    update_interval: int = Field(
        default=86400, ge=1, description="Update interval in seconds (24 hours default)"
    )


class OverseerrModel(Updatable):
    enabled: bool = Field(default=False, description="Enable Overseerr integration")
    url: EmptyOrUrl = Field(
        default="http://localhost:5055", description="Overseerr URL"
    )
    api_key: str = Field(default="", description="Overseerr API key")
    use_webhook: bool = Field(
        default=False, description="Use webhook instead of polling"
    )
    update_interval: int = Field(
        default=60, ge=1, description="Update interval in seconds"
    )


class PlexWatchlistModel(Updatable):
    enabled: bool = Field(
        default=False, description="Enable Plex Watchlist integration"
    )
    rss: List[EmptyOrUrl] = Field(
        default_factory=list, description="Plex Watchlist RSS feed URLs"
    )
    update_interval: int = Field(
        default=60, ge=1, description="Update interval in seconds"
    )


class TraktOauthModel(BaseModel):
    oauth_client_id: str = Field(default="", description="Trakt OAuth client ID")
    oauth_client_secret: str = Field(
        default="", description="Trakt OAuth client secret"
    )
    oauth_redirect_uri: str = Field(default="", description="Trakt OAuth redirect URI")
    access_token: str = Field(default="", description="Trakt OAuth access token")
    refresh_token: str = Field(default="", description="Trakt OAuth refresh token")


class TraktModel(Updatable):
    enabled: bool = Field(default=False, description="Enable Trakt integration")
    api_key: str = Field(default="", description="Trakt API key")
    watchlist: List[str] = Field(
        default_factory=list, description="Trakt usernames for watchlist monitoring"
    )
    user_lists: List[str] = Field(
        default_factory=list, description="Trakt user list URLs to monitor"
    )
    collection: List[str] = Field(
        default_factory=list, description="Trakt usernames for collection monitoring"
    )
    fetch_trending: bool = Field(
        default=False, description="Fetch trending content from Trakt"
    )
    trending_count: int = Field(
        default=10, ge=1, description="Number of trending items to fetch"
    )
    fetch_popular: bool = Field(
        default=False, description="Fetch popular content from Trakt"
    )
    popular_count: int = Field(
        default=10, ge=1, description="Number of popular items to fetch"
    )
    fetch_most_watched: bool = Field(
        default=False, description="Fetch most watched content from Trakt"
    )
    most_watched_period: str = Field(
        default="weekly",
        description="Period for most watched (daily, weekly, monthly, yearly)",
    )
    most_watched_count: int = Field(
        default=10, ge=1, description="Number of most watched items to fetch"
    )
    update_interval: int = Field(
        default=86400, ge=1, description="Update interval in seconds (24 hours default)"
    )
    oauth: TraktOauthModel = Field(
        default_factory=lambda: TraktOauthModel(),
        description="Trakt OAuth configuration",
    )
    proxy_url: EmptyOrUrl = Field(
        default="", description="Proxy URL for Trakt API requests"
    )


class ContentModel(Observable):
    overseerr: OverseerrModel = Field(
        default_factory=lambda: OverseerrModel(), description="Overseerr configuration"
    )
    plex_watchlist: PlexWatchlistModel = Field(
        default_factory=lambda: PlexWatchlistModel(),
        description="Plex Watchlist configuration",
    )
    mdblist: MdblistModel = Field(
        default_factory=lambda: MdblistModel(), description="MDBList configuration"
    )
    listrr: ListrrModel = Field(
        default_factory=lambda: ListrrModel(), description="Listrr configuration"
    )
    trakt: TraktModel = Field(
        default_factory=lambda: TraktModel(), description="Trakt configuration"
    )


# Scraper Services


class TorrentioConfig(Observable):
    enabled: bool = Field(default=False, description="Enable Torrentio scraper")
    filter: str = Field(
        default="sort=qualitysize%7Cqualityfilter=480p,scr,cam",
        description="Torrentio filter parameters",
    )
    url: EmptyOrUrl = Field(
        default="http://torrentio.strem.fun", description="Torrentio URL"
    )
    timeout: int = Field(default=30, ge=1, description="Request timeout in seconds")
    ratelimit: bool = Field(default=True, description="Enable rate limiting")
    proxy_url: EmptyOrUrl = Field(
        default="", description="Proxy URL for Torrentio requests"
    )


class CometConfig(Observable):
    enabled: bool = Field(default=False, description="Enable Comet scraper")
    url: EmptyOrUrl = Field(default="http://localhost:8000", description="Comet URL")
    timeout: int = Field(default=30, ge=1, description="Request timeout in seconds")
    ratelimit: bool = Field(default=True, description="Enable rate limiting")


class ZileanConfig(Observable):
    enabled: bool = Field(default=False, description="Enable Zilean scraper")
    url: EmptyOrUrl = Field(default="http://localhost:8181", description="Zilean URL")
    timeout: int = Field(default=30, ge=1, description="Request timeout in seconds")
    ratelimit: bool = Field(default=True, description="Enable rate limiting")


class MediafusionConfig(Observable):
    enabled: bool = Field(default=False, description="Enable Mediafusion scraper")
    url: EmptyOrUrl = Field(
        default="http://localhost:8000", description="Mediafusion URL"
    )
    timeout: int = Field(default=30, ge=1, description="Request timeout in seconds")
    ratelimit: bool = Field(default=True, description="Enable rate limiting")


class OrionoidConfigParametersDict(Observable):
    video3d: bool = Field(default=False, description="Include 3D video results")
    videoquality: str = Field(default="sd_hd8k", description="Video quality filter")
    limitcount: int = Field(default=5, ge=1, description="Maximum number of results")


class OrionoidConfig(Observable):
    enabled: bool = Field(default=False, description="Enable Orionoid scraper")
    api_key: str = Field(default="", description="Orionoid API key")
    cached_results_only: bool = Field(
        default=False, description="Only return cached/downloadable results"
    )
    parameters: OrionoidConfigParametersDict = Field(
        default_factory=lambda: OrionoidConfigParametersDict(),
        description="Additional Orionoid parameters",
    )
    timeout: int = Field(default=30, ge=1, description="Request timeout in seconds")
    ratelimit: bool = Field(default=True, description="Enable rate limiting")


class JackettConfig(Observable):
    enabled: bool = Field(default=False, description="Enable Jackett scraper")
    url: EmptyOrUrl = Field(default="http://localhost:9117", description="Jackett URL")
    api_key: str = Field(default="", description="Jackett API key")
    timeout: int = Field(default=30, ge=1, description="Request timeout in seconds")
    ratelimit: bool = Field(default=True, description="Enable rate limiting")


class ProwlarrConfig(Observable):
    enabled: bool = Field(default=False, description="Enable Prowlarr scraper")
    url: EmptyOrUrl = Field(default="http://localhost:9696", description="Prowlarr URL")
    api_key: str = Field(default="", description="Prowlarr API key")
    timeout: int = Field(default=30, ge=1, description="Request timeout in seconds")
    ratelimit: bool = Field(default=True, description="Enable rate limiting")
    limiter_seconds: int = Field(
        default=60, ge=1, description="Rate limiter cooldown in seconds"
    )


class RarbgConfig(Observable):
    enabled: bool = Field(default=False, description="Enable RARBG scraper")
    url: EmptyOrUrl = Field(default="https://therarbg.to", description="RARBG URL")
    timeout: int = Field(default=30, ge=1, description="Request timeout in seconds")
    ratelimit: bool = Field(default=True, description="Enable rate limiting")


class ScraperModel(Observable):
    after_2: float = Field(
        default=2, description="Hours to wait after 2 failed scrapes"
    )
    after_5: float = Field(
        default=6, description="Hours to wait after 5 failed scrapes"
    )
    after_10: float = Field(
        default=24, description="Hours to wait after 10 failed scrapes"
    )
    enable_aliases: bool = Field(
        default=True, description="Enable title aliases for better matching"
    )
    bucket_limit: int = Field(
        default=5, ge=0, le=20, description="Maximum results per quality bucket"
    )
    max_failed_attempts: int = Field(
        default=0,
        ge=0,
        le=10,
        description="Maximum failed scrape attempts before giving up",
    )
    dubbed_anime_only: bool = Field(
        default=False, description="Only scrape dubbed anime content"
    )
    torrentio: TorrentioConfig = Field(
        default_factory=lambda: TorrentioConfig(), description="Torrentio configuration"
    )
    jackett: JackettConfig = Field(
        default_factory=lambda: JackettConfig(), description="Jackett configuration"
    )
    prowlarr: ProwlarrConfig = Field(
        default_factory=lambda: ProwlarrConfig(), description="Prowlarr configuration"
    )
    orionoid: OrionoidConfig = Field(
        default_factory=lambda: OrionoidConfig(), description="Orionoid configuration"
    )
    mediafusion: MediafusionConfig = Field(
        default_factory=lambda: MediafusionConfig(),
        description="Mediafusion configuration",
    )
    zilean: ZileanConfig = Field(
        default_factory=lambda: ZileanConfig(), description="Zilean configuration"
    )
    comet: CometConfig = Field(
        default_factory=lambda: CometConfig(), description="Comet configuration"
    )
    rarbg: RarbgConfig = Field(
        default_factory=lambda: RarbgConfig(), description="RARBG configuration"
    )


# Version Ranking Model (set application defaults here!)


class RTNSettingsModel(SettingsModel, Observable): ...


# Application Settings


class IndexerModel(Observable):
    update_interval: int = Field(
        default=60 * 60,
        ge=1,
        description="Indexer update interval in seconds (1 hour default)",
    )


class DatabaseModel(Observable):
    host: PostgresDsn = Field(
        default_factory=lambda: PostgresDsn(
            "postgresql+psycopg2://postgres:postgres@localhost/riven"
        ),
        description="Database connection string",
    )


class NotificationsModel(Observable):
    enabled: bool = Field(default=False, description="Enable notifications")
    on_item_type: List[str] = Field(
        default_factory=lambda: ["movie", "show", "season", "episode"],
        description="Item types to send notifications for",
    )
    service_urls: List[str] = Field(
        default_factory=list,
        description="Notification service URLs (e.g., Discord webhooks)",
    )


class SubtitleProviderConfig(Observable):
    enabled: bool = Field(default=False, description="Enable this subtitle provider")


class SubtitleProvidersDict(Observable):
    opensubtitles: SubtitleProviderConfig = Field(
        default_factory=lambda: SubtitleProviderConfig(),
        description="OpenSubtitles provider configuration",
    )


class SubtitleConfig(Observable):
    enabled: bool = Field(default=False, description="Enable subtitle downloading")
    languages: List[str] = Field(
        default_factory=lambda: ["eng"],
        description="Subtitle languages to download (ISO 639-2 codes)",
    )
    providers: SubtitleProvidersDict = Field(
        default_factory=lambda: SubtitleProvidersDict(),
        description="Subtitle provider configurations",
    )


class PostProcessing(Observable):
    subtitle: SubtitleConfig = Field(
        default_factory=lambda: SubtitleConfig(),
        description="Subtitle post-processing configuration",
    )


class LoggingModel(Observable):
    enabled: bool = Field(default=True, description="Enable file logging")
    retention_hours: int = Field(
        default=24, description="Log retention period in hours"
    )
    rotation_mb: int = Field(default=10, description="Log file rotation size in MB")
    compression: Literal["zip", "gz", "bz2", "xz", ""] = Field(
        default="", description="Log compression format (empty for no compression)"
    )


class AppModel(Observable):
    version: str = Field(default_factory=get_version, description="Application version")
    api_key: str = Field(default="", description="API key for Riven API access")
    log_level: Literal["TRACE", "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = (
        Field(default="INFO", description="Logging level")
    )
    tracemalloc: bool = Field(
        default=False, description="Enable Python memory tracking (debug)"
    )
    filesystem: FilesystemModel = Field(
        default_factory=lambda: FilesystemModel(),
        description="Filesystem configuration",
    )
    updaters: UpdatersModel = Field(
        default_factory=lambda: UpdatersModel(),
        description="Library updaters configuration",
    )
    downloaders: DownloadersModel = Field(
        default_factory=lambda: DownloadersModel(),
        description="Downloader services configuration",
    )
    content: ContentModel = Field(
        default_factory=lambda: ContentModel(),
        description="Content services configuration",
    )
    scraping: ScraperModel = Field(
        default_factory=lambda: ScraperModel(), description="Scraper configuration"
    )
    ranking: RTNSettingsModel = Field(
        default_factory=lambda: RTNSettingsModel(),
        description="Result ranking configuration",
    )
    indexer: IndexerModel = Field(
        default_factory=lambda: IndexerModel(), description="Indexer configuration"
    )
    database: DatabaseModel = Field(
        default_factory=lambda: DatabaseModel(), description="Database configuration"
    )
    notifications: NotificationsModel = Field(
        default_factory=lambda: NotificationsModel(),
        description="Notifications configuration",
    )
    post_processing: PostProcessing = Field(
        default_factory=lambda: PostProcessing(),
        description="Post-processing configuration",
    )
    logging: LoggingModel = Field(
        default_factory=lambda: LoggingModel(), description="Logging configuration"
    )

    @field_validator("log_level", mode="before")
    def check_debug(cls, v):
        if v == True:
            return "DEBUG"
        elif v == False:
            return "INFO"
        return v.upper()

    def __init__(self, **data: Any):
        current_version = get_version()
        existing_version = data.get("version", current_version)
        super().__init__(**data)
        if existing_version < current_version:
            self.version = current_version

        if self.api_key == "":
            self.api_key = generate_api_key()
