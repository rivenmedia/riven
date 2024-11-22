from loguru import logger

from program.media.item import MediaItem, MovieMediaType, ShowMediaType
from program.media.state import States
from program.media.stream import Stream
from program.settings.manager import settings_manager
from program.services.downloaders.shared import filesize_is_acceptable, get_invalid_filesize_log_string

from .alldebrid import AllDebridDownloader
from .realdebrid import RealDebridDownloader
from .torbox import TorBoxDownloader

class InvalidFileSizeException(Exception):
    pass

class DownloadCachedStreamResult:
    def __init__(self, container=None, torrent_id=None, info=None, info_hash=None):
        self.container = container
        self.torrent_id = torrent_id
        self.info = info
        self.info_hash = info_hash

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
            TorBoxDownloader: TorBoxDownloader()
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
        logger.debug(f"Running downloader for {item.log_string}")
        # for stream in item.streams:
        #     download_result = None
        #     try:
        #         download_result = self.download_cached_stream(item, stream)
        #         if download_result:
        #             self.validate_filesize(item, download_result)
        #             if not self.update_item_attributes(item, download_result):
        #                 raise Exception("No matching files found!")
        #             break
        #     except Exception as e:
        #         if download_result and download_result.torrent_id:
        #             self.service.delete_torrent(download_result.torrent_id)
        #         logger.debug(f"Invalid stream: {stream.infohash} - reason: {e}")
        #         item.blacklist_stream(stream)

        # Chunk streams into groups of 10
        chunk_size = 10
        for i in range(0, len(item.streams), chunk_size):
            logger.debug(f"Processing chunk {i} to {i + chunk_size}")
            chunk = item.streams[i:i + chunk_size]
            instant_availability = self.get_instant_availability([stream.infohash for stream in chunk])
            # Filter out streams that aren't cached
            available_streams = [stream for stream in chunk if instant_availability.get(stream.infohash, None)]
            if not available_streams:
                continue
            for stream in available_streams:
                download_result = None
                try:
                    download_result = self.download_cached_stream(item, stream, instant_availability[stream.infohash])
                    if download_result:
                        self.validate_filesize(item, download_result)
                    if not self.update_item_attributes(item, download_result):
                        raise Exception("No matching files found!")
                    break
                except Exception as e:
                    if download_result and download_result.torrent_id:
                        self.service.delete_torrent(download_result.torrent_id)
                    logger.debug(f"Invalid stream: {stream.infohash} - reason: {e}")
                    item.blacklist_stream(stream)
        yield item


    def download_cached_stream(self, item: MediaItem, stream: Stream, cached_containers: list[dict]) -> DownloadCachedStreamResult:
        if not cached_containers:
            raise Exception("Not cached!")
        the_container = cached_containers[0]
        torrent_id = self.add_torrent(stream.infohash)
        info = self.get_torrent_info(torrent_id)
        self.select_files(torrent_id, the_container.keys())
        logger.log("DEBRID", f"Downloaded {item.log_string} from '{stream.raw_title}' [{stream.infohash}]")
        return DownloadCachedStreamResult(the_container, torrent_id, info, stream.infohash)

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