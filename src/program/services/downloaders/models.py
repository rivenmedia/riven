from datetime import datetime
from typing import Dict, List, Literal, Optional, Union

import regex
from pydantic import BaseModel, Field

from program.settings.manager import settings_manager

DEFAULT_VIDEO_EXTENSIONS = ["mp4", "mkv", "avi"]
ALLOWED_VIDEO_EXTENSIONS = [
    "mp4", "mkv", "avi", "mov", "wmv", "flv",
    "m4v", "webm", "mpg","mpeg", "m2ts", "ts",
]

ANIME_SPECIALS_PATTERN: regex.Pattern = regex.compile(r"\b(OVA|NCED|NCOP|NC|OVA|ED(\d?v?\d?)|OPv?(\d+)?|SP\d+)\b", regex.IGNORECASE)

VIDEO_EXTENSIONS: list[str] = settings_manager.settings.downloaders.video_extensions or DEFAULT_VIDEO_EXTENSIONS
VALID_VIDEO_EXTENSIONS = [ext for ext in VIDEO_EXTENSIONS if ext in ALLOWED_VIDEO_EXTENSIONS]
if not VALID_VIDEO_EXTENSIONS:
    VALID_VIDEO_EXTENSIONS = DEFAULT_VIDEO_EXTENSIONS

movie_min_filesize: int = settings_manager.settings.downloaders.movie_filesize_mb_min
movie_max_filesize: int = settings_manager.settings.downloaders.movie_filesize_mb_max
episode_min_filesize: int = settings_manager.settings.downloaders.episode_filesize_mb_min
episode_max_filesize: int = settings_manager.settings.downloaders.episode_filesize_mb_max

# constraints for filesizes, follows the format tuple(min, max)
FILESIZE_MOVIE_CONSTRAINT: tuple[int, int] = (
    movie_min_filesize if movie_min_filesize >= 0 else 0,
    movie_max_filesize if movie_max_filesize > 0 else float("inf")
)
FILESIZE_EPISODE_CONSTRAINT: tuple[int, int] = (
    episode_min_filesize if episode_min_filesize >= 0 else 0,
    episode_max_filesize if episode_max_filesize > 0 else float("inf")
)


class NotCachedException(Exception):
    """Exception raised for torrents that are not cached"""

class NoMatchingFilesException(Exception):
    """Exception raised for torrents that do not match the expected files"""

class InvalidDebridFileException(Exception):
    """Exception raised for errors creating a DebridFile"""


class DebridFile(BaseModel):
    """Represents a file from a debrid service"""
    file_id: Optional[int] = Field(default=None)
    filename: Optional[str] = Field(default=None)
    filesize: Optional[int] = Field(default=None)
    download_url: Optional[str] = Field(default=None)

    @classmethod
    def create(
        cls,
        path: str = None,
        filename: str = None,
        filesize_bytes: int = None,
        filetype: Literal["movie", "show", "season", "episode"] = None,
        file_id: Optional[int] = None,
        limit_filesize: bool = True
    ) -> Optional["DebridFile"]:
        """Factory method to validate and create a DebridFile"""
        filename_lower = filename.lower()

        if "sample" in filename_lower:
            raise InvalidDebridFileException(f"Skipping sample file: '{filename}'")

        if not any(filename_lower.endswith(ext) for ext in VALID_VIDEO_EXTENSIONS):
            raise InvalidDebridFileException(f"Skipping non-video file: '{filename}'")

        if path and ANIME_SPECIALS_PATTERN.search(path):
            raise InvalidDebridFileException(f"Skipping anime special: '{path}'")

        if limit_filesize:
            filesize_mb = filesize_bytes / 1_000_000
            if filetype == "movie":
                if not (FILESIZE_MOVIE_CONSTRAINT[0] <= filesize_mb <= FILESIZE_MOVIE_CONSTRAINT[1]):
                    raise InvalidDebridFileException(f"Skipping movie file: '{filename}' - filesize: {round(filesize_mb, 2)}MB is outside the allowed range of {FILESIZE_MOVIE_CONSTRAINT[0]}MB to {FILESIZE_MOVIE_CONSTRAINT[1]}MB")
            elif filetype in ["show", "season", "episode"]:
                if not (FILESIZE_EPISODE_CONSTRAINT[0] <= filesize_mb <= FILESIZE_EPISODE_CONSTRAINT[1]):
                    raise InvalidDebridFileException(f"Skipping episode file: '{filename}' - filesize: {round(filesize_mb, 2)}MB is outside the allowed range of {FILESIZE_EPISODE_CONSTRAINT[0]}MB to {FILESIZE_EPISODE_CONSTRAINT[1]}MB")

        return cls(filename=filename, filesize=filesize_bytes, file_id=file_id)

    def to_dict(self) -> Dict[str, Union[int, str]]:
        """Convert the DebridFile to a dictionary"""
        return {
            "filename": self.filename,
            "filesize": self.filesize,
            "file_id": self.file_id,
            "download_url": self.download_url
        }


