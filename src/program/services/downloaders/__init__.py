from loguru import logger

from program.media.item import MediaItem, MovieMediaType, ShowMediaType
from program.media.state import States
from program.media.stream import Stream
from program.settings.manager import settings_manager
from program.services.downloaders.shared import (
    DownloadCachedStreamResult,
    filesize_is_acceptable,
    get_invalid_filesize_log_string,
)

from .alldebrid import AllDebridDownloader
from .realdebrid import RealDebridDownloader, TorrentNotFoundError, InvalidFileIDError
# from .torbox import TorBoxDownloader
import os

class InvalidFileSizeException(Exception):
    pass

class Downloader:
    def __init__(self):
        self.key = "downloader"
        self.initialized = False
        self.speed_mode = (
            settings_manager.settings.downloaders.prefer_speed_over_quality
        )
        self.services = {
            RealDebridDownloader: RealDebridDownloader(),
            AllDebridDownloader: AllDebridDownloader(),
            # TorBoxDownloader: TorBoxDownloader()
        }
        self.service = next(
            (service for service in self.services.values() if service.initialized), None
        )

        self.initialized = self.validate()

    def validate(self):
        if self.service is None:
            logger.error(
                "No downloader service is initialized. Please initialize a downloader service."
            )
            return False
        return True

    def run(self, item: MediaItem):
        """Run downloader for media item with concurrent downloads"""
        logger.debug(f"Running downloader for {item.log_string}")
        
        # Skip if item or any of its children are already downloaded
        if item.type == ShowMediaType.Show.value:
            for season in item.seasons:
                for episode in season.episodes:
                    if episode.state in [States.Downloaded, States.Symlinked, States.Completed]:
                        logger.debug(f"Skipping download for {episode.log_string} - already in state: {episode.state}")
                        continue
        elif item.type == ShowMediaType.Season.value:
            for episode in item.episodes:
                if episode.state in [States.Downloaded, States.Symlinked, States.Completed]:
                    logger.debug(f"Skipping download for {episode.log_string} - already in state: {episode.state}")
                    continue
        elif item.state in [States.Downloaded, States.Symlinked, States.Completed]:
            logger.debug(f"Skipping download for {item.log_string} - already in state: {item.state}")
            return

        from concurrent.futures import ThreadPoolExecutor, as_completed
        MAX_CONCURRENT_DOWNLOADS = 1

        # Sort streams by RTN rank (higher rank is better)
        sorted_streams = sorted(item.streams, key=lambda x: x.rank, reverse=True)

        # Take only the top 3 streams to try
        for stream in sorted_streams[:3]:
            try:
                result = self.download_cached_stream(item, stream)
                if not result:
                    logger.debug(f"No result returned for stream {stream.infohash}")
                    continue
                if not result.container:
                    logger.debug(f"No valid files found in torrent for stream {stream.infohash}")
                    item.blacklist_stream(stream)
                    continue
                self.validate_filesize(item, result)
                if self.update_item_attributes(item, result):
                    # Store the state before yielding
                    item.store_state()
                    yield item
                    return
            except InvalidFileIDError as e:
                # Don't blacklist for file ID errors as they may be temporary
                logger.debug(f"File selection failed for stream {stream.infohash}: {str(e)}")
                continue
            except InvalidFileSizeException:
                media_type = self._get_item_media_type(item)
                logger.debug(f"Invalid filesize for stream {stream.infohash}")
                item.blacklist_stream(stream)
                continue
            except Exception as e:
                logger.debug(f"Invalid stream: {stream.infohash} - reason: {str(e)}")
                item.blacklist_stream(stream)
                continue

    def download_cached_stream(self, item: MediaItem, stream: Stream) -> DownloadCachedStreamResult:
        """Download a cached stream from the active debrid service"""
        return self.service.download_cached_stream(item, stream)

    def get_instant_availability(self, infohashes: list[str]) -> dict[str, list[dict]]:
        return self.service.get_instant_availability(infohashes)

    def add_torrent(self, infohash: str) -> int:
        return self.service.add_torrent(infohash)

    def get_torrent_info(self, torrent_id: int):
        return self.service.get_torrent_info(torrent_id)

    def select_files(self, torrent_id, container):
        self.service.select_files(torrent_id, container)

    def delete_torrent(self, torrent_id):
        self.service.delete_torrent(torrent_id)

    def update_item_attributes(self, item: MediaItem, download_result: DownloadCachedStreamResult) -> bool:
        """Update the item attributes with the downloaded files and active stream"""
        found = False
        info_hash = download_result.info_hash
        id = download_result.torrent_id
        
        # Get the original filename from the torrent info
        original_filename = download_result.info.get("filename", "")
        filename = original_filename
        
        # Process each file in the container
        for file in download_result.container.values():
            if item.type == MovieMediaType.Movie.value:
                if self.service.file_finder.container_file_matches_movie(file):
                    file_path = file[self.service.file_finder.filename_attr]
                    logger.debug(f"Found matching movie file: {file_path}")
                    # Get just the filename from the path
                    item.file = os.path.basename(file_path)
                    # Get the parent folder from the path, fallback to torrent name
                    item.folder = os.path.dirname(file_path) or filename
                    # Store the original torrent name for alternative matching
                    item.alternative_folder = original_filename
                    item.active_stream = {"infohash": info_hash, "id": id}
                    found = True
                    break
            
            if item.type in (ShowMediaType.Show.value, ShowMediaType.Season.value, ShowMediaType.Episode.value):
                show = item
                if item.type == ShowMediaType.Season.value:
                    show = item.parent
                elif item.type == ShowMediaType.Episode.value:
                    show = item.parent.parent
                    
                file_season, file_episodes = self.service.file_finder.container_file_matches_episode(file)
                logger.debug(f"Episode match result - season: {file_season}, episodes: {file_episodes}")
                
                if file_season and file_episodes:
                    season = next((season for season in show.seasons if season.number == file_season), None)
                    if season:
                        logger.debug(f"Found matching season {file_season}")
                        for file_episode in file_episodes:
                            episode = next((episode for episode in season.episodes if episode.number == file_episode), None)
                            if episode and episode.state not in [States.Completed, States.Symlinked, States.Downloaded]:
                                logger.debug(f"Found matching episode {file_episode} in season {file_season}")
                                # Store the full file path for the episode
                                file_path = file[self.service.file_finder.filename_attr]
                                # Get just the filename from the path
                                episode.file = os.path.basename(file_path)
                                # Get the parent folder from the path, fallback to torrent name
                                episode.folder = os.path.dirname(file_path) or filename
                                # Store the original torrent name for alternative matching
                                episode.alternative_folder = original_filename
                                # Store stream info for future reference
                                episode.active_stream = {"infohash": info_hash, "id": id}
                                # Log the stored paths for debugging
                                logger.debug(f"Stored paths for {episode.log_string}:")
                                logger.debug(f"  File: {episode.file}")
                                logger.debug(f"  Folder: {episode.folder}")
                                logger.debug(f"  Alt Folder: {episode.alternative_folder}")
                                # We have to make sure the episode is correct if item is an episode
                                if item.type != ShowMediaType.Episode.value or (item.type == ShowMediaType.Episode.value and episode.number == item.number):
                                    found = True
                    else:
                        logger.debug(f"No matching season found for season {file_season}")
        return found

    def validate_filesize(self, item: MediaItem, download_result: DownloadCachedStreamResult):
        for file in download_result.container.values():
            item_media_type = self._get_item_media_type(item)
            if not filesize_is_acceptable(file[self.service.file_finder.filesize_attr], item_media_type):

                raise InvalidFileSizeException(f"File '{file[self.service.file_finder.filename_attr]}' is invalid: {get_invalid_filesize_log_string(file[self.service.file_finder.filesize_attr], item_media_type)}")
        logger.debug(f"All files for {download_result.info_hash} are of an acceptable size")

    @staticmethod
    def _get_item_media_type(item):
        if item.type in (media_type.value for media_type in ShowMediaType):
            return ShowMediaType.Show.value
        return MovieMediaType.Movie.value