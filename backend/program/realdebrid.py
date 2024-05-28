"""Realdebrid module"""

import contextlib
import time
from os.path import splitext
from pathlib import Path
from types import SimpleNamespace
from typing import Generator, List

from program.media.item import Episode, MediaItem, Movie, Season, Show
from program.media.state import States
from program.settings.manager import settings_manager
from requests import ConnectTimeout
from RTN import extract_episodes
from RTN.exceptions import GarbageTorrent
from RTN.parser import episodes_from_season, parse, title_match
from utils.logger import logger, FileLogger
from utils.request import get, ping, post

WANTED_FORMATS = {".mkv", ".mp4", ".avi"}
RD_BASE_URL = "https://api.real-debrid.com/rest/1.0"


class Debrid:
    """Real-Debrid API Wrapper"""

    def __init__(self, hash_cache):
        self.initialized = False
        self.settings = settings_manager.settings.real_debrid
        self.auth_headers = {"Authorization": f"Bearer {self.settings.api_key}"}
        self.running = False
        if not self._validate():
            logger.error("Realdebrid settings incorrect or not premium!")
            return
        logger.success("Real Debrid initialized!")
        self.hash_cache = hash_cache
        self.file_logger = FileLogger("Real-Debrid Manager", "green")
        self.file_logger.add_column("Item", style="cyan")
        self.file_logger.add_column("Filename", style="green")
        self.file_logger.add_column("Status", style="yellow")
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
            logger.exception(f"Failed to validate Real-Debrid settings: {e}")
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
        hash_key = item.active_stream.get("hash", None)
        
        # Check cache first to see if we already know the download status
        if self.hash_cache.is_blacklisted(hash_key):
            logger.log("DEBRID", f"Skipping download check for blacklisted hash: {hash_key}")
            return False

        # Check if the hash is already marked as downloaded in the cache
        if self.hash_cache.is_downloaded(hash_key):
            logger.log("DEBRID", f"Item already downloaded for hash: {hash_key}")
            return True

        # If not in cache, check Real-Debrid torrents
        torrents = self.get_torrents(1000)
        for torrent in torrents:
            if torrent.hash == hash_key:
                info = self.get_torrent_info(torrent.id)
                if self._matches_item(info, item):
                    # Cache this as downloaded
                    item.set("active_stream.id", torrent.id)
                    self.set_active_files(item)
                    logger.log("DEBRID", f"Torrent for {item.log_string} already downloaded with id {torrent.id}")
                    self.hash_cache.mark_as_downloaded(torrent.hash)
                    return True

        # If no matching torrent found, blacklist this hash to avoid rechecking
        self.hash_cache.blacklist(hash_key)
        return False

    def _matches_item(self, torrent_info, item):
        """Check if the torrent info matches the item specifics."""
        if isinstance(item, Movie):
            return any(
                file.selected == 1 and file.filesize > 200000000 for file in torrent_info.files
            )
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
            self.hash_cache.mark_as_downloaded(item.active_stream["hash"])
        # logger.log("DEBRID", f"Downloaded {item.log_string}")
        if item.active_stream.get("name"):
            self.file_logger.add_row(item.log_string, item.active_stream["name"], "Downloaded")
        self.file_logger.log_table()

    def set_active_files(self, item):
        """Set active files for item from real-debrid.com"""
        info = self.get_torrent_info(item.get("active_stream")["id"])
        item.active_stream["alternative_name"] = info.original_filename
        item.active_stream["name"] = info.filename

    def is_cached(self, item: MediaItem) -> bool:
        """Check if item is cached on real-debrid.com"""
        processed_stream_hashes = set()
        filtered_streams = self._get_filtered_streams(item, processed_stream_hashes)
        if not filtered_streams:
            logger.log("NOT_FOUND", f"No streams found for {item.log_string}")
            return False

        for stream_chunk in self._chunks(filtered_streams, 10):
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

    def _is_wanted_movie(self, container: dict, item: Movie) -> bool:
        """Check if container has wanted files for a movie"""
        if not isinstance(item, Movie):
            logger.error(f"Item is not a Movie instance: {item.log_string}")
            return False

        # also sort by highest filesize too
        # so we are selecting the movie instead of movie extras
        filenames = sorted(
            [file for file in container.values() 
            if file and file["filesize"] > 200000  # 200 MB
            and splitext(file["filename"].lower())[1] in WANTED_FORMATS],
            key=lambda file: file["filesize"],
            reverse=True
        )

        if not filenames:
            return False

        for file in filenames:
            with contextlib.suppress(GarbageTorrent, TypeError):
                parsed_file = parse(file, remove_trash=True)
                if not parsed_file or not parsed_file.title:
                    continue
                if title_match(parsed_file.parsed_title, item.title):
                    item.set("folder", item.active_stream.get("name"))
                    item.set("alternative_folder", item.active_stream.get("alternative_name", None))
                    item.set("file", file)
                    logger.log("DEBRID", f"Movie found for {item.log_string}")
                    return True
        return False

    def _is_wanted_episode(self, container: dict, item: Episode) -> bool:
        """Check if container has wanted files for an episode"""
        if not isinstance(item, Episode):
            logger.error(f"Item is not an Episode instance: {item.log_string}")
            return False

        filenames = [
            file["filename"] for file in container.values() 
            if file and file["filesize"] > 40000 
            and splitext(file["filename"].lower())[1] in WANTED_FORMATS
        ]

        if not filenames:
            return False

        one_season = False
        if isinstance(item, Show):
            one_season = len(item.seasons) == 1
        elif isinstance(item, Season):
            one_season = len(item.parent.seasons) == 1
        elif isinstance(item, Episode):
            one_season = len(item.parent.parent.seasons) == 1

        for file in filenames:
            with contextlib.suppress(GarbageTorrent, TypeError):
                parsed_file = parse(file, remove_trash=True)
                if not parsed_file or not parsed_file.episode:
                    continue
                if (item.number in parsed_file.episode and item.parent.number in parsed_file.season) or (one_season and item.number in parsed_file.episode):
                    item.set("folder", item.active_stream.get("name"))
                    item.set("alternative_folder", item.active_stream.get("alternative_name"))
                    item.set("file", file)
                    logger.log("DEBRID", f"Episode found for {item.log_string}")
                    return True
        return False

    def _is_wanted_show(self, container: dict, item: Show) -> bool:
        """Check if container has wanted files for a show"""
        if not isinstance(item, Show):
            logger.error(f"Item is not a Show instance: {item.log_string}")
            return False

        filenames = [
            file["filename"] for file in container.values()
            if file and file["filesize"] > 40000
            and splitext(file["filename"].lower())[1] in WANTED_FORMATS
        ]

        if not filenames:
            return False

        # Create a dictionary to map seasons and episodes needed
        needed_episodes = {}
        acceptable_states = [States.Indexed, States.Scraped, States.Unknown, States.Failed]

        for season in item.seasons:
            if season.state in acceptable_states and season.is_released:
                needed_episode_numbers = set()
                for episode in season.episodes:
                    if episode.state in acceptable_states and episode.is_released:
                        needed_episode_numbers.add(episode.number)
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
                if not parsed_file or not parsed_file.show:
                    continue
                if parsed_file.show == item.title:
                    # Check each season and episode to find a match
                    for season_number, episodes in needed_episodes.items():
                        if parsed_file.season == season_number:
                            for episode_number in list(episodes):
                                if parsed_file.episode == episode_number:
                                    # Store the matched file for this episode
                                    matched_files[(season_number, episode_number)] = file
                                    episodes.remove(episode_number)
        if not matched_files:
            return False

        # Check if all episodes were found
        all_found = all(len(episodes) == 0 for episodes in needed_episodes.values())

        if all_found:
            # Set details for each episode that has a matched file
            for (season_number, episode_number), file in matched_files.items():
                season = next(season for season in item.seasons if season.number == season_number)
                episode = next(episode for episode in season.episodes if episode.number == episode_number)
                episode.set("folder", item.active_stream.get("name"))
                episode.set("alternative_folder", item.active_stream.get("alternative_name", None))
                episode.set("file", file)
                logger.log("DEBRID", f"Episode found for {item.log_string}: {episode.log_string}")
            return True
        return False

    def _is_wanted_season(self, container: dict, item: Season) -> bool:
        """Check if container has wanted files for a season"""
        if not isinstance(item, Season):
            logger.error(f"Item is not a Season instance: {item.log_string}")
            return False

        filenames = [
            file["filename"] for file in container.values()
            if file and file["filesize"] > 40000
            and splitext(file["filename"].lower())[1] in WANTED_FORMATS
        ]

        if not filenames:
            return False

        # Check if all episodes are in files
        if self._check_all_episodes_in_files(filenames, item):
            return True

        # Retry with a different method if the first check fails
        return self._retry_check_episodes_in_files(filenames, item)

    def _check_all_episodes_in_files(self, filenames, item):
        """Check if all episodes are present in the provided filenames"""
        if not isinstance(item, Season):
            logger.error(f"Item is not a Season instance: {item.log_string}")
            return False

        check_all = all(
            any(episode.number in episodes_from_season(file, item.number) for episode in item.episodes)
            for file in filenames
        )

        if check_all:
            self._assign_files_to_episodes(filenames, item)
            return True
        return False

    def _retry_check_episodes_in_files(self, filenames, item):
        """Retry checking episodes in files with a different approach"""
        if not isinstance(item, Season):
            logger.error(f"Item is not a Season instance: {item.log_string}")
            return False

        episodes = [
            episode.number for episode in item.episodes
            if episode.state in [States.Indexed, States.Scraped, States.Unknown]
            and episode.is_released
        ]

        needed_files = []
        for file in filenames:
            with contextlib.suppress(GarbageTorrent, TypeError):
                parsed_file = parse(file, remove_trash=True)
                if not parsed_file.episode:
                    continue
                if any(parsed_episode in episodes for parsed_episode in parsed_file.episode):
                    if len(item.parent.seasons) == 1 or item.number in parsed_file.season:
                        needed_files.append(file)
                    if len(needed_files) == len(episodes):
                        break

        if len(needed_files) == len(episodes):
            self._assign_files_to_episodes(needed_files, item)
            return True
        return False

    # def _assign_files_to_episodes(self, filenames, item):
    #     """Assign files to episodes based on the filenames"""
    #     for file in filenames:
    #         for episode in extract_episodes(file):
    #             if episode - 1 in range(len(item.episodes)):
    #                 item.episodes[episode - 1].set("folder", item.active_stream.get("name"))
    #                 item.episodes[episode - 1].set("alternative_folder", item.active_stream.get("alternative_name"))
    #                 item.episodes[episode - 1].set("file", file)
    #                 logger.log("DEBRID", f"Episode found for {item.episodes[episode - 1].log_string}")

    def _assign_files_to_episodes(self, filenames, item):
        """Assign files to episodes based on the filenames"""
        for file in filenames:
            for episode in extract_episodes(file):
                if episode - 1 in range(len(item.episodes)):
                    episode_obj = item.episodes[episode - 1]
                    if not self.hash_cache.is_downloaded(episode_obj.active_stream.get("hash")):
                        episode_obj.set("folder", item.active_stream.get("name"))
                        episode_obj.set("alternative_folder", item.active_stream.get("alternative_name"))
                        episode_obj.set("file", file)
                        logger.log("DEBRID", f"Episode found and processed for {episode_obj.log_string}")


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
            logger.exception(f"Failed to get torrents from Real-Debrid, site is probably down: {e}")
        return []

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
