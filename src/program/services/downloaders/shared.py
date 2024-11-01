from RTN import parse

from abc import ABC, abstractmethod
from loguru import logger
from program.media.item import MediaItem
from program.media.state import States
from program.settings.manager import settings_manager
from typing import Optional

from datetime import datetime

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

VIDEO_EXTENSIONS = (
    settings_manager.settings.downloaders.video_extensions or DEFAULT_VIDEO_EXTENSIONS
)
VIDEO_EXTENSIONS = [ext for ext in VIDEO_EXTENSIONS if ext in ALLOWED_VIDEO_EXTENSIONS]

if not VIDEO_EXTENSIONS:
    VIDEO_EXTENSIONS = DEFAULT_VIDEO_EXTENSIONS

# Type aliases
InfoHash = str  # A torrent hash
DebridTorrentId = (
    str  # Identifier issued by the debrid service for a torrent in their cache
)


class DownloaderBase(ABC):
    """
    The abstract base class for all Downloader implementations.
    """

    @abstractmethod
    def validate():
        pass
    @abstractmethod
    def get_instant_availability():
        pass

    @abstractmethod
    def add_torrent():
        pass

    @abstractmethod
    def select_files():
        pass

    @abstractmethod
    def get_torrent_info():
        pass

    @abstractmethod
    def delete_torrent():
        pass

class FileFinder:
    """
    A class that helps you find files.

    Attributes:
        filename_attr (str): The name of the file attribute.
    """

    min_movie_filesize = settings_manager.settings.downloaders.movie_filesize_mb_min
    max_movie_filesize = settings_manager.settings.downloaders.movie_filesize_mb_max
    min_episode_filesize = settings_manager.settings.downloaders.episode_filesize_mb_min
    max_episode_filesize = settings_manager.settings.downloaders.episode_filesize_mb_max
    are_filesizes_valid = False

    def __init__(self, name, size):
        self.filename_attr = name
        self.filesize_attr = size
        self.are_filesizes_valid = self._validate_filesizes()

    def _validate_filesizes(self) -> bool:
        if not isinstance(settings_manager.settings.downloaders.movie_filesize_mb_min, int) or settings_manager.settings.downloaders.movie_filesize_mb_min < -1:
            logger.error("Movie filesize min is not set or invalid.")
            return False
        if not isinstance(settings_manager.settings.downloaders.movie_filesize_mb_max, int) or settings_manager.settings.downloaders.movie_filesize_mb_max < -1:
            logger.error("Movie filesize max is not set or invalid.")
            return False
        if not isinstance(settings_manager.settings.downloaders.episode_filesize_mb_min, int) or settings_manager.settings.downloaders.episode_filesize_mb_min < -1:
            logger.error("Episode filesize min is not set or invalid.")
            return False
        if not isinstance(settings_manager.settings.downloaders.episode_filesize_mb_max, int) or settings_manager.settings.downloaders.episode_filesize_mb_max < -1:
            logger.error("Episode filesize max is not set or invalid.")
            return False
        return True

    def container_file_matches_episode(self, file):
        filename = file[self.filename_attr]
        try:
            parsed_data = parse(filename)
            return parsed_data.seasons[0], parsed_data.episodes
        except Exception:
            return None, None

    def container_file_matches_movie(self, file):
        filename = file[self.filename_attr]
        try:
            parsed_data = parse(filename)
            return parsed_data.type == "movie"
        except Exception:
            return None

    def filesize_is_acceptable_movie(self, filesize):
        if not self.are_filesizes_valid:
            logger.error("Filesize settings are invalid, movie file sizes will not be checked.")
            return True
        min_size = settings_manager.settings.downloaders.movie_filesize_mb_min * 1_000_000
        max_size = settings_manager.settings.downloaders.movie_filesize_mb_max * 1_000_000 if settings_manager.settings.downloaders.movie_filesize_mb_max != -1 else float("inf")
        is_acceptable = min_size <= filesize <= max_size
        if not is_acceptable:
            logger.debug(f"Filesize {filesize} is not within acceptable range {min_size} - {max_size}")
        return is_acceptable

    def filesize_is_acceptable_show(self, filesize):
        if not self.are_filesizes_valid:
            logger.error("Filesize settings are invalid, episode file sizes will not be checked.")
            return True
        min_size = settings_manager.settings.downloaders.episode_filesize_mb_min * 1_000_000
        max_size = settings_manager.settings.downloaders.episode_filesize_mb_max * 1_000_000 if settings_manager.settings.downloaders.episode_filesize_mb_max != -1 else float("inf")
        is_acceptable = min_size <= filesize <= max_size
        if not is_acceptable:
            logger.debug(f"Filesize {filesize} is not within acceptable range {min_size} - {max_size}")
        return is_acceptable


def premium_days_left(expiration: datetime) -> str:
    """Convert an expiration date into a message showing days remaining on the user's premium account"""
    time_left = expiration - datetime.utcnow()
    days_left = time_left.days
    hours_left, minutes_left = divmod(time_left.seconds // 3600, 60)
    expiration_message = ""

    if days_left > 0:
        expiration_message = f"Your account expires in {days_left} days."
    elif hours_left > 0:
        expiration_message = (
            f"Your account expires in {hours_left} hours and {minutes_left} minutes."
        )
    else:
        expiration_message = "Your account expires soon."
    return expiration_message


def hash_from_uri(magnet_uri: str) -> str:
    if len(magnet_uri) == 40:
        # Probably already a hash
        return magnet_uri
    start = magnet_uri.index("urn:btih:") + len("urn:btih:")
    return magnet_uri[start : start + 40]
