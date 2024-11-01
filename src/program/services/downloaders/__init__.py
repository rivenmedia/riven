from concurrent.futures import CancelledError, ThreadPoolExecutor, as_completed

from program.media.item import MediaItem
from program.media.state import States
from program.media.stream import Stream
from program.settings.manager import settings_manager
from loguru import logger

from .alldebrid import AllDebridDownloader
from .realdebrid import RealDebridDownloader
# from .torbox import TorBoxDownloader


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
        logger.debug(f"Running downloader for {item.log_string}")

        for stream in item.streams:
            torrent_id = None
            try:
                torrent_id = self.download_cached_stream(item, stream)
                if torrent_id:
                    break
            except Exception as e:
                if torrent_id:
                    self.service.delete_torrent(torrent_id)
                logger.debug(f"Blacklisting {stream.raw_title} for {item.log_string}, reason: {e}")
                item.blacklist_stream(stream)
        yield item

    def download_cached_stream(self, item: MediaItem, stream: Stream) -> bool:
        torrent_id = None
        cached_containers = self.get_instant_availability([stream.infohash]).get(stream.infohash, None)
        if not cached_containers:
            raise Exception("Not cached!")
        the_container = cached_containers[0]
        torrent_id = self.add_torrent(stream.infohash)
        info = self.get_torrent_info(torrent_id)
        self.select_files(torrent_id, the_container.keys())
        if not self.update_item_attributes(item, info, the_container):
            raise Exception("No matching files found!")
        logger.info(f"Downloaded {item.log_string} from '{stream.raw_title}' [{stream.infohash}]")
        return torrent_id

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

    def update_item_attributes(self, item: MediaItem, info, container) -> bool:
        """Update the item attributes with the downloaded files and active stream"""
        found = False
        item = item
        container = container
        for file in container.values():
            if item.type == "movie" and self.service.file_finder.container_file_matches_movie(file):
                item.file = file[self.service.file_finder.filename_attr]
                item.folder = info["filename"]
                item.alternative_folder = info["original_filename"]
                item.active_stream = {"infohash": info["hash"], "id": info["id"]}
                found = True
                break
            if item.type in ["show", "season", "episode"]:
                show = item
                if item.type == "season":
                    show = item.parent
                elif item.type == "episode":
                    show = item.parent.parent
                file_season, file_episodes = self.service.file_finder.container_file_matches_episode(file)
                if file_season and file_episodes:
                    season = next((season for season in show.seasons if season.number == file_season), None)
                    for file_episode in file_episodes:
                        episode = next((episode for episode in season.episodes if episode.number == file_episode), None)
                        if episode and episode.state not in [States.Completed, States.Symlinked, States.Downloaded]:
                            episode.file = file[self.service.file_finder.filename_attr]
                            episode.folder = info["filename"]
                            episode.alternative_folder = info["original_filename"]
                            episode.active_stream = {"infohash": info["hash"], "id": info["id"]}
                            # We have to make sure the episode is correct if item is an episode
                            if item.type != "episode" or (item.type == "episode" and episode.number == item.number):
                                found = True
        return found