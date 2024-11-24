from typing import List, Union
from loguru import logger

from program.media.item import MediaItem, Show, Season, Episode, Movie
from program.media.state import States
from program.media.stream import Stream
from program.settings.manager import settings_manager
from program.services.downloaders.shared import parse_filename
from program.services.downloaders.models import (
    DebridFile, ParsedFileData, TorrentContainer, TorrentInfo,
    DownloadedTorrent, NoMatchingFilesException, NotCachedException
)

# from .alldebrid import AllDebridDownloader
from .realdebrid import RealDebridDownloader
from .torbox import TorBoxDownloader


class Downloader:
    def __init__(self):
        self.key = "downloader"
        self.initialized = False
        self.speed_mode = settings_manager.settings.downloaders.prefer_speed_over_quality
        self.services = {
            RealDebridDownloader: RealDebridDownloader(),
            TorBoxDownloader: TorBoxDownloader(),
            # AllDebridDownloader: AllDebridDownloader()
        }
        self.service = next((service for service in self.services.values() if service.initialized), None)
        self.initialized = self.validate()

    def validate(self):
        if self.service is None:
            logger.error(
                "No downloader service is initialized. Please initialize a downloader service."
            )
            return False
        return True

    def run(self, item: MediaItem):
        logger.debug(f"Running downloader for {item.log_string} ({item.id})")
        chunk_size = 10
        for i in range(0, len(item.streams), chunk_size):
            chunk: List[Stream] = item.streams[i:i + chunk_size]
            response: List[TorrentContainer] = self.get_instant_availability([stream.infohash for stream in chunk], item.type)
            for stream in chunk:
                container: TorrentContainer = next((c for c in response if c.infohash == stream.infohash), None)
                download_result = None
                try:
                    if container and container.cached:
                        # Handle cached streams
                        download_result: DownloadedTorrent = self.download_cached_stream(stream, container)
                    else:
                        # Handle uncached streams (not implemented)
                        raise NotCachedException("Not cached!")
                    if download_result:
                        logger.log("DEBRID", f"Downloaded {item.log_string} from '{stream.raw_title}' [{stream.infohash}]")
                        if not self.update_item_attributes(item, download_result):
                            raise NoMatchingFilesException("No matching files found!")
                        break
                except Exception as e:
                    logger.debug(f"Invalid stream: {stream.infohash} - reason: {e}")
                    if download_result and download_result.id:
                        self.service.delete_torrent(download_result.id)
                    item.blacklist_stream(stream)
        yield item

    def download_cached_stream(self, stream: Stream, container: TorrentContainer) -> DownloadedTorrent:
        """Download a cached stream"""
        torrent_id: int = self.add_torrent(stream.infohash)
        info: TorrentInfo = self.get_torrent_info(torrent_id)
        self.select_files(torrent_id, container)
        return DownloadedTorrent(id=torrent_id, info=info, infohash=stream.infohash, container=container)

    def download_uncached_stream(self, stream: Stream) -> DownloadedTorrent:
        """Download an uncached stream"""
        pass

    def update_item_attributes(self, item: MediaItem, download_result: DownloadedTorrent) -> bool:
        """Update the item attributes with the downloaded files and active stream"""
        if not download_result.container:
            logger.error(f"No container found for {item.log_string} ({item.id})")
            return False
        item = item
        found = False
        container: List[DebridFile] = download_result.container.files
        for file in container:
            file_data: ParsedFileData = parse_filename(file.filename)
            if item.type == "movie" and file_data.item_type == "movie":
                self._update_attributes(item, file, download_result)
                found = True
                break
            elif item.type in ("show", "season", "episode"):
                if not (file_data.season and file_data.episodes):
                    continue
                show: Show = item if item.type == "show" else (item.parent if item.type == "season" else item.parent.parent)
                season: Season = next((season for season in show.seasons if season.number == file_data.season), None)
                for file_episode in file_data.episodes:
                    episode: Episode = next((episode for episode in season.episodes if episode.number == file_episode), None)
                    if episode and episode.state not in [States.Completed, States.Symlinked, States.Downloaded]:
                        self._update_attributes(episode, file, download_result)
                        found = True
        return found

    def _update_attributes(self, item: Union[Movie, Episode], debrid_file: DebridFile, download_result: DownloadedTorrent) -> None:
        """Update the item attributes with the downloaded files and active stream"""
        item.file = debrid_file.filename
        item.folder = download_result.info.name
        item.alternative_folder = download_result.info.alternative_filename
        item.active_stream = {"infohash": download_result.infohash, "id": download_result.info.id}

    def get_instant_availability(self, infohashes: list[str], item_type: str) -> List[TorrentContainer]:
        """Check if the torrent is cached"""
        return self.service.get_instant_availability(infohashes, item_type)

    def add_torrent(self, infohash: str) -> int:
        """Add a torrent by infohash"""
        return self.service.add_torrent(infohash)

    def get_torrent_info(self, torrent_id: int) -> TorrentInfo:
        """Get information about a torrent"""
        return self.service.get_torrent_info(torrent_id)

    def select_files(self, torrent_id: int, container: list[str]) -> None:
        """Select files from a torrent"""
        self.service.select_files(torrent_id, container)

    def delete_torrent(self, torrent_id: int) -> None:
        """Delete a torrent"""
        self.service.delete_torrent(torrent_id)
