"""Realdebrid module"""

import contextlib
import time
from pathlib import Path
import traceback
from types import SimpleNamespace
from typing import Generator, List
from dateutil import parser as dateutil_parser

from RTN import extract_episodes

from program.media.state import States
from program.media.item import Episode, MediaItem, Movie, Season
from program.settings.manager import settings_manager
from requests import ConnectTimeout
from RTN.parser import episodes_from_season, parse, title_match
from RTN.exceptions import GarbageTorrent
from utils.logger import logger
from utils.request import get, ping, post

WANTED_FORMATS = (".mkv", ".mp4", ".avi")
RD_BASE_URL = "https://api.real-debrid.com/rest/1.0"


class Debrid:
    """Real-Debrid API Wrapper"""

    def __init__(self):
        self.initialized = False
        self.settings = settings_manager.settings.real_debrid
        self.auth_headers = {"Authorization": f"Bearer {self.settings.api_key}"}
        self.running = False
        if not self._validate():
            logger.error("Realdebrid settings incorrect or not premium!")
            return
        logger.info("Real Debrid initialized!")
        self.initialized = True

    def _validate(self) -> bool:
        """Validate Real-Debrid settings and API key"""
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
        # lets check if we already downloaded this item
        if not self.is_cached(item):
            return
        if not self._is_downloaded(item):
            self._download_item(item)
        self._set_file_paths(item)
        yield item

    def _is_downloaded(self, item):
        """Check if item is already downloaded"""
        torrents = self.get_torrents(1000)
        for torrent in torrents:
            if torrent.hash == item.active_stream.get("hash", None):
                info = self.get_torrent_info(torrent.id)
                if isinstance(item, Episode):
                    if not any(
                        file
                        for file in info.files
                        if file.selected == 1
                        and item.number
                        in episodes_from_season(
                            item.parent.number, Path(file.path).name
                        )
                    ):
                        return False

                item.set("active_stream.id", torrent.id)
                self.set_active_files(item)
                logger.debug("Torrent for %s already downloaded with id %s", item.log_string, torrent.id)
                return True
        return False

    def _download_item(self, item: MediaItem):
        """Download item from real-debrid.com"""
        request_id = self.add_magnet(item)
        if not request_id:
            logger.error("Failed to add magnet for %s", item.log_string)
            return

        item.set("active_stream.id", request_id)
        self.set_active_files(item)
        time.sleep(0.5)

        if not self.select_files(request_id, item):
            logger.error("Failed to select files for %s", item.log_string)
            return
        
        item.set("active_stream.id", request_id)
        logger.info("Downloaded %s", item.log_string)

    def set_active_files(self, item):
        """Set active files for item from real-debrid.com"""
        info = self.get_torrent_info(item.get("active_stream")["id"])
        item.active_stream["alternative_name"] = info.original_filename
        item.active_stream["name"] = info.filename
        logger.debug("Set active files for %s", item.log_string)

    def is_cached(self, item: MediaItem) -> bool:
        """Check if item is cached on real-debrid.com"""
        processed_stream_hashes = set()
        filtered_streams = self._get_filtered_streams(item, processed_stream_hashes)
        if not filtered_streams:
            logger.debug("No streams found for %s", item.log_string)
            return False

        for stream_chunk in self._chunks(filtered_streams, 10):
            streams = "/".join(stream_chunk)
            try:
                response = get(f"{RD_BASE_URL}/torrents/instantAvailability/{streams}/", additional_headers=self.auth_headers, response_type=dict)
                if response.is_ok:
                    for stream_hash, provider_list in response.data.items():
                        if isinstance(provider_list, list) and not provider_list:
                            # uncached provider_list
                            continue
                        elif isinstance(provider_list, dict) and not provider_list.get("rd") or stream_hash in processed_stream_hashes:
                            # uncached provider_list
                            continue
                        processed_stream_hashes.add(stream_hash)
                        if self._process_providers(item, provider_list, stream_hash):
                            return True
            except Exception:
                logger.exception("Error checking cache for streams", traceback.format_exception_only)
        item.set("streams", {})
        logger.debug("No wanted cached streams found for %s", item.log_string)
        return False

    def _get_filtered_streams(self, item: MediaItem, processed_stream_hashes: set) -> List[str]:
        """Get filtered streams for an item"""
        if isinstance(item, (Movie, Episode)):
            return [hash for hash in item.streams if hash and hash not in processed_stream_hashes]
        elif isinstance(item, Season):
            if not item.streams:
                return [hash for episode in item.episodes for hash in episode.streams if hash and hash not in processed_stream_hashes]
            return [hash for hash in item.streams if hash and hash not in processed_stream_hashes]
        logger.error("Item type not supported to be downloaded %s", item.log_string)
        return []

    def _chunks(self, lst: List, n: int) -> Generator[List, None, None]:
        for i in range(0, len(lst), n):
            yield lst[i: i + n]

    def _process_providers(self, item: MediaItem, provider_list: dict, stream_hash: str) -> bool:
        """Process providers for an item"""
        if not provider_list:
            return False

        sorted_containers = sorted(
            (container for containers in provider_list.values() for container in containers),
            key=lambda container: -len(container)
        )

        for container in sorted_containers:
            if isinstance(item, Movie) and self._is_wanted_movie(container, item):
                item.set("active_stream", {"hash": stream_hash, "files": container, "id": None})
                return True
            if isinstance(item, Season) and self._is_wanted_season(container, item):
                item.set("active_stream", {"hash": stream_hash, "files": container, "id": None})
                return True
            if isinstance(item, Episode) and self._is_wanted_episode(container, item):
                item.set("active_stream", {"hash": stream_hash, "files": container, "id": None})
                return True
        return False


