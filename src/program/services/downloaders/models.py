from datetime import datetime
from typing import Any, Literal

import regex
from pydantic import BaseModel, Field

from program.settings import settings_manager
from program.media.item import ProcessedItemType

DEFAULT_VIDEO_EXTENSIONS = ["mp4", "mkv", "avi"]
ALLOWED_VIDEO_EXTENSIONS = [
    "mp4",
    "mkv",
    "avi",
    "mov",
    "wmv",
    "flv",
    "m4v",
    "webm",
    "mpg",
    "mpeg",
    "m2ts",
    "ts",
]

ANIME_SPECIALS_PATTERN = regex.compile(
    r"\b(OVA|NCED|NCOP|NC|OVA|ED(\d?v?\d?)|OPv?(\d+)?|SP\d+)\b", regex.IGNORECASE
)

VALID_VIDEO_EXTENSIONS = (
    [
        ext
        for ext in settings_manager.settings.downloaders.video_extensions
        if ext in ALLOWED_VIDEO_EXTENSIONS
    ]
) or DEFAULT_VIDEO_EXTENSIONS

movie_min_filesize = settings_manager.settings.downloaders.movie_filesize_mb_min
movie_max_filesize = settings_manager.settings.downloaders.movie_filesize_mb_max
episode_min_filesize = settings_manager.settings.downloaders.episode_filesize_mb_min
episode_max_filesize = settings_manager.settings.downloaders.episode_filesize_mb_max

# constraints for filesizes, follows the format tuple(min, max)
(MOVIE_MIN_FILESIZE, MOVIE_MAX_FILESIZE) = (
    movie_min_filesize if movie_min_filesize >= 0 else 0,
    movie_max_filesize if movie_max_filesize > 0 else float("inf"),
)

(EPISODE_MIN_FILESIZE, EPISODE_MAX_FILESIZE) = (
    episode_min_filesize if episode_min_filesize >= 0 else 0,
    episode_max_filesize if episode_max_filesize > 0 else float("inf"),
)


class NotCachedException(Exception):
    """Exception raised for torrents that are not cached"""


class NoMatchingFilesException(Exception):
    """Exception raised for torrents that do not match the expected files"""


class InvalidDebridFileException(Exception):
    """Exception raised for errors creating a DebridFile"""


class BitrateLimitExceededException(InvalidDebridFileException):
    """Exception raised when a file exceeds the allowed bitrate limit"""


class DebridFile(BaseModel):
    """Represents a file from a debrid service"""

    file_id: int | None
    filename: str
    filesize: int
    download_url: str | None = None

    @classmethod
    def create(
        cls,
        filesize_bytes: int,
        filename: str,
        filetype: ProcessedItemType,
        path: str | None = None,
        file_id: int | None = None,
        limit_filesize: bool = True,
    ) -> "DebridFile":
        """Factory method to validate and create a DebridFile"""

        filename_lower = filename.lower() if filename else ""

        if "sample" in filename_lower:
            raise InvalidDebridFileException(f"Skipping sample file: '{filename}'")

        if not any(filename_lower.endswith(ext) for ext in VALID_VIDEO_EXTENSIONS):
            raise InvalidDebridFileException(f"Skipping non-video file: '{filename}'")

        if path and ANIME_SPECIALS_PATTERN.search(path):
            raise InvalidDebridFileException(f"Skipping anime special: '{path}'")

        if limit_filesize:
            filesize_mb = filesize_bytes / 1_000_000

            # Determine limits dynamically, respecting overrides if present
            if filetype == "movie":
                 min_default = settings_manager.settings.downloaders.movie_filesize_mb_min
                 max_default = settings_manager.settings.downloaders.movie_filesize_mb_max
                 min_limit = settings_manager.get_setting("min_filesize", min_default)
                 max_limit = settings_manager.get_setting("max_filesize", max_default)
            elif filetype in ["show", "season", "episode"]:
                 min_default = settings_manager.settings.downloaders.episode_filesize_mb_min
                 max_default = settings_manager.settings.downloaders.episode_filesize_mb_max
                 min_limit = settings_manager.get_setting("min_filesize", min_default)
                 max_limit = settings_manager.get_setting("max_filesize", max_default)
            else:
                 min_limit = 0
                 max_limit = float("inf")
                 
            # Ensure safe values
            min_limit = min_limit if min_limit is not None and min_limit >= 0 else 0
            max_limit = max_limit if max_limit is not None and max_limit > 0 else float("inf")

            if not (min_limit <= filesize_mb <= max_limit):
                raise InvalidDebridFileException(
                    f"Skipping {filetype} file: '{filename}' - filesize: {round(filesize_mb, 2)}MB is outside the allowed range of {min_limit}MB to {max_limit}MB"
                )

        return cls(filename=filename, filesize=filesize_bytes, file_id=file_id)

    def to_dict(self) -> dict[str, Any]:
        """Convert the DebridFile to a dictionary"""

        return {
            "filename": self.filename,
            "filesize": self.filesize,
            "file_id": self.file_id,
            "download_url": self.download_url,
        }


