"""Riven settings models"""

from pathlib import Path
from typing import Any, Callable, List

from pydantic import BaseModel, Field, field_validator
from RTN.models import SettingsModel

from program.settings.migratable import MigratableBaseModel
from program.utils import generate_api_key, get_version

deprecation_warning = (
    "This has been deprecated and will be removed in a future version."
)


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


class TorBoxModel(Observable):
    enabled: bool = False
    api_key: str = ""


class DownloadersModel(Observable):
    video_extensions: List[str] = ["mp4", "mkv", "avi"]
    movie_filesize_mb_min: int = 700
    movie_filesize_mb_max: int = -1  # -1 is no limit
    episode_filesize_mb_min: int = 100
    episode_filesize_mb_max: int = -1  # -1 is no limit
    proxy_url: str = ""
    real_debrid: RealDebridModel = RealDebridModel()
    all_debrid: AllDebridModel = AllDebridModel()
    torbox: TorBoxModel = TorBoxModel()


# Filesystem Service


class FilesystemModel(Observable):
    mount_path: Path = Path(".data/mount")
    library_path: Path = Path("/mount")
    debug_fuse: bool = False
    separate_anime_dirs: bool = False
    
    # VFS Performance Settings
    readahead_buffer_mb: int = Field(default=4, ge=1, le=512, description="Readahead buffer size in MB for streaming optimization")
    url_cache_ttl_minutes: int = Field(default=15, ge=1, le=120, description="URL cache TTL in minutes")
    
    # HTTP Request Settings
    http_timeout_seconds: int = Field(default=30, ge=10, le=300, description="HTTP request timeout in seconds")
    http_connect_timeout_seconds: int = Field(default=5, ge=1, le=30, description="HTTP connection timeout in seconds")
    http_low_speed_limit_kbps: int = Field(default=10, ge=1, le=10240, description="Minimum transfer speed in KB/s before timeout")
    http_low_speed_time_seconds: int = Field(default=15, ge=5, le=120, description="Time in seconds to maintain minimum speed")
    
    # FUSE Cache Settings
    fuse_entry_timeout_seconds: int = Field(default=300, ge=1, le=3600, description="FUSE entry cache timeout in seconds")
    fuse_attr_timeout_seconds: int = Field(default=300, ge=1, le=3600, description="FUSE attribute cache timeout in seconds")
    
    # Advanced Settings
    enable_request_serialization: bool = Field(default=True, description="Serialize HTTP requests per file path")
    enable_http_keepalive: bool = Field(default=True, description="Enable HTTP keep-alive connections")
    max_concurrent_requests_per_file: int = Field(default=1, ge=1, le=10, description="Maximum concurrent HTTP requests per file")
    
    # Retry and Error Handling
    http_max_retries: int = Field(default=2, ge=1, le=10, description="Maximum HTTP request retry attempts")
    retry_delay_seconds: float = Field(default=1.0, ge=0.1, le=30.0, description="Delay between retry attempts in seconds")
    enable_exponential_backoff: bool = Field(default=True, description="Use exponential backoff for retries")
    
    # FUSE Mount Options
    enable_allow_other: bool = Field(default=False, description="Allow other users to access the mount")
    enable_auto_unmount: bool = Field(default=True, description="Automatically unmount on exit")
    fuse_max_background: int = Field(default=12, ge=1, le=256, description="Maximum FUSE background requests")
    fuse_congestion_threshold: int = Field(default=10, ge=1, le=128, description="FUSE congestion threshold")
    
    # Buffer Management
    enable_adaptive_buffering: bool = Field(default=False, description="Dynamically adjust buffer size based on bitrate")
    min_buffer_mb: int = Field(default=1, ge=1, le=256, description="Minimum buffer size in MB for adaptive buffering")
    max_buffer_mb: int = Field(default=128, ge=4, le=2048, description="Maximum buffer size in MB for adaptive buffering")
    buffer_prefetch_factor: float = Field(default=1.5, ge=1.0, le=5.0, description="Prefetch multiplier for sequential reads")
    
    # Disk Cache (rclone-inspired)
    enable_disk_cache: bool = Field(default=False, description="Enable persistent disk cache like rclone --vfs-cache-mode full")
    disk_cache_path: Path = Field(default=Path(".data/vfs-cache"), description="Disk cache directory path")
    disk_cache_max_size_gb: int = Field(default=50, ge=1, le=1000, description="Maximum disk cache size in GB")
    disk_cache_max_age_hours: int = Field(default=24, ge=1, le=168, description="Maximum cache age in hours")
    disk_cache_cleanup_interval_minutes: int = Field(default=60, ge=5, le=1440, description="Cache cleanup interval in minutes")
    
    # Dynamic Chunking (rclone-inspired)
    enable_dynamic_chunking: bool = Field(default=False, description="Enable dynamic chunk sizing like rclone")
    min_chunk_size_mb: int = Field(default=1, ge=1, le=64, description="Minimum chunk size in MB")
    max_chunk_size_mb: int = Field(default=256, ge=64, le=2048, description="Maximum chunk size in MB (like --vfs-read-chunk-size-limit)")
    chunk_size_multiplier: float = Field(default=2.0, ge=1.0, le=10.0, description="Chunk size growth multiplier")
    
    # Fast Fingerprinting (rclone-inspired)
    enable_fast_fingerprint: bool = Field(default=False, description="Enable fast file fingerprinting like rclone --vfs-fast-fingerprint")
    fingerprint_cache_seconds: int = Field(default=300, ge=30, le=3600, description="File fingerprint cache duration")
    
    # Advanced Prefetching
    enable_predictive_prefetch: bool = Field(default=False, description="Enable predictive prefetching based on access patterns")
    prefetch_window_seconds: int = Field(default=300, ge=60, le=3600, description="Prefetch window for sequential access")
    access_pattern_learning: bool = Field(default=False, description="Learn and adapt to access patterns")
    
    # Cache Polling (rclone-inspired)
    cache_poll_interval_seconds: int = Field(default=15, ge=5, le=300, description="Cache refresh interval like rclone --poll-interval")
    enable_background_cache_refresh: bool = Field(default=False, description="Refresh cache in background")
    
    # Extreme Performance Optimizations
    enable_zero_copy_io: bool = Field(default=False, description="Enable zero-copy I/O operations for maximum throughput")
    enable_memory_mapped_cache: bool = Field(default=False, description="Use memory-mapped files for cache (faster than disk I/O)")
    tcp_no_delay: bool = Field(default=True, description="Disable Nagle's algorithm for lower latency")
    tcp_keep_alive: bool = Field(default=True, description="Enable TCP keep-alive for persistent connections")
    socket_buffer_size_kb: int = Field(default=1024, ge=64, le=8192, description="TCP socket buffer size in KB")
    
    # Aggressive Caching
    enable_aggressive_readahead: bool = Field(default=False, description="Extremely aggressive readahead beyond normal prefetching")
    aggressive_readahead_mb: int = Field(default=1024, ge=256, le=4096, description="Aggressive readahead buffer size in MB")
    enable_speculative_prefetch: bool = Field(default=False, description="Speculatively prefetch likely-to-be-accessed data")
    
    # Low-Level Optimizations
    enable_io_uring: bool = Field(default=False, description="Use io_uring for async I/O (Linux only, experimental)")
    enable_direct_io: bool = Field(default=False, description="Bypass OS page cache for direct I/O")
    thread_pool_size: int = Field(default=16, ge=4, le=64, description="Thread pool size for parallel operations")
    
    # Network Optimizations
    enable_tcp_fast_open: bool = Field(default=False, description="Enable TCP Fast Open for reduced latency")
    enable_http3_quic: bool = Field(default=False, description="Enable HTTP/3 over QUIC (experimental)")
    connection_reuse_timeout_seconds: int = Field(default=300, ge=60, le=3600, description="How long to keep connections alive")
    
    # Memory Optimizations
    enable_huge_pages: bool = Field(default=False, description="Use huge pages for better memory performance")
    memory_pool_size_mb: int = Field(default=512, ge=128, le=2048, description="Pre-allocated memory pool size")
    enable_buffer_recycling: bool = Field(default=True, description="Recycle buffers to reduce GC pressure")
    
    # Connection Pool Settings
    max_connections_per_host: int = Field(default=10, ge=1, le=50, description="Maximum HTTP connections per host")
    connection_pool_timeout_seconds: int = Field(default=60, ge=10, le=300, description="Connection pool timeout in seconds")
    enable_http2: bool = Field(default=False, description="Enable HTTP/2 support (experimental)")
    
    # Monitoring and Logging
    enable_performance_metrics: bool = Field(default=False, description="Enable VFS performance metrics collection")
    log_slow_requests_threshold_seconds: float = Field(default=5.0, ge=0.5, le=60.0, description="Log requests slower than this threshold")
    enable_bandwidth_monitoring: bool = Field(default=False, description="Monitor and log bandwidth usage")
    
    # File Handle Management
    max_open_files: int = Field(default=1000, ge=100, le=10000, description="Maximum number of open file handles")
    file_handle_timeout_seconds: int = Field(default=300, ge=60, le=3600, description="Timeout for idle file handles")
    enable_file_handle_pooling: bool = Field(default=True, description="Reuse file handles when possible")
    
    @field_validator("readahead_buffer_mb")
    def validate_readahead_buffer(cls, v):
        if v < 1:
            raise ValueError("readahead_buffer_mb must be at least 1 MB")
        if v > 512:
            raise ValueError("readahead_buffer_mb cannot exceed 512 MB")
        return v
    
    @field_validator("max_buffer_mb")
    def validate_max_buffer(cls, v, info):
        min_buffer = info.data.get('min_buffer_mb', 1)
        if v < min_buffer:
            raise ValueError(f"max_buffer_mb ({v}) must be >= min_buffer_mb ({min_buffer})")
        return v

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
    proxy_url: str = ""

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
    proxy_url: str = ""


