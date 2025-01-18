from typing import List, Optional, Union

from loguru import logger

from program.media.item import Episode, MediaItem, Movie, Season, Show
from program.media.state import States
from program.media.stream import Stream
from program.services.downloaders.models import (
    DebridFile,
    DownloadedTorrent,
    NoMatchingFilesException,
    NotCachedException,
    ParsedFileData,
    TorrentContainer,
    TorrentInfo,
)
from program.services.downloaders.shared import parse_filename

from .alldebrid import AllDebridDownloader
from .realdebrid import RealDebridDownloader


class Downloader:
    def __init__(self):
        self.key = "downloader"
        self.initialized = False
        self.services = {
            RealDebridDownloader: RealDebridDownloader(),
            AllDebridDownloader: AllDebridDownloader()
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
        logger.debug(f"Starting download process for {item.log_string} ({item.id})")

        if item.active_stream:
            logger.debug(f"Skipping {item.log_string} ({item.id}) as it has already been downloaded by another download session")
            yield item

        download_success = False
        for stream in item.streams:
            container = self.validate_stream(stream, item)
            if not container:
                logger.debug(f"Stream {stream.infohash} is not cached or valid.")
                continue

            try:
                download_result = self.download_cached_stream(stream, container)
                if self.update_item_attributes(item, download_result):
                    logger.log("DEBRID", f"Downloaded {item.log_string} from '{stream.raw_title}' [{stream.infohash}]")
                    download_success = True
                    break
                else:
                    raise NoMatchingFilesException(f"No valid files found")
            except Exception as e:
                logger.debug(f"Stream {stream.infohash} failed: {e}")
                if 'download_result' in locals() and download_result.id:
                    self.service.delete_torrent(download_result.id)
                item.blacklist_stream(stream)

        if not download_success:
            logger.debug(f"Failed to download any streams for {item.log_string} ({item.id})")

        yield item

    def validate_stream(self, stream: Stream, item: MediaItem) -> Optional[TorrentContainer]:
        """
        Validate a single stream by ensuring its files match the item's requirements.
        """
        container = self.get_instant_availability(stream.infohash, item.type)
        if not container:
            item.blacklist_stream(stream)
            return None

        valid_files = []
        for file in container.files or []:
            debrid_file = DebridFile.create(
                filename=file.filename,
                filesize_bytes=file.filesize,
                filetype=item.type,
                file_id=file.file_id
            )
            if debrid_file:
                valid_files.append(debrid_file)

        if valid_files:
            container.files = valid_files
            return container

        item.blacklist_stream(stream)
        return None

    def update_item_attributes(self, item: MediaItem, download_result: DownloadedTorrent) -> bool:
        """Update the item attributes with the downloaded files and active stream."""
        if not download_result.container:
            raise NotCachedException(f"No container found for {item.log_string} ({item.id})")

        found = False
        for file in download_result.container.files:
            file_data: ParsedFileData = parse_filename(file.filename)
            if self.match_file_to_item(item, file_data, file, download_result):
                found = True
                break

        return found

    def match_file_to_item(self, item: MediaItem, file_data: ParsedFileData, file: DebridFile, download_result: DownloadedTorrent) -> bool:
        """Check if the file matches the item and update attributes."""
        found = False
        if item.type == "movie" and file_data.item_type == "movie":
            self._update_attributes(item, file, download_result)
            return True

        if item.type in ("show", "season", "episode"):
            if not (file_data.season and file_data.episodes):
                return False

            show: Show = item if item.type == "show" else (item.parent if item.type == "season" else item.parent.parent)
            season: Season = next((season for season in show.seasons if season.number == file_data.season), None)
            for file_episode in file_data.episodes:
                episode: Episode = next((episode for episode in season.episodes if episode.number == file_episode), None)
                if episode and episode.state not in [States.Completed, States.Symlinked, States.Downloaded]:
                    self._update_attributes(episode, file, download_result)
                    found = True

        return found

    def download_cached_stream(self, stream: Stream, container: TorrentContainer) -> DownloadedTorrent:
        """Download a cached stream"""
        torrent_id: int = self.add_torrent(stream.infohash)
        info: TorrentInfo = self.get_torrent_info(torrent_id)
        if container.file_ids:
            self.select_files(torrent_id, container.file_ids)
        return DownloadedTorrent(id=torrent_id, info=info, infohash=stream.infohash, container=container)

    def _update_attributes(self, item: Union[Movie, Episode], debrid_file: DebridFile, download_result: DownloadedTorrent) -> None:
        """Update the item attributes with the downloaded files and active stream"""
        item.file = debrid_file.filename
        item.folder = download_result.info.name
        item.alternative_folder = download_result.info.alternative_filename
        item.active_stream = {"infohash": download_result.infohash, "id": download_result.info.id}

    def get_instant_availability(self, infohash: str, item_type: str) -> List[TorrentContainer]:
        """Check if the torrent is cached"""
        return self.service.get_instant_availability(infohash, item_type)

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
