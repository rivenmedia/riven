"""Realdebrid module"""

import time
from pathlib import Path
from types import SimpleNamespace
from typing import Generator, List

from program.media.item import Episode, MediaItem, Movie, Season, Show
from program.settings.manager import settings_manager
from requests import ConnectTimeout
from RTN.parser import episodes_from_season
from utils.logger import logger
from utils.request import get, ping, post

WANTED_FORMATS = [".mkv", ".mp4", ".avi"]
RD_BASE_URL = "https://api.real-debrid.com/rest/1.0"


class Debrid:
    """Real-Debrid API Wrapper"""

    def __init__(self):
        self.initialized = False
        self.key = "real_debrid"
        self.settings = settings_manager.settings.real_debrid
        self.auth_headers = {"Authorization": f"Bearer {self.settings.api_key}"}
        self.running = False
        if not self._validate():
            logger.error("Realdebrid settings incorrect or not premium!")
            return
        logger.info("Real Debrid initialized!")
        self.initialized = True

    def _validate(self) -> bool:
        try:
            response = ping(f"{RD_BASE_URL}/user", additional_headers=self.auth_headers)
            if response.ok:
                user_info = response.json()
                return user_info.get("premium", 0) > 0
        except ConnectTimeout:
            logger.error("Connection to Real-Debrid timed out.")
        except Exception as e:
            logger.error("Failed to validate Real-Debrid settings: %s", e)
        return False

    def run(self, item: MediaItem) -> Generator[MediaItem, None, None]:
        """Download media item from real-debrid.com"""
        if not item.streams:
            yield item
            return
        if isinstance(item, Show):
            logger.debug("Show items are not supported by Real-Debrid")
            yield item
            return
        if not self.is_cached(item):
            yield item
            return
        if not self._is_downloaded(item):
            self._download_item(item)
        self._set_file_paths(item)
        yield item

    def _is_downloaded(self, item: MediaItem) -> bool:
        """Check if item is already downloaded"""
        try:
            torrents = self.get_torrents(1000)
            for torrent in torrents:
                if torrent.hash == item.active_stream.get("hash"):
                    info = self.get_torrent_info(torrent.id)
                    if isinstance(item, Episode):
                        if not any(file for file in info.files if file.selected == 1 and item.number in episodes_from_season(Path(file.path).name, item.parent.number)):
                            return False

                    item.set("active_stream.id", torrent.id)
                    self.set_active_files(item)
                    logger.debug("Torrent for %s already downloaded", item.log_string)
                    return True
        except Exception as e:
            logger.error("Error checking if item is downloaded: %s", e)
        return False

    def _download_item(self, item: MediaItem):
        """Download item from real-debrid.com"""
        request_id = self.add_magnet(item)
        if not request_id:
            logger.error("Failed to add magnet for %s", item.log_string)
            return
        item.set("active_stream.id", request_id)
        self.set_active_files(item)
        time.sleep(0.5)  # Ensure the torrent is processed before selecting files
        if not self.select_files(request_id, item):
            logger.error("Failed to select files for %s", item.log_string)
            return
        item.set("active_stream.id", request_id)
        logger.info("Downloaded %s", item.log_string)

    def set_active_files(self, item: MediaItem) -> None:
        """Set active files for item from real-debrid.com"""
        try:
            info = self.get_torrent_info(item.get("active_stream")["id"])
            item.set("active_stream.alternative_name", info.original_filename)
            item.set("active_stream.name", info.filename)
        except Exception as e:
            logger.error("Failed to set active files for %s: %s", item.log_string, e)

    def is_cached(self, item: MediaItem) -> bool:
        """Check if item is cached on real-debrid.com"""
        processed_stream_hashes = set()
        filtered_streams = [hash for hash in item.streams if hash and hash not in processed_stream_hashes]

        for stream_chunk in self._chunks(filtered_streams, 5):
            streams = "/".join(stream_chunk)
            try:
                response = get(f"{RD_BASE_URL}/torrents/instantAvailability/{streams}/", additional_headers=self.auth_headers, response_type=dict)
                if response.is_ok:
                    for stream_hash, provider_list in response.data.items():
                        if stream_hash in processed_stream_hashes or len(provider_list) == 0:
                            continue
                        processed_stream_hashes.add(stream_hash)
                        if self._process_providers(item, provider_list, stream_hash):
                            return True
            except Exception as e:
                logger.error(f"Error checking cache for streams: {e}")

        item.set("streams", {})
        logger.debug("No cached streams found for %s", item.log_string)
        return False

    def _chunks(self, lst: List, n: int) -> Generator[List, None, None]:
        for i in range(0, len(lst), n):
            yield lst[i : i + n]

    def _process_providers(self, item: MediaItem, provider_list: dict, stream_hash: str) -> bool:
        for containers in provider_list.values():
            if not containers:
                # This hash is uncached (no files)
                continue
            for container in containers:
                # This hash is cached on real-debrid
                if self._is_wanted_files(container, item):
                    item.set("active_stream", {"hash": stream_hash, "files": container, "id": None})
                    return True
        return False

    def _is_wanted_files(self, container: dict, item: MediaItem) -> bool:
        filenames = [file["filename"] for file in container.values()]
        wanted = any(file.endswith(format) for format in WANTED_FORMATS for file in filenames)
        if not wanted:
            # Filenames dont match wanted formats
            return False
        if isinstance(item, Movie):
            # return wanted and all(file["filesize"] > 200000 for file in container.values())
            # can we break this down easier so its easy to follow
            for file in container.values():
                if file["filesize"] > 200000:
                    return True
        if isinstance(item, Season):
            # return wanted and all(any(episode.number in episodes_from_season(file, item.number) for file in filenames) for episode in item.episodes)
            for file in filenames:
                for episode in item.episodes:
                    if episode.number in episodes_from_season(file, item.number):
                        return True
        if isinstance(item, Episode):
            # return wanted and any(item.number in episodes_from_season(file, item.parent.number) for file in filenames)
            for file in filenames:
                for episode in item.parent.episodes:
                    if episode.number in episodes_from_season(file, item.parent.number):
                        return True
        return False

    def _set_file_paths(self, item: MediaItem):
        """Set file paths for item from real-debrid.com"""
        try:
            if isinstance(item, Movie):
                self._handle_movie_paths(item)
            elif isinstance(item, Season):
                self._handle_season_paths(item)
            elif isinstance(item, Episode):
                self._handle_episode_paths(item)
            else:
                logger.error("Item type not supported: %s", item.__class__.__name__)
        except Exception as e:
            logger.error("Failed to set file paths for %s: %s", item.log_string, e)

    def _handle_movie_paths(self, item: Movie):
        """Set file paths for movie from real-debrid.com"""
        try:
            item.set("folder", item.active_stream.get("name"))
            item.set("alternative_folder", item.active_stream.get("alternative_name", None))
            item.set("file", next(file for file in item.active_stream.get("files").values())["filename"])
        except Exception as e:
            logger.error("Failed to handle movie paths for %s: %s", item.log_string, e)

    def _handle_season_paths(self, season: Season):
        """Set file paths for season from real-debrid.com"""
        try:
            for file in season.active_stream["files"].values():
                for episode in episodes_from_season(file["filename"], season.number):
                    if episode - 1 in range(len(season.episodes)):
                        season.episodes[episode - 1].set("folder", season.active_stream.get("name"))
                        season.episodes[episode - 1].set("alternative_folder", season.active_stream.get("alternative_name"))
                        season.episodes[episode - 1].set("file", file["filename"])
        except Exception as e:
            logger.error("Failed to handle season paths for %s: %s", season.log_string, e)

    def _handle_episode_paths(self, episode: Episode):
        """Set file paths for episode from real-debrid.com"""
        try:
            file = next(file for file in episode.active_stream.get("files").values() if episode.number in episodes_from_season(file["filename"], episode.parent.number))
            episode.set("folder", episode.active_stream.get("name"))
            episode.set("alternative_folder", episode.active_stream.get("alternative_name"))
            episode.set("file", file["filename"])
        except Exception as e:
            logger.error("Failed to handle episode paths for %s: %s", episode.log_string, e)

    def add_magnet(self, item: MediaItem) -> str:
        """Add magnet link to real-debrid.com"""
        if not isinstance(item.active_stream, dict) or not item.active_stream.get("hash"):
            logger.error("No active stream or hash found for %s", item.log_string)
            return None

        try:
            hash = item.active_stream["hash"]
            response = post(
                f"{RD_BASE_URL}/torrents/addMagnet",
                {"magnet": f"magnet:?xt=urn:btih:{hash}&dn=&tr="},
                additional_headers=self.auth_headers,
            )
            if response.is_ok:
                return response.data.id
            logger.error("Failed to add magnet: %s", response.data)
        except Exception as e:
            logger.error("Error adding magnet for %s: %s", item.log_string, e)
        return None

    def get_torrents(self, limit: int) -> List[SimpleNamespace]:
        """Get torrents from real-debrid.com"""
        try:
            response = get(f"{RD_BASE_URL}/torrents?limit={str(limit)}", additional_headers=self.auth_headers)
            if response.is_ok and response.data:
                return response.data
        except Exception as e:
            logger.error("Failed to get torrents from Real-Debrid, site is probably down: %s", e)
        return []

    def select_files(self, request_id: str, item: MediaItem) -> bool:
        """Select files from real-debrid.com"""
        files = item.active_stream.get("files")
        if not files:
            logger.error("No files to select for %s", item.log_string)
            return False

        try:
            response = post(
                f"{RD_BASE_URL}/torrents/selectFiles/{request_id}",
                {"files": ",".join(files.keys())},
                additional_headers=self.auth_headers,
            )
            return response.is_ok
        except Exception as e:
            logger.error("Error selecting files for %s: %s", item.log_string, e)
            return False

    def get_torrent_info(self, request_id: str) -> dict:
        """Get torrent info from real-debrid.com"""
        try:
            response = get(f"{RD_BASE_URL}/torrents/info/{request_id}", additional_headers=self.auth_headers)
            if response.is_ok:
                return response.data
        except Exception as e:
            logger.error("Failed to get torrent info for %s: %s", request_id, e)
        return {}
