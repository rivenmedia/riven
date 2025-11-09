"""Riven settings models"""

from pathlib import Path
from typing import Any, Callable, List, Literal, Annotated

from pydantic import (
    BaseModel,
    Field,
    field_validator,
    model_validator,
    BeforeValidator,
    TypeAdapter,
)
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

    _notify_observers: Callable | None = None

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
            def __enter__(self):
                pass

            def __exit__(self, exc_type, exc_value, traceback):
                pass

        return NotifyContextManager()


# Download Services


class RealDebridModel(Observable):
    enabled: bool = Field(default=False, description="Enable Real-Debrid")
    api_key: str = Field(default="", description="Real-Debrid API key")


class DebridLinkModel(Observable):
    enabled: bool = Field(default=False, description="Enable Debrid-Link")
    api_key: str = Field(default="", description="Debrid-Link API key")


class AllDebridModel(Observable):
    enabled: bool = Field(default=False, description="Enable AllDebrid")
    api_key: str = Field(default="", description="AllDebrid API key")


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
    debrid_link: DebridLinkModel = Field(
        default_factory=lambda: DebridLinkModel(),
        description="Debrid-Link downloader configuration",
    )
    all_debrid: AllDebridModel = Field(
        default_factory=lambda: AllDebridModel(),
        description="AllDebrid downloader configuration",
    )


# Filesystem Service


class LibraryProfileFilterRules(BaseModel):
    """Filter rules for library profile matching (metadata-only)"""

    content_types: List[str] | None = Field(
        default=None,
        description="Media types to include (movie, show). None/omit = all types",
    )
    genres: List[str] | None = Field(
        default=None,
        description="Genres to include/exclude. Prefix with '!' to exclude. "
        "Examples: ['action', 'adventure'] = include these genres, "
        "['action', '!horror'] = include action but exclude horror. "
        "None/omit = no genre filter",
    )
    exclude_genres: List[str] | None = Field(
        default=None,
        description="DEPRECATED: Use genres with '!' prefix instead. "
        "This field is kept for backward compatibility and will be auto-migrated.",
    )
    min_year: int | None = Field(
        default=None,
        ge=1900,
        description="Minimum release year. None/omit = no minimum",
    )
    max_year: int | None = Field(
        default=None,
        ge=1900,
        description="Maximum release year. None/omit = no maximum",
    )
    is_anime: bool | None = Field(
        default=None, description="Filter by anime flag. None/omit = no anime filter"
    )
    networks: List[str] | None = Field(
        default=None,
        description="TV networks to include/exclude. Prefix with '!' to exclude. "
        "Examples: ['HBO', 'Netflix'], ['HBO', '!Fox']. None/omit = no network filter",
    )
    countries: List[str] | None = Field(
        default=None,
        description="Countries to include/exclude. Prefix with '!' to exclude. "
        "Examples: ['US', 'GB'], ['US', '!CN']. None/omit = no country filter",
    )
    languages: List[str] | None = Field(
        default=None,
        description="Languages to include/exclude. Prefix with '!' to exclude. "
        "Examples: ['en', 'es'], ['en', '!zh']. None/omit = no language filter",
    )
    min_rating: float | None = Field(
        default=None,
        ge=0.0,
        le=10.0,
        description="Minimum rating (0-10 scale). None/omit = no minimum",
    )
    max_rating: float | None = Field(
        default=None,
        ge=0.0,
        le=10.0,
        description="Maximum rating (0-10 scale). None/omit = no maximum",
    )
    content_ratings: List[str] | None = Field(
        default=None,
        description="Content ratings to include/exclude. Prefix with '!' to exclude. "
        "Examples: ['PG', 'PG-13'], ['PG', '!R']. "
        "Common ratings: G, PG, PG-13, R, NC-17, TV-Y, TV-PG, TV-14, TV-MA. "
        "None/omit = no rating filter",
    )

    @model_validator(mode="after")
    def migrate_exclude_genres(self):
        """Auto-migrate exclude_genres to genres with '!' prefix."""
        if self.exclude_genres:
            # Merge exclude_genres into genres with '!' prefix
            self.genres = self.genres or []
            for genre in self.exclude_genres:
                exclusion = f"!{genre}" if not genre.startswith("!") else genre
                if exclusion not in self.genres:
                    self.genres.append(exclusion)
            # Clear deprecated field
            self.exclude_genres = None
        return self