class TorrentContainer(BaseModel):
    """Represents a collection of files from an infohash from a debrid service"""

    infohash: str
    files: list[DebridFile] = Field(default_factory=list[DebridFile])
    torrent_id: int | str | None = None  # Cached torrent_id to avoid re-adding
    torrent_info: "TorrentInfo | None" = None  # Cached info to avoid re-fetching

    @property
    def cached(self) -> bool:
        """Check if the torrent is cached"""

        return len(self.files) > 0

    @property
    def file_ids(self) -> list[int]:
        """Get the file ids of the cached files"""

        return [file.file_id for file in self.files if file.file_id is not None]

    def to_dict(self) -> dict[str, Any]:
        """Convert the TorrentContainer to a dictionary including the infohash"""

        return {
            "infohash": self.infohash,
            "files": {file.file_id: file.to_dict() for file in self.files if file},
        }


class TorrentFile(BaseModel):
    """Represents a file within a torrent"""

    id: int
    path: str
    bytes: int
    selected: Literal[0, 1]
    download_url: str

    @property
    def filename(self) -> str:
        """Extract the filename from the path"""

        return self.path.split("/")[-1]


class TorrentInfo(BaseModel):
    """Torrent information from a debrid service"""

    id: int | str
    name: str
    status: str | None = None
    infohash: str | None = None
    progress: float | None = None
    bytes: int | None = None
    created_at: datetime | None = None
    expires_at: datetime | None = None
    completed_at: datetime | None = None
    alternative_filename: str | None = None

    # Real-Debrid only
    files: dict[int, TorrentFile] = Field(default_factory=dict[int, TorrentFile])

    # Real-Debrid download links
    links: list[str] = Field(default_factory=list)

    @property
    def size_mb(self) -> float:
        """Convert bytes to megabytes"""

        return self.bytes / 1_000_000 if self.bytes else 0

    @property
    def cached(self) -> bool:
        """Check if the torrent is cached"""

        return len(self.files) > 0


class DownloadedTorrent(BaseModel):
    """Represents the result of a download operation"""

    id: int | str
    infohash: str
    container: TorrentContainer
    info: TorrentInfo


class UserInfo(BaseModel):
    """Normalized user information across different debrid services"""

    service: Literal["realdebrid", "debridlink", "alldebrid"]
    username: str | None = None
    email: str | None = None
    user_id: int | str
    premium_status: Literal["free", "premium"]
    premium_expires_at: datetime | None = None
    premium_days_left: int | None = None

    # Service-specific fields (optional)
    points: int | None = None  # Real-Debrid
    total_downloaded_bytes: int | None = None
    cooldown_until: datetime | None = None


class UnrestrictedLink(BaseModel):
    download: str
    filename: str
    filesize: int
