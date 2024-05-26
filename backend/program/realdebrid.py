"""Realdebrid module"""

import contextlib
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Generator, List

from program.media.state import States
from program.media.item import Episode, MediaItem, Movie, Season, Show
from program.settings.manager import settings_manager
from requests import ConnectTimeout
from RTN.parser import episodes_from_season, parse
from RTN.exceptions import GarbageTorrent
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
        if isinstance(item, (Movie, Episode)):
            if not item.active_stream.get("hash"):
                if not item.streams or not self.is_cached(item):
                    logger.error("No streams found for %s", item.log_string)
                    yield item
                    return

        elif isinstance(item, Season):
            # if it doesnt have any streams for any of its episodes,
            # or item.streams either, then we should skip it
            if item.streams:
                if not self.is_cached(item):
                    logger.error("No streams found for %s", item.log_string)
                    yield item
                    return
            else:
                if not any(self.is_cached(episode) for episode in item.episodes if episode.state == States.Scraped):
                    logger.error("No streams found for %s", item.log_string)
                    yield item
                    return

        # item should have active_stream set if cached by this point
        if not self._is_downloaded(item):
            # if not downloaded, download it
            self._download_item(item)
        # if downloaded, set file paths
        self._set_file_paths(item)
        yield item

    def _is_downloaded(self, item: MediaItem) -> bool:
        """Check if item is already downloaded"""
        try:
            torrents = self.get_torrents(2500)
            active_hash = item.active_stream.get("hash")
            for torrent in torrents:
                if torrent.hash == active_hash and torrent.status == "downloaded":
                    info = self.get_torrent_info(torrent.id)
                    if isinstance(item, Episode):
                        ep = item.number
                        if item.get("active_stream.id") == torrent.id:
                            logger.debug("Torrent for %s already downloaded for %s", item.log_string, info.filename)
                            self.set_active_files(item)
                            return True
                        for file in info.files:
                            if file.selected == 1:
                                if ep in episodes_from_season(Path(file.path).name, item.parent.number):
                                    logger.debug("Torrent for %s already downloaded for %s", item.log_string, info.filename)
                                    item.set("active_stream.id", torrent.id)
                                    self.set_active_files(item)
                                    return True
                    if isinstance(item, Season):
                        success = True
                        for episode in item.episodes:
                            if not self._is_episode_downloaded(episode, info):
                                success = False
                        if success:
                            item.set("active_stream.id", torrent.id)
                            return True
                    if isinstance(item, Movie):
                        if item.get("active_stream.id") == torrent.id:
                            logger.debug("Torrent for %s already downloaded for %s", item.log_string, info.filename)
                            self.set_active_files(item)
                            return True
                        for file in info.files:
                            if file.selected == 1:
                                logger.debug("Torrent for %s already downloaded for %s", item.log_string, info.filename)
                                item.set("active_stream.id", torrent.id)
                                self.set_active_files(item)
                                return True
        except Exception as e:
            logger.error("Error checking if item is downloaded: %s", e)
        return False

    def _is_episode_downloaded(self, episode: Episode, info: dict) -> bool:
        """Check if a specific episode is already downloaded"""
        for file in info.files:
            if file.selected == 1 and episode.number in episodes_from_season(Path(file.path).name, episode.parent.number):
                logger.debug("Episode %s already downloaded for %s", episode.log_string, info.filename)
                episode.set("active_stream.id", info["id"])
                self.set_active_files(episode)
                return True
        return False

    def _download_item(self, item: MediaItem):
        """Download item from real-debrid.com"""
        # we shouldn't be here if there is no active stream or id
        if not item.active_stream.get("hash"):
            logger.error("No active stream found for %s", item.log_string)
            return
        request_id = self.add_magnet(item) # This is always failing to add magnet. Why?
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
        filenames = [file["filename"] for file in item.active_stream.get("files").values()]
        for file in filenames:
            logger.debug("Downloaded file for %s: %s", item.log_string, file)

    def set_active_files(self, item: MediaItem) -> None:
        """Set active files for item from real-debrid.com"""
        try:
            info = self.get_torrent_info(item.get("active_stream")["id"])
            if not info:
                logger.error("No torrent info found for %s", item.log_string)
                return
            item.set("active_stream.alternative_name", info.original_filename)
            item.set("active_stream.name", info.filename)
            logger.debug("Set active files for %s", item.log_string)
        except Exception as e:
            logger.error("Failed to set active files for %s: %s", item.log_string, e)

    def is_cached(self, item: MediaItem) -> bool:
        """Check if item is cached on real-debrid.com"""
        processed_stream_hashes = set()
        if isinstance(item, (Movie, Episode)):
            filtered_streams = [hash for hash in item.streams if hash and hash not in processed_stream_hashes]
        elif isinstance(item, Season):
            if not item.streams:
                # lets check if any of the episodes have streams
                filtered_streams = [hash for episode in item.episodes for hash in episode.streams if hash and hash not in processed_stream_hashes]
            else:
                # if the season has streams, we can use them
                filtered_streams = [hash for hash in item.streams if hash and hash not in processed_stream_hashes]
        else:
            logger.error("Item type not supported: %s", item.log_string)
            return False

        if not filtered_streams:
            logger.debug("No streams found for %s", item.log_string)
            return False

        for stream_chunk in self._chunks(filtered_streams, 15):
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
        logger.debug("No wanted cached streams found for %s", item.log_string)
        return False

    def _chunks(self, lst: List, n: int) -> Generator[List, None, None]:
        for i in range(0, len(lst), n):
            yield lst[i : i + n]

    def _process_providers(self, item: MediaItem, provider_list: dict, stream_hash: str) -> bool:
        sorted_containers = sorted(provider_list, key=lambda x: len(provider_list[x]), reverse=True)
        for containers in sorted_containers:
            if not containers:
                continue
            for container in containers:
                if self._is_wanted_files(container, item):
                    item.set("active_stream", {"hash": stream_hash, "files": container, "id": None})
                    return True
        return False

    def _is_wanted_files(self, container: dict, item: MediaItem) -> bool:
        filenames = [file["filename"].lower() for file in container.values()]
        wanted = any(file.endswith(format) for format in WANTED_FORMATS for file in filenames)
        if not wanted:
            # Filenames dont match wanted formats
            return False
        if isinstance(item, Movie):
            for file in filenames:
                try:
                    parsed_data = parse(file, remove_trash=True)
                except GarbageTorrent:
                    continue

                if file["filesize"] > 200000 and parsed_data.title == item.title and parsed_data.year == item.aired_at.year:
                    return True
        if isinstance(item, Season):
            for file in filenames:
                for episode in item.episodes:
                    if episode.number in episodes_from_season(file, item.number):
                        return True
        if isinstance(item, Episode):
            for file in filenames:

                try:
                    parsed_data = parse(file, remove_trash=True)
                except GarbageTorrent:
                    continue

                for episode in item.parent.episodes:
                    eps_in_file = episodes_from_season(file, item.parent.number)
                    if episode.number in eps_in_file or [parsed_data.episode if item.parent.number == 1 and not eps_in_file else None]:
                        logger.debug("Episode %s is in file %s, marking wanted", episode.log_string, file)
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
        # <realdebrid._handle_episode_paths> - Failed to handle episode paths for 9-1-1 S07E03: 'NoneType' object has no attribute 'values'
        if not episode.active_stream.get("files"):
            logger.error("Failed to handle episode paths for %s: No files found", episode.log_string)
            return

        try:
            # file = next(file for file in episode.active_stream.get("files").values() if episode.number in episodes_from_season(file["filename"], episode.parent.number))
            # lets break it down so its easier to debug
            for file in episode.active_stream.get("files").values():
                if not episode.number in episodes_from_season(file["filename"], episode.parent.number):
                    logger.debug("Item %s is not in file %s", episode.log_string, file["filename"])
                    continue
                logger.debug("Setting file path for %s with file %s", episode.log_string, file["filename"])
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
