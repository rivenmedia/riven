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
        """
        Factory method to validate and create a DebridFile instance.
        
        This method validates the provided file attributes and constructs a DebridFile object if valid.
        It checks that the filename does not indicate a sample file, that the file has a permitted video extension,
        and, if filesize restrictions are enabled, that the file size falls within the allowed range based
        on the file type ("movie" uses FILESIZE_MOVIE_CONSTRAINT, while "show", "season", or "episode" use FILESIZE_EPISODE_CONSTRAINT).
        
        Parameters:
            filename (str): The name of the file to evaluate.
            filesize_bytes (int): The size of the file in bytes.
            filetype (Literal["movie", "show", "season", "episode"]): The type of the file which determines the applicable file size constraints.
            file_id (Optional[int], optional): An optional identifier for the file. Defaults to None.
            limit_filesize (bool, optional): Flag indicating whether to enforce file size validation. Defaults to True.
        
        Returns:
            DebridFile: A new DebridFile instance with the validated attributes.
        
        Raises:
            InvalidDebridFileException: If the filename indicates a sample file, the file extension is not among the valid video extensions,
                or the file size is outside the allowed range for the specified file type.
        """
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
        """
        Convert and return the torrent size in megabytes.
        
        This method converts the torrent's size from bytes to megabytes by dividing the `bytes` attribute by 1,000,000.
        If `bytes` is zero or not provided, the method returns 0.
        
        Returns:
            float: The torrent size in megabytes.
        """
        return self.bytes / 1_000_000 if self.bytes else 0

    @property
    def cached(self) -> bool:
        """
        Determine whether the torrent is cached.
        
        This method checks if the torrent is considered cached by verifying the presence of files.
        A torrent is deemed cached if its file collection is non-empty.
        
        Returns:
            bool: True if there is at least one file present; False otherwise.
        """
        return len(self.files) > 0

    @property
    def file_ids(self) -> List[int]:
        """
        Retrieve a list of file IDs for all cached files.
        
        This method iterates over the instance's `files` collection and extracts the `file_id` from each file object that has a valid (truthy) value. It filters out files that do not have a valid `file_id`.
        
        Returns:
            List[int]: A list of file IDs corresponding to the cached files.
        """
        return [file.file_id for file in self.files if file.file_id]

    @property
    def filemap(self) -> Dict[int, Dict[int, DebridFile]]:
        """
        Organize files into a nested dictionary by season and episode.
        
        This method iterates over the files in self.files and groups them according to their 'season' and 'episode' attributes:
          - If both 'season' and 'episode' are present, the file is added to a nested dictionary under the corresponding season (outer key) and episode (inner key).
          - If a file has an episode but no season, it is assumed to belong to season 1 and is assigned directly to key 1.
          - If neither season nor episode is provided, the file is assumed to be a movie and is assigned to key 0.
        
        Returns:
          dict: A dictionary where keys represent season numbers and values are either dictionaries mapping episode numbers to DebridFile objects or, when season/episode data is incomplete, direct DebridFile instances. For example:
              {
                  0: {  # Movie (no season or episode information)
                      1: DebridFile(filename="path/to/movie.mkv")
                  },
                  1: {  # Season 1
                      1: DebridFile(filename="path/to/s01e01.mkv"),  # Episode 1
                      2: DebridFile(filename="path/to/s01e02.mkv")     # Episode 2
                  },
                  2: {  # Season 2
                      1: DebridFile(filename="path/to/s02e01.mkv")     # Episode 1
                  }
              }
        
        Note:
          The structure of the returned dictionary may vary if a file’s season or episode attribute is missing.
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