# for container in containers:
#     wanted_files = {}
#     if isinstance(item, Movie) and all(file["filesize"] > 200000 for file in container.values()):
#         wanted_files = container
#     if len(wanted_files) > 0 and all(item for item in wanted_files.values() if Path(item["filename"]).suffix in WANTED_FORMATS):
#         item.set(
#             "active_stream",
#             {"hash": stream_hash, "files": wanted_files, "id": None},
#         )
#         return True

    def _is_wanted_movie(self, container: dict, item: Movie) -> bool:
        """Check if container has wanted files for a movie"""
        filenames = [
            file["filename"] for file in container.values() 
            if file and file["filesize"] > 200000 
            and file["filename"].lower().endswith(WANTED_FORMATS)
        ]
        if not filenames:
            return False

        for file in filenames:
            try:
                parsed_file = parse(file, remove_trash=True)
            except GarbageTorrent:
                pass
            if title_match(parsed_file.parsed_title, item.title):
                logger.debug("Found wanted %s file '%s' for %s", parsed_file.type, file, item.log_string)
                return True
        return False

# for container in containers:
#     wanted_files = {}
#     if isinstance(item, Season) and all(any(episode.number in parser.episodes_in_season(item.number, file["filename"]) for file in container.values()) for episode in item.episodes):
#         wanted_files = container
#     if len(wanted_files) > 0 and all(item for item in wanted_files.values() if Path(item["filename"]).suffix in WANTED_FORMATS):
#         item.set(
#             "active_stream",
#             {"hash": stream_hash, "files": wanted_files, "id": None},
#         )
#         return True

    def _is_wanted_season(self, container: dict, item: Season) -> bool:
        """Check if container has wanted files for a season"""
