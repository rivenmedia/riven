from abc import ABC, abstractmethod
from datetime import datetime
from enum import Enum
from typing import List, Optional, Union

from RTN import ParsedData, parse

from program.media.stream import Stream
from program.services.downloaders.models import (
    ParsedFileData,
    TorrentContainer,
    TorrentInfo,
    UserInfo,
)
from program.settings.manager import settings_manager


class DownloaderBase(ABC):
    """The abstract base class for all Downloader implementations."""
    PROXY_URL: str = settings_manager.settings.downloaders.proxy_url

    @abstractmethod
    def validate(self) -> bool:
        """
        Validate the downloader configuration and premium status

        Returns:
            ValidationResult: Contains validation status and any error messages
        """

    @abstractmethod
    def get_instant_availability(self, infohash: str, item_type: str) -> Optional[TorrentContainer]:
        """
        Get instant availability for a single infohash

        Args:
            infohash: The hash of the torrent to check
            item_type: The type of media item being checked

        Returns:
            Optional[TorrentContainer]: Cached status and available files for the hash, or None if not available
        """

    @abstractmethod
    def add_torrent(self, infohash: str) -> Union[int, str]:
        """
        Add a torrent and return its information

        Args:
            infohash: The hash of the torrent to add

        Returns:
            Union[int, str]: The ID of the added torrent

        Notes:
            The return type changes depending on the downloader
        """

    @abstractmethod
    def select_files(self, torrent_id: Union[int, str], file_ids: list[int]) -> None:
        """
        Select which files to download from the torrent

        Args:
            torrent_id: ID of the torrent to select files for
            file_ids: IDs of the files to select
        """

    @abstractmethod
    def get_torrent_info(self, torrent_id: Union[int, str]) -> TorrentInfo:
        """
        Get information about a specific torrent using its ID

        Args:
            torrent_id: ID of the torrent to get info for

        Returns:
            TorrentInfo: Current information about the torrent
        """

    @abstractmethod
    def delete_torrent(self, torrent_id: Union[int, str]) -> None:
        """
        Delete a torrent from the service

        Args:
            torrent_id: ID of the torrent to delete
        """

    @abstractmethod
    def get_user_info(self) -> Optional[UserInfo]:
        """
        Get normalized user information from the debrid service

        Returns:
            UserInfo: Normalized user information including premium status and expiration
        """


def parse_filename(filename: str) -> ParsedFileData:
    """Parse a filename into a ParsedFileData object"""
    parsed_data: ParsedData = parse(filename)
    season: int | None = parsed_data.seasons[0] if parsed_data.seasons else None
    return ParsedFileData(item_type=parsed_data.type, season=season, episodes=parsed_data.episodes)


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

class Resolution(Enum):
    UHD_2160P = 9
    UHD_1440P = 7
    FHD_1080P = 6
    HD_720P = 5
    SD_576P = 4
    SD_480P = 3
    SD_360P = 2
    UNKNOWN = 1


RESOLUTION_MAP: dict[str, Resolution] = {
    "4k": Resolution.UHD_2160P,
    "2160p": Resolution.UHD_2160P,
    "1440p": Resolution.UHD_1440P,
    "1080p": Resolution.FHD_1080P,
    "720p": Resolution.HD_720P,
    "576p": Resolution.SD_576P,
    "480p": Resolution.SD_480P,
    "360p": Resolution.SD_360P,
    "unknown": Resolution.UNKNOWN,
}


def get_resolution(torrent: Stream) -> Resolution:
    """Get the resolution of a torrent."""
    resolution = torrent.resolution.lower() if torrent.resolution else "unknown"
    return RESOLUTION_MAP.get(resolution, Resolution.UNKNOWN)

def _sort_streams_by_quality(streams: List[Stream]) -> List[Stream]:
    """Sort streams by resolution (highest first) and then by rank (highest first)."""
    return sorted(
        streams,
        key=lambda stream: (get_resolution(stream).value, stream.rank),
        reverse=True
    )   