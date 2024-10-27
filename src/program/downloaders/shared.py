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
    def process_hashes(
        self, chunk: list[InfoHash], needed_media: dict, break_pointer: list[bool]
    ) -> dict:
        """
        Search for debrid-cached media in a list of torrent hashes, returning a dictionary with the files found.

        - chunk:         A list of infohashes to scan.
        - needed_media:  The media needed for completing this show. A dict of {season: [episodeList]}.
                         season and episodeList are ints. For movies, needed_media is None.
        - break_pointer: A list of two booleans. The first must be set to True once the needed_media is found.
                         If the second bool is True, continue scanning all chunks, else break once needed_media is found.

        Return value looks like this. FileFinder is a helper that can be used to build the inner dict based on needed_media.
        ```
        {
            "69033cebd0f892bf7e9181b8002923936b9ac604": {
                "matched_files": {
                    1: {                # Season (or 1 for movies)
                        1: {            # Episode (or 1 for movies)
                            "filename": "Big.Buck.Bunny.4K.WEBDL.2160p.X265.AAR.UTR.mkv"
                        }
                    }
                }
            }
        }
        ```
        """

    @abstractmethod
    def download_cached(self, active_stream: dict) -> DebridTorrentId:
        """
        Instructs the debrid service to download this content.

        - active_stream: A dict containing the key "infohash", the torrent hash to download.

        Returns an identifier used by the debrid service to reference this torrent later.
        """

    @abstractmethod
    def get_torrent_names(self, id: DebridTorrentId) -> tuple[str, Optional[str]]:
        """
        Gets the name(s) of the torrent with this debrid-specific identifier

        - active_stream: A dict containing the key "infohash", whose value is the torrent hash to download.

        Returns the name of the torrent, and an alternative / original name if the debrid service provides one
        (None otherwise).
        """

    @abstractmethod
    def delete_torrent_with_infohash(self, infohash: InfoHash) -> None:
        """
        Deletes a torrent from the debrid service.

        - infohash: Hash of the torrent.
        """

    @abstractmethod
    def add_torrent_magnet(self, magnet_uri: str) -> DebridTorrentId:
        """
        Adds a torrent to the debrid service using a magnet URI.

        - magnet_uri: The URI of the torrent to add (like magnet:?xt=urn:btih:<infohash>)
        """

    @abstractmethod
    def get_torrent_info(self, torrent_id: DebridTorrentId) -> dict:
        """
        Gets information about a cached torrent.

        - torrent_id: The identifier used by the debrid service for this torrent.

        The returned dict has at least "hash" and "filename".
        """

    @abstractmethod
    def get_instant_availability_formatted(self, infohashes: list[str]) -> dict:
        """
        Checks the debrid service for the availability of torrents by their infohashes.

        - infohashes: A list of infohashes to check.

        Returns a dict of infohashes and their availability.
        """


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

    def get_cached_container(
        self,
        needed_media: dict[int, list[int]],
        break_pointer: list[bool] = [False],
        container: dict = {},
    ) -> dict:
        if not needed_media or len(container) >= len(
            [episode for season in needed_media for episode in needed_media[season]]
        ):
            matched_files = self.cache_matches(container, needed_media, break_pointer)
            if matched_files:
                return {"all_files": container, "matched_files": matched_files}
        return {}

    def filename_matches_show(self, filename):
        try:
            parsed_data = parse(filename)
            return parsed_data.seasons[0], parsed_data.episodes
        except Exception:
            return None, None

    def filename_matches_movie(self, filename):
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

    def cache_matches(
        self,
        cached_files: dict,
        needed_media: dict[int, list[int]],
        break_pointer: list[bool] = [False],
    ):
        if needed_media:
            # Convert needed_media to a set of (season, episode) tuples
            needed_episodes = {
                (season, episode)
                for season in needed_media
                for episode in needed_media[season]
            }
            matches_dict = {}

            for file in cached_files.values():
                if break_pointer[1] and break_pointer[0]:
                    break
                matched_season, matched_episodes = self.filename_matches_show(
                    file[self.filename_attr]
                )
                if matched_season and matched_episodes:
                    for episode in matched_episodes:
                        if (matched_season, episode) in needed_episodes and self.filesize_is_acceptable_show(file[self.filesize_attr]):
                            if matched_season not in matches_dict:
                                matches_dict[matched_season] = {}
                            matches_dict[matched_season][episode] = file
                            needed_episodes.remove((matched_season, episode))

            if not needed_episodes:
                return matches_dict
        else:
            biggest_file = max(
                cached_files.values(), key=lambda x: x[self.filesize_attr]
            )
            if biggest_file and self.filename_matches_movie(
                biggest_file[self.filename_attr]
            ) and self.filesize_is_acceptable_movie(biggest_file[self.filesize_attr]):
                return {1: {1: biggest_file}}


def get_needed_media(item: MediaItem) -> dict:
    acceptable_states = [
        States.Indexed,
        States.Scraped,
        States.Unknown,
        States.Failed,
        States.PartiallyCompleted,
        States.Ongoing,
    ]
    if item.type == "movie":
        needed_media = None
    elif item.type == "show":
        needed_media = {
            season.number: [
                episode.number
                for episode in season.episodes
                if episode.state in acceptable_states
            ]
            for season in item.seasons
            if season.state in acceptable_states
        }
    elif item.type == "season":
        needed_media = {
            item.number: [
                episode.number
                for episode in item.episodes
                if episode.state in acceptable_states
            ]
        }
    elif item.type == "episode":
        needed_media = {item.parent.number: [item.number]}
    return needed_media


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