class ParsedFileData(BaseModel):
    """Represents a parsed file from a filename"""
    item_type: Literal["movie", "show"]
    season: Optional[int] = Field(default=None)
    episodes: Optional[List[int]] = Field(default_factory=list)


class TorrentContainer(BaseModel):
    """Represents a collection of files from an infohash from a debrid service"""
    infohash: str
    files: List[DebridFile] = Field(default_factory=list)
    torrent_id: Optional[Union[int, str]] = None  # Cached torrent_id to avoid re-adding
    torrent_info: Optional['TorrentInfo'] = None  # Cached info to avoid re-fetching

    @property
    def cached(self) -> bool:
        """Check if the torrent is cached"""
        return len(self.files) > 0

    @property
    def file_ids(self) -> List[int]:
        """Get the file ids of the cached files"""
        return [file.file_id for file in self.files if file.file_id is not None]

    def to_dict(self) -> Dict[str, Union[str, Dict]]:
        """Convert the TorrentContainer to a dictionary including the infohash"""
        return {
            "infohash": self.infohash,
            "files": {file.file_id: file.to_dict() for file in self.files if file}
        }


class TorrentInfo(BaseModel):
    """Torrent information from a debrid service"""
    id: Union[int, str]
    name: str
    status: Optional[str] = None
    infohash: Optional[str] = None
    progress: Optional[float] = None
    bytes: Optional[int] = None
    created_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    alternative_filename: Optional[str] = None
    files: Dict[int, Dict[str, Union[int, str]]] = Field(default_factory=dict)  # Real-Debrid only
    links: List[str] = Field(default_factory=list)  # Real-Debrid download links

    @property
    def size_mb(self) -> float:
        """Convert bytes to megabytes"""
        return self.bytes / 1_000_000 if self.bytes else 0

    @property
    def cached(self) -> bool:
        """Check if the torrent is cached"""
        return len(self.files) > 0

    @property
    def file_ids(self) -> List[int]:
        """Get the file ids of the cached files"""
        return [file.file_id for file in self.files if file.file_id]


class DownloadedTorrent(BaseModel):
    """Represents the result of a download operation"""
    id: Union[int, str]
    infohash: str
    container: TorrentContainer
    info: TorrentInfo


class UserInfo(BaseModel):
    """Normalized user information across different debrid services"""
    service: Literal["realdebrid", "torbox"]
    username: Optional[str] = None
    email: Optional[str] = None
    user_id: Union[int, str]
    premium_status: Literal["free", "premium"]
    premium_expires_at: Optional[datetime] = None
    premium_days_left: Optional[int] = None

    # Service-specific fields (optional)
    points: Optional[int] = None  # Real-Debrid
    total_downloaded_bytes: Optional[int] = None  # TorBox
    cooldown_until: Optional[datetime] = None  # TorBox