#     if isinstance(item, Season) and all(any(episode.number in parser.episodes_in_season(item.number, file["filename"]) for file in container.values()) for episode in item.episodes):
        filenames = [
            file["filename"] for file in container.values() 
            if file and file["filesize"] > 40000 
            and file["filename"].lower().endswith(WANTED_FORMATS)
        ]

        if not filenames:
            return False

        check_all = all(
            any(episode.number in episodes_from_season(file, item.number) for episode in item.episodes)
            for file in filenames
        )

        if check_all:
            logger.debug("[Old Method] All episodes found in files for %s", item.log_string)
            return True

        episodes = [
            episode.number for episode in item.episodes
            if episode.state not in [States.Completed, States.Downloaded, States.Symlinked]
        ]

        # If previous method fails, try a new method
        needed_files = []
        for file in filenames:
            try:
                parsed_file = parse(file, remove_trash=True)
                if item.number in parsed_file.season:
                    needed_files.append(file)
                if len(needed_files) == len(episodes):
                    logger.debug("[New Method] All episodes found in files for %s", item.log_string)
                    break
            except GarbageTorrent:
                continue

        if needed_files:
            for file in needed_files:
                logger.debug("Season %s is in file %s, marking wanted", item.log_string, file)
                return True
        return False

            # eps_in_file = episodes_from_season(file, item.number)
            # if all(episode in eps_in_file for episode in episodes):
            # else:


# for container in containers:
#     wanted_files = {}
#     if isinstance(item, Episode) and any(item.number in parser.episodes_in_season(item.parent.number, episode["filename"]) for episode in container.values()):
#         wanted_files = container
#     if len(wanted_files) > 0 and all(item for item in wanted_files.values() if Path(item["filename"]).suffix in WANTED_FORMATS):
#         item.set(
#             "active_stream",
#             {"hash": stream_hash, "files": wanted_files, "id": None},
#         )
#         return True

    def _is_wanted_episode(self, container: dict, item: Episode) -> bool:
        """Check if container has wanted files for an episode"""
        filenames = [
            file["filename"] for file in container.values() 
            if file and file["filesize"] > 40000 
            and file["filename"].lower().endswith(WANTED_FORMATS)
        ]

        if not filenames:
            return False

        for file in filenames:
            try:
                parsed_file = parse(file, remove_trash=True)
            except GarbageTorrent:
                continue

            with contextlib.suppress(TypeError):
                eps_in_file = episodes_from_season(file, item.parent.number)
            if item.number in eps_in_file:
                logger.debug("Episode %s is in file %s, marking wanted", item.log_string, file)
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
            logger.debug("Set file path for %s with file %s", item.log_string, item.file)
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
                        logger.debug("Set file path for %s with file %s", season.episodes[episode - 1].log_string, file["filename"])
            logger.debug("Set file paths for %s", season.log_string)
        except Exception as e:
            logger.error("Failed to handle season paths for %s: %s", season.log_string, e)

    def _handle_episode_paths(self, episode: Episode):
        """Set file paths for episode from real-debrid.com"""
        if not episode.active_stream.get("files"):
            logger.error("Failed to handle episode paths for %s: No files found", episode.log_string)
            return

        try:
            for file in episode.active_stream.get("files").values():
                if episode.number in episodes_from_season(file["filename"], episode.parent.number):
                    logger.debug("Setting file path for %s with file %s", episode.log_string, file["filename"])
                    episode.set("folder", episode.active_stream.get("name"))
                    episode.set("alternative_folder", episode.active_stream.get("alternative_name"))
                    episode.set("file", file["filename"])
                    logger.debug("Set file path for %s with file %s", episode.log_string, file["filename"])
            logger.debug("Set file paths for %s", episode.log_string)
        except Exception as e:
            logger.error("Failed to handle episode paths for %s: %s", episode.log_string, e)


    ### API Methods for Real-Debrid below

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
            response = get(
                f"{RD_BASE_URL}/torrents?limit={str(limit)}",
                additional_headers=self.auth_headers
            )
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
        if not request_id:
            logger.error("No request ID found")
            return {}

        try:
            response = get(
                f"{RD_BASE_URL}/torrents/info/{request_id}", 
                additional_headers=self.auth_headers
            )
            if response.is_ok:
                return response.data
        except Exception as e:
            logger.error("Failed to get torrent info for %s: %s", request_id, e)
        return {}
