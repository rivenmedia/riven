from datetime import datetime
from typing import Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Field

from program.settings.manager import settings_manager

DEFAULT_VIDEO_EXTENSIONS = ["mp4", "mkv", "avi"]
ALLOWED_VIDEO_EXTENSIONS = [
    "mp4", "mkv", "avi", "mov", "wmv", "flv",
    "m4v", "webm", "mpg","mpeg", "m2ts", "ts",
]

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

    @classmethod
    def create(
        cls,
        filename: str,
        filesize_bytes: int,
        filetype: Literal["movie", "show", "season", "episode"],
        file_id: Optional[int] = None,
        limit_filesize: bool = True
    ) -> Optional["DebridFile"]:
        """Factory method to validate and create a DebridFile"""
        filename_lower = filename.lower()

        if "sample" in filename_lower:
            raise InvalidDebridFileException(f"Skipping sample file: '{filename}'")

        if not any(filename_lower.endswith(ext) for ext in VALID_VIDEO_EXTENSIONS):
            raise InvalidDebridFileException(f"Skipping non-video file: '{filename}'")

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
            "file_id": self.file_id
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

    @property
    def filemap(self) -> Dict[int, Dict[int, DebridFile]]:
        """Return a dictionary of files by season and episode
        
        Example:
        {
            0: {  # Movie if no season or episode
                1: DebridFile(filename="path/to/movie.mkv")
            },
            1: {  # Season 1
                1: DebridFile(filename="path/to/s01e01.mkv"),  # Episode 1
                2: DebridFile(filename="path/to/s01e02.mkv")   # Episode 2
            },
            2: {  # Season 2
                1: DebridFile(filename="path/to/s02e01.mkv")   # Episode 1
            }
        }
        """
        filemap = {}
        for file in self.files:
            if file.season and file.episode:
                # if both season and episode are present,
                # we add the file to the season and episode
                if file.season not in filemap:
                    filemap[file.season] = {}
                filemap[file.season][file.episode] = file
            elif not file.season and file.episode:
                # if no season but episode is present,
                # this probably only has one season, or its anime.
                filemap[1] = file
            else:
                # if no season, we assume it's a movie
                filemap[0] = file
        return filemap


class DownloadedTorrent(BaseModel):
    """Represents the result of a download operation"""
    id: Union[int, str]
    infohash: str
    container: TorrentContainer
    info: TorrentInfo
