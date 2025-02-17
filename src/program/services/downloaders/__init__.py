from typing import List, Optional, Union

from loguru import logger

from program.media.item import Episode, MediaItem, Movie, Season, Show
from program.media.state import States
from program.media.stream import Stream
from program.services.downloaders.models import (
    DebridFile,
    InvalidDebridFileException,
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
        """
        Executes the download process for a given media item by iterating over its available streams.
        
        This generator function first checks conditions under which no download should be attempted:
        - If the item's parent is blocked (using item.is_parent_blocked()), it logs a debug message and immediately yields the item.
        - If the item already has an active stream or its last_state indicates it has been downloaded (i.e., one of Completed, Symlinked, or Downloaded), it logs this status and yields the item.
        - If no streams are available for the item, a debug message is logged and the item is yielded.
        
        If streams are available, the function processes each stream by:
        - Validating the stream via the validate_stream() method. If validation fails (i.e., no valid torrent container is returned), the function logs a debug message and moves to the next stream.
        - For a valid stream, attempting to download the cached stream with download_cached_stream(), and then updating the item's attributes with update_item_attributes().
          - If the update is successful, a success message is logged and the download process is stopped.
          - If update_item_attributes() does not confirm the download (e.g., no matching valid files are found), a NoMatchingFilesException is raised internally.
        - Handling any exceptions by logging the error, attempting to delete any created torrent using the service's delete_torrent(), and blacklisting the problematic stream with item.blacklist_stream().
        
        Finally, if none of the streams result in a successful download, the function logs a failure message and yields the item.
        
        Parameters:
            item (MediaItem): The media item to be processed for download. It should contain attributes such as streams, active_stream, last_state, and log_string that guide the download logic.
        
        Yields:
            MediaItem: The original or updated media item, reflecting any changes from a successful download attempt or remaining unchanged if no stream was successfully processed.
        
        Raises:
            No exceptions are propagated externally; all exceptions during the download attempt are caught and handled within the function.
        
        Example:
            >>> for processed_item in downloader.run(media_item):
            ...     process(processed_item)
        """
        logger.debug(f"Starting download process for {item.log_string} ({item.id})")

        if item.is_parent_blocked():
            logger.debug(f"Skipping {item.log_string} ({item.id}) as it has a blocked parent, or is a blocked item")
            yield item

        if item.active_stream or item.last_state in [States.Completed, States.Symlinked, States.Downloaded]:
            logger.debug(f"Skipping {item.log_string} ({item.id}) as it has already been downloaded by another download session")
            yield item

        if not item.streams:
            logger.debug(f"No streams available for {item.log_string} ({item.id})")
            yield item

        download_success = False
        for stream in item.streams:
            container: Optional[TorrentContainer] = self.validate_stream(stream, item)
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
                    raise NoMatchingFilesException(f"No valid files found for {item.log_string} ({item.id})")
            except Exception as e:
                logger.debug(f"Stream {stream.infohash} failed: {e}")
                if 'download_result' in locals() and download_result.id:
                    try:
                        self.service.delete_torrent(download_result.id)
                        logger.debug(f"Deleted failed torrent {stream.infohash} for {item.log_string} ({item.id}) on debrid service.")
                    except Exception as e:
                        logger.debug(f"Failed to delete torrent {stream.infohash} for {item.log_string} ({item.id}) on debrid service: {e}")
                item.blacklist_stream(stream)

        if not download_success:
            logger.debug(f"Failed to download any streams for {item.log_string} ({item.id})")

        yield item

    def validate_stream(self, stream: Stream, item: MediaItem) -> Optional[TorrentContainer]:
        """
        Validate a media stream for a given media item.
        
        This method checks if the stream's torrent container is instantly available for the item's type and then validates each file within the container. If a valid container is not found, or if none of the files pass validation (due to issues such as an InvalidDebridFileException), the stream is blacklisted from the media item and the method returns None. If valid files are found, the container's file list is updated to include only these files and the container is returned.
        
        Parameters:
            stream (Stream): A stream object containing the infohash and associated file metadata.
            item (MediaItem): The media item for which the stream is being validated. The item may have its stream blacklisted if validation fails.
        
        Returns:
            Optional[TorrentContainer]: The torrent container with validated files if available; otherwise, None.
        """
        container = self.get_instant_availability(stream.infohash, item.type)
        if not container:
            item.blacklist_stream(stream)
            return None

        valid_files = []
        for file in container.files or []:
            try:
                debrid_file = DebridFile.create(
                    filename=file.filename,
                    filesize_bytes=file.filesize,
                    filetype=item.type,
                    file_id=file.file_id
                )
            except InvalidDebridFileException as e:
                logger.debug(f"{stream.infohash}: {e}")
                continue
            if debrid_file:
                valid_files.append(debrid_file)

        if valid_files:
            container.files = valid_files
            return container

        item.blacklist_stream(stream)
        return None

    def update_item_attributes(self, item: MediaItem, download_result: DownloadedTorrent) -> bool:
        """
        Update the attributes of the given media item based on the downloaded torrent result.
        
        This method verifies that the download result contains a valid container. If no container is found,
        a NotCachedException is raised. It then iterates over each file in the container, parses the filename
        to extract file details, and uses the match_file_to_item method to determine if the file corresponds to
        the media item. If any file matches, the media item attributes are updated accordingly.
        
        Parameters:
            item (MediaItem): The media item whose attributes are to be updated.
            download_result (DownloadedTorrent): The result object containing the download information and files,
                                                   including the container from which files are extracted.
        
        Returns:
            bool: True if at least one file in the container matches the media item and updates its attributes;
                  False otherwise.
        
        Raises:
            NotCachedException: If the download_result does not contain a valid container.
        """
        if not download_result.container:
            raise NotCachedException(f"No container found for {item.log_string} ({item.id})")

        found = False
        for file in download_result.container.files:
            file_data: ParsedFileData = parse_filename(file.filename)
            if self.match_file_to_item(item, file_data, file, download_result):
                found = True

        return found

    def match_file_to_item(self, item: MediaItem, file_data: ParsedFileData, file: DebridFile, download_result: DownloadedTorrent) -> bool:
        """
        Matches a debrid file to a media item and updates the item or episode attributes if a valid match is found.
        
        This method verifies whether the provided debrid file, based on its parsed metadata, corresponds to the given media item. For movies, a match is successful when both the media item and the parsed file data indicate a "movie" type. For TV shows or episodic content (i.e., items with types "show", "season", or "episode"), the function checks if the file data includes episode numbers. It then determines the correct season (assuming season 1 if not specified) and iterates through the episode numbers to locate matching episodes within that season. If a matching episode is found and its state is not one of completed, symlinked, or downloaded states, the method will update the episode’s attributes using an internal attribute update function.
        
        Parameters:
            item (MediaItem): The media item to match, which may represent a movie, show, season, or episode.
            file_data (ParsedFileData): The parsed metadata extracted from the debrid file, including the item type, season number, and a list of episode numbers.
            file (DebridFile): The debrid file associated with the download.
            download_result (DownloadedTorrent): The result of the download attempt, used to update item attributes if matched.
        
        Returns:
            bool: True if the debrid file matches the media item and the attributes are successfully updated; otherwise, False.
        """
        found = False

        if item.type == "movie" and file_data.item_type == "movie":
            self._update_attributes(item, file, download_result)
            return True

        if item.type in ("show", "season", "episode"):
            if not file_data.episodes:
                return False

            show: Show = item if item.type == "show" else (item.parent if item.type == "season" else item.parent.parent)
            season_number = file_data.season if file_data.season is not None else 1  # Assuming season 1 if not specified
            season: Season = next((season for season in show.seasons if season.number == season_number), None)
            if season is None:
                # These messages can get way too spammy.
                # logger.debug(f"Season {season_number} not found in show {show.log_string}, unable to match files to season children. Metadata may be incorrect for show.")
                return False

            for file_episode in file_data.episodes:
                episode: Episode = next((episode for episode in season.episodes if episode.number == file_episode), None)
                if episode is None:
                    # logger.debug(f"Episode {file_episode} from file does not match any episode in {season.log_string}. Metadata may be incorrect for season.")
                    return False

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
