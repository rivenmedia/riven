from program.media.item import MediaItem
from utils.logger import logger

from .alldebrid import AllDebridDownloader
from .realdebrid import RealDebridDownloader
from .torbox import TorBoxDownloader
from .shared import get_needed_media
from concurrent.futures import CancelledError, ThreadPoolExecutor, as_completed


class Downloader:
    def __init__(self):
        self.key = "downloader"
        self.initialized = False
        self.service = next((service for service in [
            RealDebridDownloader(),
            #AllDebridDownloader(),
            #TorBoxDownloader()
            ] if service.initialized), None)

        self.initialized = self.validate()

    def validate(self):
        if self.service is None:
            logger.error("No downloader service is initialized. Please initialize a downloader service.")
            return False
        return True

    def run(self, item: MediaItem):
        logger.debug(f"Running downloader for {item.log_string}")
        needed_media = get_needed_media(item)
        hashes = [stream.infohash for stream in item.streams if stream.infohash not in self.service.existing_hashes]
        cached_streams = self.get_cached_streams(hashes, needed_media)
        if len(cached_streams) > 0:
            item.active_stream = cached_streams[0]
            try:
                self.download(item, item.active_stream)
            except Exception as e:
                logger.error(f"Failed to download {item.log_string}: {e}")
                self._delete_and_reset_active_stream(item)
        else:
            for stream in item.streams:
                item.blacklist_stream(stream)
            logger.log("DEBRID", f"No cached torrents found for {item.log_string}")
        yield item

    def _delete_and_reset_active_stream(self, item: MediaItem):
        self.service.existing_hashes.remove(item.active_stream["infohash"])
        self.service.delete_torrent_with_infohash(item.active_stream["infohash"])
        stream = next(stream for stream in item.streams if stream.infohash == item.active_stream["infohash"])
        item.active_stream = {}
        item.blacklist_stream(stream)

    def get_cached_streams(self, hashes: list[str], needed_media, break_on_first = True) -> dict:
        chunks = [hashes[i:i + 5] for i in range(0, len(hashes), 5)]
        # Using a list to share the state, booleans are immutable
        break_pointer = [False, break_on_first]
        results = []

        with ThreadPoolExecutor(thread_name_prefix="Dowloader") as executor:
            futures = []
            for chunk in chunks:
                future = executor.submit(self.service.process_hashes, chunk, needed_media, break_pointer)
                futures.append(future)

            for future in as_completed(futures):
                try:
                    _result = future.result()
                except CancelledError:
                    continue
                if isinstance(_result, dict) and len(_result) > 0:
                    results.append(_result)
                    if break_on_first:
                        for future in futures:
                            future.cancel()

        return results

    def download(self, item, active_stream: dict) -> str:
        torrent_id = self.service.download_cached(active_stream)
        torrent_names = self.service.get_torrent_names(torrent_id)
        update_item_attributes(item, torrent_names)
        logger.log("DEBRID", f"Downloaded {item.log_string}")

def update_item_attributes(item: MediaItem, names: tuple[str, str]):
    """ Update the item attributes with the downloaded files and active stream """
    matches_dict = item.active_stream.get("matched_files")
    item.folder = names[0]
    item.alternative_folder = names[1]
    stream = next((stream for stream in item.streams if stream.infohash == item.active_stream["infohash"]), None)
    item.active_stream["name"] = stream.raw_title

    if item.type in ["movie", "episode"]:
        item.file = next(file["filename"] for file in next(iter(matches_dict.values())).values())
    elif item.type == "show":
        for season in item.seasons:
            for episode in season.episodes:
                file = matches_dict.get(season.number, {}).get(episode.number, {})
                if file:
                    episode.file = file["filename"]
                    episode.folder = item.folder
                    episode.alternative_folder = item.alternative_folder
                    episode.active_stream = {**item.active_stream, "files": [ episode.file ] }
    elif item.type == "season":
        for episode in item.episodes:
            file = matches_dict.get(item.number, {}).get(episode.number, {})
            if file:
                episode.file = file["filename"]
                episode.folder = item.folder
                episode.alternative_folder = item.alternative_folder
                episode.active_stream = {**item.active_stream, "files": [ episode.file ] }