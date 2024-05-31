"""Realdebrid module"""

import contextlib
import time
import traceback
from os.path import splitext
from pathlib import Path
from types import SimpleNamespace
from typing import Generator, List, Union

from program.media.item import Episode, MediaItem, Movie, Season, Show
from program.media.state import States
from program.settings.manager import settings_manager
from requests import ConnectTimeout
from RTN import extract_episodes
from RTN.exceptions import GarbageTorrent
from RTN.parser import episodes_from_season, parse, title_match
from utils.logger import FileLogger, logger
from utils.request import get, ping, post

WANTED_FORMATS = {".mkv", ".mp4", ".avi"}
RD_BASE_URL = "https://api.real-debrid.com/rest/1.0"


class Debrid:
    """Real-Debrid API Wrapper"""

    def __init__(self, hash_cache):
        self.key = "realdebrid"
        self.settings = settings_manager.settings.real_debrid
        self.auth_headers = {"Authorization": f"Bearer {self.settings.api_key}"}
        self.initialized = self.validate()
        if not self.initialized:
            return
        self.hash_cache = hash_cache
        self.file_logger = FileLogger("Real-Debrid Manager", "green")
        self.file_logger.add_column("Item", style="cyan")
        self.file_logger.add_column("Filename", style="green")
        self.file_logger.add_column("Status", style="yellow")
        logger.success("Real Debrid initialized!")


    def validate(self) -> bool:
        """Validate Real-Debrid settings and API key"""
        if not self.settings.enabled:
            logger.warning("Real-Debrid is set to disabled")
            return False
        if not self.settings.api_key:
            logger.warning("Real-Debrid API key is not set")
            return False

        try:
            response = ping(f"{RD_BASE_URL}/user", additional_headers=self.auth_headers)
            if response.ok:
                user_info = response.json()
                return user_info.get("premium", 0) > 0
        except ConnectTimeout:
            logger.error("Connection to Real-Debrid timed out.")
        except Exception as e:
            logger.exception(f"Failed to validate Real-Debrid settings: {e}")
        return False

    def run(self, item: MediaItem) -> Generator[MediaItem, None, None]:
        """Download media item from real-debrid.com"""    
        if not self.is_cached(item):
            yield item
            return
        if not self._is_downloaded(item):
            self._download_item(item)
        self._set_file_paths(item)
        self.log_item(item)
        yield item

    @staticmethod
    def log_item(item: MediaItem) -> None:
        """Log the downloaded files for the item based on its type."""
        if isinstance(item, Movie):
            if hasattr(item, 'file'):
                logger.log("DEBRID", f"{item.state.name}: {item.log_string} with file: {item.file}")
            else:
                logger.log("DEBRID", f"No file to log for Movie: {item.title}")
        elif isinstance(item, Episode):
            if hasattr(item, 'file'):
                logger.log("DEBRID", f"{item.state.name}: {item.log_string} with file: {item.file}")
            else:
                logger.log("DEBRID", f"No file to log for Episode: {item.title} S{item.season_number}E{item.episode_number}")
        elif isinstance(item, Season):
            if hasattr(item, 'episodes') and item.episodes:
                for episode in item.episodes:
                    if hasattr(episode, 'file'):
                        logger.log("DEBRID", f"{episode.state.name}: {episode.log_string} with file: {episode.file}")
                    else:
                        logger.log("DEBRID", f"No file to log for Episode: {item.title} Season {item.season_number} Episode {episode.episode_number}")
            else:
                logger.log("DEBRID", f"No episodes to log for Season: {item.title} Season {item.season_number}")
        elif isinstance(item, Show):
            if hasattr(item, 'episodes') and item.episodes:
                for episode in item.episodes:
                    if hasattr(episode, 'file'):
                        logger.log("DEBRID", f"{episode.state.name}: {episode.log_string} with file: {episode.file}")
                    else:
                        logger.log("DEBRID", f"No file to log for Episode: {item.title} Season {item.season_number} Episode {episode.episode_number}")
            else:
                logger.log("DEBRID", f"No episodes to log for Season: {item.title} Season {item.season_number}")
        else:
            logger.log("DEBRID", f"Unsupported item type for logging: {type(item).__name__}")

    def _is_downloaded(self, item):
        """Check if item is already downloaded"""
        hash_key = item.active_stream.get("hash", None)
        if not hash_key:
            return False

        if self.hash_cache.is_blacklisted(hash_key):
            logger.log("DEBRID", f"Skipping download check for blacklisted hash: {hash_key}")
            return False

        if self.hash_cache.is_downloaded(hash_key):
            logger.log("DEBRID", f"Item already downloaded for hash: {hash_key}")

        torrents = self.get_torrents(1000)
        sorted_torrents = sorted(torrents.items(), key=lambda x: x[0])  # Sort torrents by hash key

        # Binary search for the hash_key in sorted list of torrents
        left, right = 0, len(sorted_torrents) - 1
        while left <= right:
            mid = (left + right) // 2
            if sorted_torrents[mid][0] < hash_key:
                left = mid + 1
            elif sorted_torrents[mid][0] > hash_key:
                right = mid - 1
            else:
                torrent = sorted_torrents[mid][1]
                if torrent.hash == hash_key:
                    info = self.get_torrent_info(torrent.id)
                    if self._matches_item(info, item):
                        # Cache this as downloaded
                        item.set("active_stream.id", torrent.id)
                        self.set_active_files(item)
                        if not self.hash_cache.is_downloaded(hash_key):
                            self.hash_cache.mark_downloaded(torrent.hash)
                        return True
                    else:
                        logger.debug(f"Torrent found but does not match item: {torrent.hash} != {hash_key}")
                        return False
            return False

    def _matches_item(self, torrent_info, item):
        """Check if the torrent info matches the item specifics."""
        if isinstance(item, Movie):
            result = False
            for file in torrent_info.files:
                logger.debug(f"Checking file: {file}")
                if file.selected == 1 and file.bytes > 200_000_000:  # 200,000,000 bytes is approximately 0.186 GB
                    result = True
                    break
            if result:
                file_size_gb = file.bytes / 1_000_000_000  # Convert bytes to gigabytes
                logger.debug(f"Matching found with {Path(file.path).name}, filesize: {file_size_gb:.2f} GB")
            return result
        if isinstance(item, Episode):
            one_season = len(item.parent.parent.seasons) == 1
            return any(
                file.selected == 1 and (
                    (item.number in extract_episodes(Path(file.path).name) and item.parent.number in extract_episodes(Path(file.path).name)) or
                    (one_season and item.number in extract_episodes(Path(file.path).name))
                )
                for file in torrent_info.files
            )
        elif isinstance(item, Season):
            # Check if all episodes of the season are present in the torrent
            season_number = item.number
            episodes_in_season = {episode.number for episode in item.episodes}
            matched_episodes = set()

            for file in torrent_info.files:
                if file.selected == 1:
                    file_episodes = extract_episodes(Path(file.path).name)
                    if season_number in file_episodes:
                        matched_episodes.update(file_episodes)

            # Check if all episodes in the season are matched
            return episodes_in_season == matched_episodes
        return False

    def _download_item(self, item: MediaItem):
        """Download item from real-debrid.com"""
        request_id = self.add_magnet(item)
        if not request_id:
            logger.error(f"Failed to add magnet for {item.log_string}")
            return

        item.set("active_stream.id", request_id)
        self.set_active_files(item)
        time.sleep(0.5)

        if not self.select_files(request_id, item):
            logger.error(f"Failed to select files for {item.log_string}")
            return

        item.set("active_stream.id", request_id)
        if not self.hash_cache.is_downloaded(item.active_stream["hash"]):
            self.hash_cache.mark_downloaded(item.active_stream["hash"])
            # self.file_logger.add_row(item.log_string, item.active_stream["name"], "Downloaded")
            # self.file_logger.log_table()

    def set_active_files(self, item: Union[Movie, Episode]) -> None:
        """Set active files for item from real-debrid.com"""
        info = self.get_torrent_info(item.get("active_stream")["id"])
        item.active_stream["alternative_name"] = info.original_filename
        item.active_stream["name"] = info.filename

    def _set_file_paths(self, item: MediaItem):
        """Set file paths for item from real-debrid.com"""
        if not item.active_stream.get("files"):
            logger.error(f"No files found for {item.log_string}")
            return

        if isinstance(item, Movie):
            self._is_wanted_movie(item.active_stream["files"], item)
        elif isinstance(item, Show):
            self._is_wanted_show(item.active_stream["files"], item)
        elif isinstance(item, Season):
            self._is_wanted_season(item.active_stream["files"], item)
        elif isinstance(item, Episode):
            self._is_wanted_episode(item.active_stream["files"], item)
        else:
            logger.error(f"Item type not supported to be downloaded {item.log_string}")

    def is_cached(self, item: MediaItem) -> bool:
        """Check if item is cached on real-debrid.com"""
        if not item.streams:
            logger.log("DEBRID", f"No streams found for {item.log_string}")
            return False

        logger.log("DEBRID", f"Processing {len(item.streams)} streams for {item.log_string}")

        processed_stream_hashes = set()
        filtered_streams = self._get_filtered_streams(item, processed_stream_hashes)
        if not filtered_streams:
            logger.log("NOT_FOUND", f"No streams found for {item.log_string}")
            return False

        for stream_chunk in self._chunks(filtered_streams, 5):
            if self._process_stream_chunk(stream_chunk, processed_stream_hashes, item):
                return True

        item.set("streams", {})
        logger.log("NOT_FOUND", f"No wanted cached streams found for {item.log_string}")
        return False

    def _process_stream_chunk(self, stream_chunk, processed_stream_hashes, item):
        """Process each stream chunk to check for availability and suitability."""
        streams = "/".join(stream_chunk)
        try:
            response = get(f"{RD_BASE_URL}/torrents/instantAvailability/{streams}/", additional_headers=self.auth_headers, response_type=dict)
            if response.is_ok:
                return self._evaluate_stream_response(response.data, processed_stream_hashes, item)
        except Exception:
            logger.exception("Error checking cache for streams")
        return False

    def _evaluate_stream_response(self, data, processed_stream_hashes, item):
        """Evaluate the response data from the stream availability check."""
        for stream_hash, provider_list in data.items():
            if stream_hash in processed_stream_hashes or self.hash_cache.is_blacklisted(stream_hash):
                continue
            if not provider_list or not provider_list.get("rd"):
                self.hash_cache.blacklist(stream_hash)
                continue
            processed_stream_hashes.add(stream_hash)
            if self._process_providers(item, provider_list, stream_hash):
                return True
            self.hash_cache.blacklist(stream_hash)
        return False

    def _get_filtered_streams(self, item: MediaItem, processed_stream_hashes: set) -> List[str]:
        """Get filtered streams for an item"""
        if isinstance(item, (Movie, Episode)):
            return [hash for hash in item.streams if hash and hash not in processed_stream_hashes]
        elif isinstance(item, Season):
            if not item.streams:
                return [hash for episode in item.episodes for hash in episode.streams if hash and hash not in processed_stream_hashes]
            return [hash for hash in item.streams if hash and hash not in processed_stream_hashes]
        logger.error(f"Item type not supported to be downloaded {item.log_string}")
        return []

    def _chunks(self, lst: List, n: int) -> Generator[List, None, None]:
        for i in range(0, len(lst), n):
            yield lst[i: i + n]

    def _process_providers(self, item: MediaItem, provider_list: dict, stream_hash: str) -> bool:
        """Process providers for an item"""
        if not provider_list or not stream_hash:
            return False

        # Sort containers by descending order of file count. 
        # This is to prioritize containers with more files.
        # Very important for handling shows/seasons/episodes
        # as we want to work with the most files possible.
        sorted_containers = sorted(
            (container for containers in provider_list.values() for container in containers),
            key=lambda container: -len(container)
        )

        for container in sorted_containers:
            if isinstance(item, Movie):
                if self._is_wanted_movie(container, item):
                    item.set("active_stream", {"hash": stream_hash, "files": container, "id": None})
                    return True
            elif isinstance(item, Show):
                if self._is_wanted_show(container, item):
                    item.set("active_stream", {"hash": stream_hash, "files": container, "id": None})
                    return True
            elif isinstance(item, Season):
                if self._is_wanted_season(container, item):
                    item.set("active_stream", {"hash": stream_hash, "files": container, "id": None})
                    return True
            elif isinstance(item, Episode):
                if self._is_wanted_episode(container, item):
                    item.set("active_stream", {"hash": stream_hash, "files": container, "id": None})
                    return True
        return False

    def _is_wanted_movie(self, container: dict, item: Movie) -> bool:
        """Check if container has wanted files for a movie"""
        if not isinstance(item, Movie):
            logger.error(f"Item is not a Movie instance: {item.log_string}")
            return False

        filenames = sorted(
            (file for file in container.values() if file and file["filesize"] > 2e+8 and splitext(file["filename"].lower())[1] in WANTED_FORMATS),
            key=lambda file: file["filesize"], reverse=True
        )

        for file in filenames:
            with contextlib.suppress(GarbageTorrent, TypeError):
                parsed_file = parse(file["filename"], remove_trash=True)
                if not parsed_file or not parsed_file.parsed_title:
                    continue
                if title_match(parsed_file.parsed_title, item.title):
                    item.set("folder", item.active_stream.get("name"))
                    item.set("alternative_folder", item.active_stream.get("alternative_name", None))
                    item.set("file", file["filename"])
                    return True
        return False

    def _is_wanted_episode(self, container: dict, item: Episode) -> bool:
        """Check if container has wanted files for an episode"""
        if not isinstance(item, Episode):
            logger.error(f"Item is not an Episode instance: {item.log_string}")
            return False

        filenames = [
            file for file in container.values()
            if file and file["filesize"] > 4e+7
            and splitext(file["filename"].lower())[1] in WANTED_FORMATS
        ]

        if not filenames:
            return False

        one_season = len(item.parent.parent.seasons) == 1

        for file in filenames:
            with contextlib.suppress(GarbageTorrent, TypeError):
                parsed_file = parse(file, remove_trash=True)
                if not parsed_file or not parsed_file.episode or 0 in parsed_file.season:
                    continue
                if item.number in parsed_file.episode and item.parent.number in parsed_file.season:
                    item.set("folder", item.active_stream.get("name"))
                    item.set("alternative_folder", item.active_stream.get("alternative_name"))
                    item.set("file", file)
                    return True
                elif one_season and item.number in parsed_file.episode:
                    item.set("folder", item.active_stream.get("name"))
                    item.set("alternative_folder", item.active_stream.get("alternative_name"))
                    item.set("file", file)
                    return True
        return False

    def _is_wanted_season(self, container: dict, item: Season) -> bool:
        """Check if container has wanted files for a season"""
        if not isinstance(item, Season):
            logger.error(f"Item is not a Season instance: {item.log_string}")
            return False

        # Filter and sort files once to improve performance
        filenames = [
            file for file in container.values()
            if file and file["filesize"] > 4e+7 and splitext(file["filename"].lower())[1] in WANTED_FORMATS
        ]

        if not filenames:
            return False

        needed_episodes = {episode.number: episode for episode in item.episodes if episode.state in [States.Indexed, States.Scraped, States.Unknown, States.Failed]}
        one_season = len(item.parent.seasons) == 1

        # Dictionary to hold the matched files for each episode
        matched_files = {}
        season_num = item.number

        # Parse files once and assign to episodes
        for file in filenames:
            with contextlib.suppress(GarbageTorrent, TypeError):
                parsed_file = parse(file["filename"], remove_trash=True)
                if not parsed_file or not parsed_file.episode or 0 in parsed_file.season:
                    continue
                # Check if the file's season matches the item's season or if there's only one season
                if season_num in parsed_file.season:
                    for ep_num in parsed_file.episode:
                        if ep_num in needed_episodes:
                            matched_files[ep_num] = file["filename"]
                elif one_season:
                    for ep_num in parsed_file.episode:
                        if ep_num in needed_episodes:
                            matched_files[ep_num] = file["filename"]
        if not matched_files:
            return False

        # Check if all needed episodes are captured
        if needed_episodes.keys() == matched_files.keys():
            # Set the necessary attributes for each episode
            for ep_num, filename in matched_files.items():
                ep = needed_episodes[ep_num]
                ep.set("folder", item.active_stream.get("name"))
                ep.set("alternative_folder", item.active_stream.get("alternative_name"))
                ep.set("file", filename)
            return True
        return False

    def _is_wanted_show(self, container: dict, item: Show) -> bool:
        """Check if container has wanted files for a show"""
        if not isinstance(item, Show):
            logger.error(f"Item is not a Show instance: {item.log_string}")
            return False

        # Filter and sort files once to improve performance
        filenames = [
            file for file in container.values()
            if file and file["filesize"] > 4e+7 and splitext(file["filename"].lower())[1] in WANTED_FORMATS
        ]

        if not filenames:
            return False

        # Create a dictionary to map seasons and episodes needed
        needed_episodes = {}
        acceptable_states = [States.Indexed, States.Scraped, States.Unknown, States.Failed]

        for season in item.seasons:
            if season.state in acceptable_states and season.is_released:
                needed_episode_numbers = {episode.number for episode in season.episodes if episode.state in acceptable_states and episode.is_released}
                if needed_episode_numbers:
                    needed_episodes[season.number] = needed_episode_numbers
        if not needed_episodes:
            return False

        # Dictionary to hold the matched files for each episode
        matched_files = {}

        # Iterate over each file to check if it matches any season and episode within the show
        for file in filenames:
            with contextlib.suppress(GarbageTorrent, TypeError):
                parsed_file = parse(file, remove_trash=True)
                if not parsed_file or not parsed_file.parsed_title or 0 in parsed_file.season:
                    continue
                # Check each season and episode to find a match
                for season_number, episodes in needed_episodes.items():
                    if season_number in parsed_file.season:
                        for episode_number in list(episodes):
                            if episode_number in parsed_file.episode:
                                # Store the matched file for this episode
                                matched_files[(season_number, episode_number)] = file
                                episodes.remove(episode_number)
        if not matched_files:
            return False

        # Check if all episodes were found
        all_found = all(len(episodes) == 0 for episodes in needed_episodes.values())

        if all_found:
            for (season_number, episode_number), file in matched_files.items():
                season = next(season for season in item.seasons if season.number == season_number)
                episode = next(episode for episode in season.episodes if episode.number == episode_number)
                episode.set("folder", item.active_stream.get("name"))
                episode.set("alternative_folder", item.active_stream.get("alternative_name", None))
                episode.set("file", file)
            return True
        return False


    ### API Methods for Real-Debrid below

    def add_magnet(self, item: MediaItem) -> str:
        """Add magnet link to real-debrid.com"""
        if not isinstance(item.active_stream, dict) or not item.active_stream.get("hash"):
            logger.error(f"No active stream or hash found for {item.log_string}")
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
            logger.error(f"Failed to add magnet: {response.data}")
        except Exception as e:
            logger.exception(f"Error adding magnet for {item.log_string}: {e}")
        return None

    def get_torrents(self, limit: int) -> dict[str, SimpleNamespace]:
        """Get torrents from real-debrid.com"""
        try:
            response = get(
                f"{RD_BASE_URL}/torrents?limit={str(limit)}",
                additional_headers=self.auth_headers
            )
            if response.is_ok and response.data:
                return {torrent.hash: torrent for torrent in response.data}
        except Exception as e:
            logger.exception(f"Failed to get torrents from Real-Debrid, site is probably down: {e}")
        return {}

    def select_files(self, request_id: str, item: MediaItem) -> bool:
        """Select files from real-debrid.com"""
        files = item.active_stream.get("files")
        # we need to make sure that every file is in our wanted formats
        files = {key: value for key, value in files.items() if splitext(value["filename"].lower())[1] in WANTED_FORMATS}

        if not files:
            logger.error(f"No files to select for {item.log_string}")
            return False

        try:
            response = post(
                f"{RD_BASE_URL}/torrents/selectFiles/{request_id}",
                {"files": ",".join(files.keys())},
                additional_headers=self.auth_headers,
            )
            return response.is_ok
        except Exception as e:
            logger.exception(f"Error selecting files for {item.log_string}: {e}")
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
            logger.exception(f"Failed to get torrent info for {request_id}: {e}")
        return {}
