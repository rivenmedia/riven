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
        
        from concurrent.futures import ThreadPoolExecutor, as_completed
        MAX_CONCURRENT_DOWNLOADS = 10

        # Sort streams by RTN rank (higher rank is better)
        sorted_streams = sorted(item.streams, key=lambda x: x.rank, reverse=True)

        # Take only the top 3 streams to try
        streams_to_try = sorted_streams[:3]
        logger.debug(f"Selected top {len(streams_to_try)} streams to try downloading (by RTN rank)")
        for stream in streams_to_try:
            logger.debug(f"Will try stream: {stream.raw_title} (rank: {stream.rank})")
        
        with ThreadPoolExecutor(max_workers=MAX_CONCURRENT_DOWNLOADS) as executor:
            # Submit selected streams to the thread pool
            future_to_stream = {
                executor.submit(self.download_cached_stream, item, stream): (stream, item)
                for stream in streams_to_try
            }
            
            # Process completed downloads
            for future in as_completed(future_to_stream):
                stream, item = future_to_stream[future]
                try:
                    result = future.result()
                    if result.container is None:
                        logger.debug(f"Invalid stream: {stream.infohash} - reason: No valid containers found")
                        item.blacklist_stream(stream)
                        continue
                    stream.container = result.container
                    stream.torrent_id = result.torrent_id
                    stream.info = result.info
                    stream.info_hash = result.info_hash
                    self.validate_filesize(item, result)
                    if not self.update_item_attributes(item, result):
                        raise Exception("No matching files found!")
                    # Cancel other downloads since we got a good one
                    for f in future_to_stream:
                        if not f.done():
                            f.cancel()
                    yield item
                    return
                except TorrentNotFoundError as e:
                    logger.debug(f"Invalid stream: {stream.infohash} - reason: {str(e)}")
                    item.blacklist_stream(stream)
                    continue
                except InvalidFileIDError as e:
                    # Don't blacklist for file ID errors as they may be temporary
                    logger.debug(f"File selection failed for stream {stream.infohash}: {str(e)}")
                    continue
                except InvalidFileSizeException:
                    logger.debug(get_invalid_filesize_log_string(item))
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
        item = item
        info_hash = download_result.info.get("hash", None)
        id = download_result.info.get("id", None)
        original_filename = download_result.info.get("original_filename", None)
        filename = download_result.info.get("filename", None)
        if not info_hash or not id or not original_filename or not filename:
            return False
        container = download_result.container
        for file in container.values():
            if item.type == MovieMediaType.Movie.value and self.service.file_finder.container_file_matches_movie(file):
                item.file = file[self.service.file_finder.filename_attr]
                item.folder = filename
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
                if file_season and file_episodes:
                    season = next((season for season in show.seasons if season.number == file_season), None)
                    for file_episode in file_episodes:
                        episode = next((episode for episode in season.episodes if episode.number == file_episode), None)
                        if episode and episode.state not in [States.Completed, States.Symlinked, States.Downloaded]:
                            episode.file = file[self.service.file_finder.filename_attr]
                            episode.folder = filename
                            episode.alternative_folder = original_filename
                            episode.active_stream = {"infohash": info_hash, "id": id}
                            # We have to make sure the episode is correct if item is an episode
                            if item.type != ShowMediaType.Episode.value or (item.type == ShowMediaType.Episode.value and episode.number == item.number):
                                found = True
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