class LibraryProfile(BaseModel):
    """Library profile configuration for organizing media into different libraries"""

    name: str = Field(description="Human-readable profile name")
    library_path: str = Field(
        description="VFS path prefix for this profile (e.g., '/kids', '/anime')"
    )
    enabled: bool = Field(default=True, description="Enable this profile")
    filter_rules: LibraryProfileFilterRules = Field(
        default_factory=lambda: LibraryProfileFilterRules(),
        description="Metadata filter rules for matching items",
    )

    @field_validator("library_path")
    def validate_library_path(cls, v):
        """Validate library_path format"""
        if not v:
            raise ValueError("library_path cannot be empty")
        if not v.startswith("/"):
            raise ValueError("library_path must start with '/'")
        if v == "/default":
            raise ValueError(
                "library_path cannot be '/default' (reserved for default path)"
            )
        # Check for valid characters (alphanumeric, dash, underscore, slash)
        import re

        if not re.match(r"^/[a-zA-Z0-9_\-/]+$", v):
            raise ValueError(
                "library_path must contain only alphanumeric characters, dashes, underscores, and slashes"
            )
        return v


class FilesystemModel(Observable):
    mount_path: Path = Field(
        default=Path("/path/to/riven/mount"),
        description="Path where Riven will mount the virtual filesystem",
    )

    library_profiles: dict[str, LibraryProfile] = Field(
        default_factory=lambda: {
            "anime": LibraryProfile(
                name="Anime",
                library_path="/anime",
                enabled=True,
                filter_rules=LibraryProfileFilterRules(is_anime=True),
            ),
            # Example profile (disabled by default) - enable or customize as needed
            # These demonstrate all available filter options
            "example_kids": LibraryProfile(
                name="Kids & Family Content",
                library_path="/kids",
                enabled=False,
                filter_rules=LibraryProfileFilterRules(
                    content_types=["movie", "show"],
                    genres=["animation", "family", "!horror"],
                    # US Movie Ratings: G, PG, PG-13, R, NC-17, NR (Not Rated), Unrated
                    # US TV Ratings: TV-Y, TV-Y7, TV-G, TV-PG, TV-14, TV-MA
                    content_ratings=["G", "PG", "TV-Y", "TV-Y7", "TV-G", "TV-PG"],
                    max_rating=7.5,
                ),
            ),
        },
        description=(
            "Library profiles for organizing media into different libraries based on metadata. "
            "An example profile is provided (disabled by default) - enable them or create your own. "
            "Each profile filters media by metadata (genres, ratings, etc.) and creates VFS paths. "
            "Media appears in all matching profile paths. Use '!' prefix in filter lists to exclude values "
            "(e.g., genres: ['action', '!horror'] = action movies but not horror)."
        ),
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

    # VFS Naming Templates
    movie_dir_template: str = Field(
        default="{title} ({year}) {{tmdb-{tmdb_id}}}",
        description=(
            "Template for movie directory names. "
            "Available variables: title, year, tmdb_id, imdb_id, resolution, codec, hdr, audio, quality, "
            "is_remux, is_proper, is_repack, is_extended, is_directors_cut, container. "
            "Example: '{title} ({year})' or '{title} ({year}) [{resolution}]'"
        ),
    )

    movie_file_template: str = Field(
        default="{title} ({year})",
        description=(
            "Template for movie file names (without extension). "
            "Available variables: title, year, tmdb_id, imdb_id, resolution, codec, hdr, audio, quality, "
            "remux, proper, repack, extended, directors_cut, edition (string flags, empty if false). "
            "Example: '{title} ({year})' or '{title} ({year}) {edition} [{resolution}] {remux}'"
        ),
    )

    show_dir_template: str = Field(
        default="{title} ({year}) {{tvdb-{tvdb_id}}}",
        description=(
            "Template for show directory names. "
            "Available variables: title, year, tvdb_id, imdb_id. "
            "Example: '{title} ({year})' or '{title} ({year}) {{tvdb-{tvdb_id}}}'"
        ),
    )

    season_dir_template: str = Field(
        default="Season {season:02d}",
        description=(
            "Template for season directory names. "
            "Available variables: season (number), show (parent show data with [title], [year], [tvdb_id], [imdb_id]). "
            "Example: 'Season {season:02d}' or 'S{season:02d}' or '{show[title]} - Season {season}'"
        ),
    )

    episode_file_template: str = Field(
        default="{show[title]} - s{season:02d}e{episode:02d}",
        description=(
            "Template for episode file names (without extension). "
            "Available variables: title, season, episode, "
            "show (parent show data with [title], [year], [tvdb_id], [imdb_id]), "
            "resolution, codec, hdr, audio, quality, remux, proper, repack, extended, directors_cut, edition. "
            "Example: '{show[title]} - s{season:02d}e{episode:02d}' or 'S{season:02d}E{episode:02d} - {title}'. "
            "Multi-episode files automatically use range format (e.g., e01-05) based on episode number formatting."
        ),
    )

    @field_validator("library_profiles")
    def validate_library_profiles(cls, v):
        """Validate library profile keys and paths"""
        import re

        for key in v.keys():
            # Profile keys must be lowercase alphanumeric with underscores
            if not re.match(r"^[a-z0-9_]+$", key):
                raise ValueError(
                    f"Profile key '{key}' must be lowercase alphanumeric with underscores only"
                )
            if key == "default":
                raise ValueError("Profile key 'default' is reserved")

        # Check for duplicate library_path values among enabled profiles
        # Disabled profiles are allowed to have duplicate paths since they're not active
        enabled_paths = {}
        for key, profile in v.items():
            if profile.enabled:
                # Normalize path for comparison (strip trailing slashes, ensure leading slash)
                normalized_path = profile.library_path.rstrip("/")
                if not normalized_path.startswith("/"):
                    normalized_path = f"/{normalized_path}"

                # Check if this path is already used by another enabled profile
                if normalized_path in enabled_paths:
                    raise ValueError(
                        f"Duplicate library_path '{profile.library_path}' found in profiles "
                        f"'{enabled_paths[normalized_path]}' and '{key}'. "
                        f"Each enabled library profile must have a unique library_path."
                    )

                # Check for reserved paths
                if normalized_path in ["/movies", "/shows"]:
                    raise ValueError(
                        f"library_path '{profile.library_path}' in profile '{key}' is reserved. "
                        f"The paths '/movies' and '/shows' are reserved for base directories."
                    )

                enabled_paths[normalized_path] = key

        return v

    @field_validator(
        "movie_dir_template",
        "movie_file_template",
        "show_dir_template",
        "season_dir_template",
        "episode_file_template",
    )
    def validate_naming_template(cls, v: str, info) -> str:
        """Validate that naming template string is syntactically valid."""
        from string import Formatter

        class SafeFormatter(Formatter):
            """Formatter that handles missing keys gracefully for validation."""

            def get_value(self, key, args, kwargs):
                if isinstance(key, str):
                    # Handle nested access: show[title]
                    if "[" in key and "]" in key:
                        parts = key.replace("]", "").split("[")
                        value = kwargs.get(parts[0], {})
                        for part in parts[1:]:
                            if isinstance(value, dict):
                                value = value.get(part, "")
                            elif isinstance(value, list):
                                try:
                                    # Handle negative indices like [-1]
                                    value = value[int(part)]
                                except (ValueError, IndexError):
                                    value = ""
                            else:
                                value = ""
                        return value or ""
                    # Simple key access
                    return kwargs.get(key, "")
                return super().get_value(key, args, kwargs)

            def format_field(self, value, format_spec):
                if value is None or value == "":
                    return ""
                return super().format_field(value, format_spec)

        try:
            # Test template with comprehensive dummy data
            formatter = SafeFormatter()
            test_data = {
                "title": "Test Title",
                "year": 2024,
                "season": 1,
                "episode": 1,
                "show": {
                    "title": "Test Show",
                    "year": 2024,
                    "tvdb_id": "12345",
                    "imdb_id": "tt1234567",
                },
                "season_obj": {"number": 1, "title": "Season 1"},
                "tmdb_id": "12345",
                "tvdb_id": "12345",
                "imdb_id": "tt1234567",
                "resolution": "1080p",
                "codec": "h264",
                "hdr": ["HDR10"],
                "audio": "aac",
                "quality": "BluRay",
                "container": "mkv",
                "remux": "REMUX",
                "proper": "PROPER",
                "repack": "REPACK",
                "extended": "Extended",
                "directors_cut": "Director's Cut",
                "edition": "Extended Director's Cut",
            }
            formatter.format(v, **test_data)
            return v
        except Exception as e:
            raise ValueError(f"Invalid naming template syntax: {e}")


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
    retries: int = Field(
        default=1, ge=0, description="Number of retries for failed requests"
    )
    ratelimit: bool = Field(default=True, description="Enable rate limiting")
    proxy_url: EmptyOrUrl = Field(
        default="", description="Proxy URL for Torrentio requests"
    )


class CometConfig(Observable):
    enabled: bool = Field(default=False, description="Enable Comet scraper")
    url: EmptyOrUrl = Field(default="http://localhost:8000", description="Comet URL")
    timeout: int = Field(default=30, ge=1, description="Request timeout in seconds")
    retries: int = Field(
        default=1, ge=0, description="Number of retries for failed requests"
    )
    ratelimit: bool = Field(default=True, description="Enable rate limiting")


class ZileanConfig(Observable):
    enabled: bool = Field(default=False, description="Enable Zilean scraper")
    url: EmptyOrUrl = Field(default="http://localhost:8181", description="Zilean URL")
    timeout: int = Field(default=30, ge=1, description="Request timeout in seconds")
    retries: int = Field(
        default=1, ge=0, description="Number of retries for failed requests"
    )
    ratelimit: bool = Field(default=True, description="Enable rate limiting")


class MediafusionConfig(Observable):
    enabled: bool = Field(default=False, description="Enable Mediafusion scraper")
    url: EmptyOrUrl = Field(
        default="http://localhost:8000", description="Mediafusion URL"
    )
    timeout: int = Field(default=30, ge=1, description="Request timeout in seconds")
    retries: int = Field(
        default=1, ge=0, description="Number of retries for failed requests"
    )
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
    retries: int = Field(
        default=1, ge=0, description="Number of retries for failed requests"
    )
    ratelimit: bool = Field(default=True, description="Enable rate limiting")


class JackettConfig(Observable):
    enabled: bool = Field(default=False, description="Enable Jackett scraper")
    url: EmptyOrUrl = Field(default="http://localhost:9117", description="Jackett URL")
    api_key: str = Field(default="", description="Jackett API key")
    timeout: int = Field(default=30, ge=1, description="Request timeout in seconds")
    retries: int = Field(
        default=1, ge=0, description="Number of retries for failed requests"
    )
    infohash_fetch_timeout: int = Field(
        default=30,
        ge=1,
        description="Timeout in seconds for parallel infohash fetching from URLs",
    )
    ratelimit: bool = Field(default=True, description="Enable rate limiting")


class ProwlarrConfig(Observable):
    enabled: bool = Field(default=False, description="Enable Prowlarr scraper")
    url: EmptyOrUrl = Field(default="http://localhost:9696", description="Prowlarr URL")
    api_key: str = Field(default="", description="Prowlarr API key")
    timeout: int = Field(default=30, ge=1, description="Request timeout in seconds")
    retries: int = Field(
        default=1, ge=0, description="Number of retries for failed requests"
    )
    infohash_fetch_timeout: int = Field(
        default=30,
        ge=1,
        description="Timeout in seconds for parallel infohash fetching from URLs",
    )
    ratelimit: bool = Field(default=True, description="Enable rate limiting")
    limiter_seconds: int = Field(
        default=60, ge=1, description="Rate limiter cooldown in seconds"
    )


class RarbgConfig(Observable):
    enabled: bool = Field(default=False, description="Enable RARBG scraper")
    url: EmptyOrUrl = Field(default="https://therarbg.to", description="RARBG URL")
    timeout: int = Field(default=30, ge=1, description="Request timeout in seconds")
    retries: int = Field(
        default=1, ge=0, description="Number of retries for failed requests"
    )
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
    schedule_offset_minutes: int = Field(
        default=30,
        ge=0,
        description="Offset in minutes after aired_at time to schedule scraping for episodes and movies (30 minutes default)",
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
    clean_interval: int = Field(
        default=60 * 60, description="Log cleanup interval in seconds (1 hour default)"
    )
    retention_hours: int = Field(
        default=24, description="Log retention period in hours"
    )
    rotation_mb: int = Field(default=10, description="Log file rotation size in MB")
    compression: Literal["zip", "gz", "bz2", "xz", "disabled"] = Field(
        default="disabled",
        description="Log compression format (empty for no compression)",
    )

    @field_validator("compression", mode="before")
    def check_compression(cls, v):
        if v == "" or not v:
            return "disabled"
        return v


class AppModel(Observable):
    version: str = Field(default_factory=get_version, description="Application version")
    api_key: str = Field(default="", description="API key for Riven API access")
    log_level: Literal["TRACE", "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = (
        Field(default="INFO", description="Logging level")
    )
    retry_interval: int = Field(
        default=60 * 60 * 24,
        ge=0,
        description="Interval in seconds to retry failed library items (24 hours default, 0 to disable)",
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