class CometConfig(Observable):
    enabled: bool = False
    url: str = "http://localhost:8000"
    timeout: int = 30
    ratelimit: bool = True


class ZileanConfig(Observable):
    enabled: bool = False
    url: str = "http://localhost:8181"
    timeout: int = 30
    ratelimit: bool = True


class MediafusionConfig(Observable):
    enabled: bool = False
    url: str = "http://localhost:8000"
    timeout: int = 30
    ratelimit: bool = True


class OrionoidConfig(Observable):
    enabled: bool = False
    api_key: str = ""
    cached_results_only: bool = False
    parameters: dict[str, Any] = {
        "video3d": False,
        "videoquality": "sd_hd8k",
        "limitcount": 5,
    }
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


class RarbgConfig(Observable):
    enabled: bool = False
    url: str = "https://therarbg.to"
    timeout: int = 30
    ratelimit: bool = True


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
    jackett: JackettConfig = JackettConfig()
    prowlarr: ProwlarrConfig = ProwlarrConfig()
    orionoid: OrionoidConfig = OrionoidConfig()
    mediafusion: MediafusionConfig = MediafusionConfig()
    zilean: ZileanConfig = ZileanConfig()
    comet: CometConfig = CometConfig()
    rarbg: RarbgConfig = RarbgConfig()


# Version Ranking Model (set application defaults here!)


class RTNSettingsModel(SettingsModel, Observable): ...


# Application Settings


class IndexerModel(Observable):
    update_interval: int = 60 * 60


class DatabaseModel(Observable):
    host: str = "postgresql+psycopg2://postgres:postgres@localhost/riven"


class NotificationsModel(Observable):
    enabled: bool = False
    on_item_type: List[str] = ["movie", "show", "season", "episode"]
    service_urls: List[str] = []


class SubliminalConfig(Observable):
    enabled: bool = False
    languages: List[str] = ["eng"]
    providers: dict = {
        "opensubtitles": {"enabled": False, "username": "", "password": ""},
        "opensubtitlescom": {"enabled": False, "username": "", "password": ""},
    }


class PostProcessing(Observable):
    subliminal: SubliminalConfig = SubliminalConfig()


class AppModel(Observable):
    version: str = get_version()
    api_key: str = ""
    debug: bool = True
    debug_database: bool = False
    log: bool = True
    tracemalloc: bool = False
    filesystem: FilesystemModel = FilesystemModel()
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
