"""Realdebrid module"""

import contextlib
import time
from datetime import datetime
from os.path import splitext
from pathlib import Path
from types import SimpleNamespace
from typing import Generator, List, Union

from program.media.item import Episode, MediaItem, Movie, Season, Show
from program.media.state import States
from program.settings.manager import settings_manager
from requests import ConnectTimeout
from RTN.exceptions import GarbageTorrent
from RTN.parser import parse
from RTN.patterns import extract_episodes
from utils.logger import logger
from utils.request import get, ping, post

WANTED_FORMATS = {".mkv", ".mp4", ".avi"}
RD_BASE_URL = "https://api.real-debrid.com/rest/1.0"


class Debrid:
    """Real-Debrid API Wrapper"""

    def __init__(self, hash_cache):
        self.key = "realdebrid"
        self.settings = settings_manager.settings.downloaders.real_debrid
        self.download_settings = settings_manager.settings.downloaders
        self.auth_headers = {"Authorization": f"Bearer {self.settings.api_key}"}
        self.proxy = self.settings.proxy_url if self.settings.proxy_enabled else None
        self.initialized = self.validate()
        if not self.initialized:
            return
        self.hash_cache = hash_cache
        logger.success("Real Debrid initialized!")

    def validate(self) -> bool:
        """Validate Real-Debrid settings and API key"""
        if not self.settings.enabled:
            logger.warning("Real-Debrid is set to disabled")
            return False
        if not self.settings.api_key:
            logger.warning("Real-Debrid API key is not set")
            return False
        if not isinstance(self.download_settings.movie_filesize_min, int) or self.download_settings.movie_filesize_min < -1:
            logger.error("Real-Debrid movie filesize min is not set or invalid.")
            return False
        if not isinstance(self.download_settings.movie_filesize_max, int) or self.download_settings.movie_filesize_max < -1:
            logger.error("Real-Debrid movie filesize max is not set or invalid.")
            return False
        if not isinstance(self.download_settings.episode_filesize_min, int) or self.download_settings.episode_filesize_min < -1:
            logger.error("Real-Debrid episode filesize min is not set or invalid.")
            return False
        if not isinstance(self.download_settings.episode_filesize_max, int) or self.download_settings.episode_filesize_max < -1:
            logger.error("Real-Debrid episode filesize max is not set or invalid.")
            return False
        if self.settings.proxy_enabled and not self.settings.proxy_url:
            logger.error("Proxy is enabled but no proxy URL is provided.")
            return False
        try:
            response = ping(f"{RD_BASE_URL}/user", additional_headers=self.auth_headers, proxies=self.proxy)
            if response.ok:
                user_info = response.json()
                username = user_info.get("username", "")
                premium_status = "Premium" if user_info.get("premium", 0) > 0 else "Not Premium"
                expiration = user_info.get("expiration", "")
                expiration_datetime = datetime.fromisoformat(expiration.replace('Z', '+00:00')).replace(tzinfo=None)
                time_left = expiration_datetime - datetime.utcnow().replace(tzinfo=None)
                days_left = time_left.days
                hours_left, minutes_left = divmod(time_left.seconds // 3600, 60)
                expiration_message = ""

                if days_left > 0:
                    expiration_message = f"Your account expires in {days_left} days."
                elif hours_left > 0:
                    expiration_message = f"Your account expires in {hours_left} hours and {minutes_left} minutes."
                else:
                    expiration_message = "Your account expires soon."

                if user_info.get("type", "") != "premium":
                    logger.log("DEBRID", "You are not a premium member.")
                    return False
                else:
                    logger.log("DEBRID", f"Hello {username}, your account is {premium_status}.")
                    logger.log("DEBRID", f"Expiration: {expiration_datetime}")
                    logger.log("DEBRID", expiration_message)

                return user_info.get("premium", 0) > 0
        except ConnectTimeout:
            logger.error("Connection to Real-Debrid timed out.")
        except Exception as e:
            logger.exception(f"Failed to validate Real-Debrid settings: {e}")
        return False


    def run(self, item: MediaItem) -> Generator[MediaItem, None, None]:
        """Download media item from real-debrid.com"""
        if (item.file and item.folder):
            yield None
            return
        if not self.is_cached(item):
            if isinstance(item, Season):
                res = [e for e in item.episodes]
                yield res
                return
            if isinstance(item, Show):
                res = [s for s in item.seasons]
                yield res
                return
            yield None
            return
        if not self._is_downloaded(item):
            self._download_item(item)
        self.log_item(item)
        yield item

    @staticmethod
    def log_item(item: MediaItem) -> None:
        """Log only the files downloaded for the item based on its type."""
        if isinstance(item, Movie):
            if item.file and item.folder:
                logger.log("DEBRID", f"Downloaded {item.log_string} with file: {item.file}")
            else:
                logger.debug(f"Movie item missing file or folder: {item.log_string}")
        elif isinstance(item, Episode):
            if item.file and item.folder:
                logger.log("DEBRID", f"Downloaded {item.log_string} with file: {item.file}")
            else:
                logger.debug(f"Episode item missing file or folder: {item.log_string}")
        elif isinstance(item, Season):
            for episode in item.episodes:
                if episode.file and episode.folder:
                    logger.log("DEBRID", f"Downloaded {episode.log_string} with file: {episode.file}")
                elif not episode.file:
                    logger.debug(f"Episode item missing file: {episode.log_string}")
                elif not episode.folder:
                    logger.debug(f"Episode item missing folder: {episode.log_string}")
        elif isinstance(item, Show):
            for season in item.seasons:
                for episode in season.episodes:
                    if episode.file and episode.folder:
                        logger.log("DEBRID", f"Downloaded {episode.log_string} with file: {episode.file}")
                    elif not episode.file:
                        logger.debug(f"Episode item missing file or folder: {episode.log_string}")
                    elif not episode.folder:
                        logger.debug(f"Episode item missing folder: {episode.log_string}")
        else:
            logger.debug(f"Unknown item type: {item.log_string}")

    def is_cached(self, item: MediaItem) -> bool:
        """Check if item is cached on real-debrid.com"""
        if not item.get("streams", {}):
            return False

        def _chunked(lst: List, n: int) -> Generator[List, None, None]:
            """Yield successive n-sized chunks from lst."""
            for i in range(0, len(lst), n):
                yield lst[i:i + n]

        logger.log("DEBRID", f"Processing {len(item.streams)} streams for {item.log_string}")

        processed_stream_hashes = set()
        filtered_streams = [hash for hash in item.streams if hash and hash not in processed_stream_hashes]
        if not filtered_streams:
            logger.log("NOT_FOUND", f"No streams found from filtering: {item.log_string}")
            return False

        for stream_chunk in _chunked(filtered_streams, 5):
            streams = "/".join(stream_chunk)
            try:
                response = get(f"{RD_BASE_URL}/torrents/instantAvailability/{streams}/", additional_headers=self.auth_headers, proxies=self.proxy, response_type=dict)
                if response.is_ok and self._evaluate_stream_response(response.data, processed_stream_hashes, item):
                    return True
            except Exception as e:
                logger.error(f"Error checking cache for streams: {str(e)}", exc_info=True)

        item.set("streams", {})
        logger.log("NOT_FOUND", f"No wanted cached streams found for {item.log_string} out of {len(filtered_streams)}")
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

    def _process_providers(self, item: MediaItem, provider_list: dict, stream_hash: str) -> bool:
        """Process providers for an item"""
        if not provider_list or not stream_hash:
            return False

        # Flatten and sort containers by descending order of file count.
        sorted_containers = sorted(
            (container for containers in provider_list.values() for container in containers),
            key=lambda container: -len(container)
        )

        if isinstance(item, Movie):
            for container in sorted_containers:
                if self._is_wanted_movie(container, item):
                    item.set("active_stream", {"hash": stream_hash, "files": container, "id": None})
                    return True
        elif isinstance(item, Show):
            for container in sorted_containers:
                if self._is_wanted_show(container, item):
                    item.set("active_stream", {"hash": stream_hash, "files": container, "id": None})
                    return True
        elif isinstance(item, Season):
            other_containers = [
                s for s in item.parent.seasons 
                if s != item and s.active_stream
                and s.state not in (States.Indexed, States.Unknown)
            ]
            for c in other_containers:
                if self._is_wanted_season(c.active_stream["files"], item):
                    item.set("active_stream", {"hash": c.active_stream["hash"], "files": c.active_stream["files"], "id": None})
                    return True
            for container in sorted_containers:
                if self._is_wanted_season(container, item):
                    item.set("active_stream", {"hash": stream_hash, "files": container, "id": None})
                    return True
        elif isinstance(item, Episode):
            for container in sorted_containers:
                if self._is_wanted_episode(container, item):
                    item.set("active_stream", {"hash": stream_hash, "files": container, "id": None})
                    return True
        # False if no cached files in containers (provider_list)
        return False

    def _is_wanted_movie(self, container: dict, item: Movie) -> bool:
        """Check if container has wanted files for a movie"""
        if not isinstance(item, Movie):
            logger.error(f"Item is not a Movie instance: {item.log_string}")
            return False

        min_size = self.download_settings.movie_filesize_min * 1_000_000
        max_size = self.download_settings.movie_filesize_max * 1_000_000 if self.download_settings.movie_filesize_max != -1 else float('inf')

        filenames = sorted(
            (file for file in container.values() if file and file["filesize"] > min_size 
            and file["filesize"] < max_size
            and splitext(file["filename"].lower())[1] in WANTED_FORMATS),
            key=lambda file: file["filesize"], reverse=True
        )

        if not filenames:
            return False

        for file in filenames:
            if not file or not file.get("filename"):
                continue
            with contextlib.suppress(GarbageTorrent, TypeError):
                parsed_file = parse(file["filename"], remove_trash=True)
                if not parsed_file or not parsed_file.parsed_title:
                    continue
                if parsed_file.type == "movie":
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

        min_size = self.download_settings.episode_filesize_min * 1_000_000
        max_size = self.download_settings.episode_filesize_max * 1_000_000 if self.download_settings.episode_filesize_max != -1 else float('inf')

        filenames = [
            file for file in container.values()
            if file and file["filesize"] > min_size
            and file["filesize"] < max_size
            and splitext(file["filename"].lower())[1] in WANTED_FORMATS
        ]

        if not filenames:
            return False

        one_season = len(item.parent.parent.seasons) == 1

        for file in filenames:
            if not file or not file.get("filename"):
                continue
            with contextlib.suppress(GarbageTorrent, TypeError):
                parsed_file = parse(file["filename"], remove_trash=True)
                if not parsed_file or not parsed_file.episode or 0 in parsed_file.season:
                    continue
                if item.number in parsed_file.episode and item.parent.number in parsed_file.season:
                    item.set("folder", item.active_stream.get("name"))
                    item.set("alternative_folder", item.active_stream.get("alternative_name"))
                    item.set("file", file["filename"])
                    return True
                elif one_season and item.number in parsed_file.episode:
                    item.set("folder", item.active_stream.get("name"))
                    item.set("alternative_folder", item.active_stream.get("alternative_name"))
                    item.set("file", file["filename"])
                    return True
        return False

    def _is_wanted_season(self, container: dict, item: Season) -> bool:
        """Check if container has wanted files for a season"""
        if not isinstance(item, Season):
            logger.error(f"Item is not a Season instance: {item.log_string}")
            return False

        min_size = self.download_settings.episode_filesize_min * 1_000_000
        max_size = self.download_settings.episode_filesize_max * 1_000_000 if self.download_settings.episode_filesize_max != -1 else float('inf')

        # Filter and sort files once to improve performance
        filenames = [
            file for file in container.values()
            if file and file["filesize"] > min_size
            and file["filesize"] < max_size
            and splitext(file["filename"].lower())[1] in WANTED_FORMATS
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
            if not file or not file.get("filename"):
                continue
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

        # Check if all needed episodes are captured (or atleast half)
        if (needed_episodes.keys() == matched_files.keys()):
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

        min_size = self.download_settings.episode_filesize_min * 1_000_000
        max_size = self.download_settings.episode_filesize_max * 1_000_000 if self.download_settings.episode_filesize_max != -1 else float('inf')

        # Filter and sort files once to improve performance
        filenames = [
            file for file in container.values()
            if file and file["filesize"] > min_size
            and file["filesize"] < max_size
            and splitext(file["filename"].lower())[1] in WANTED_FORMATS
        ]

        if not filenames:
            return False

        # Create a dictionary to map seasons and episodes needed
        needed_episodes = {}
        acceptable_states = [States.Indexed, States.Scraped, States.Unknown, States.Failed]

        for season in item.seasons:
            if season.state in acceptable_states and season.is_released_nolog:
                needed_episode_numbers = {episode.number for episode in season.episodes if episode.state in acceptable_states and episode.is_released_nolog}
                if needed_episode_numbers:
                    needed_episodes[season.number] = needed_episode_numbers
        if not needed_episodes:
            return False

        # Iterate over each file to check if it matches
        # the season and episode within the show
        matched_files = {}
        for file in filenames:
            with contextlib.suppress(GarbageTorrent, TypeError):
                parsed_file = parse(file["filename"], remove_trash=True)
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

        all_found = all(len(episodes) == 0 for episodes in needed_episodes.values())

        if all_found:
            for (season_number, episode_number), file in matched_files.items():
                season = next(season for season in item.seasons if season.number == season_number)
                episode = next(episode for episode in season.episodes if episode.number == episode_number)
                episode.set("folder", item.active_stream.get("name"))
                episode.set("alternative_folder", item.active_stream.get("alternative_name", None))
                episode.set("file", file.get("filename"))
            return True
        return False

    def _is_downloaded(self, item: MediaItem) -> bool:
        """Check if item is already downloaded after checking if it was cached"""
        hash_key = item.active_stream.get("hash", None)
        if not hash_key:
            logger.log("DEBRID", f"Item missing hash, skipping check: {item.log_string}")
            return False

        if self.hash_cache.is_blacklisted(hash_key):
            logger.log("DEBRID", f"Skipping download check for blacklisted hash: {hash_key}")
            return False

        if self.hash_cache.is_downloaded(hash_key) and item.active_stream.get("id", None):
            logger.log("DEBRID", f"Item already downloaded for hash: {hash_key}")
            return True

        logger.debug(f"Checking if torrent is already downloaded for item: {item.log_string}")
        torrents = self.get_torrents(1000)
        torrent = torrents.get(hash_key)

        if not torrent:
            logger.debug(f"No matching torrent found for hash: {hash_key}")
            return False

        if item.active_stream.get("id", None):
            logger.debug(f"Item already has an active stream ID: {item.active_stream.get('id')}")
            return True

        info = self.get_torrent_info(torrent.id)
        if not info or not hasattr(info, "files"):
            logger.debug(f"Failed to get torrent info for ID: {torrent.id}")
            self.hash_cache.blacklist(torrent.hash)
            return False

        if not _matches_item(info, item):
            self.hash_cache.blacklist(torrent.hash)
            return False

        # Cache this as downloaded
        logger.debug(f"Marking torrent as downloaded for hash: {torrent.hash}")
        self.hash_cache.mark_downloaded(torrent.hash)
        item.set("active_stream.id", torrent.id)
        self.set_active_files(item)
        logger.debug(f"Set active files for item: {item.log_string} with {len(item.active_stream.get('files', {}))} total files")
        return True

    def _download_item(self, item: MediaItem):
        """Download item from real-debrid.com"""
        logger.debug(f"Starting download for item: {item.log_string}")
        request_id = self.add_magnet(item) # uses item.active_stream.hash
        logger.debug(f"Magnet added to Real-Debrid, request ID: {request_id} for {item.log_string}")
        item.set("active_stream.id", request_id)
        self.set_active_files(item)
        logger.debug(f"Active files set for item: {item.log_string} with {len(item.active_stream.get('files', {}))} total files")
        time.sleep(0.5)
        self.select_files(request_id, item)
        logger.debug(f"Files selected for request ID: {request_id} for {item.log_string}")
        self.hash_cache.mark_downloaded(item.active_stream["hash"])
        logger.debug(f"Item marked as downloaded: {item.log_string}")

    def set_active_files(self, item: MediaItem) -> None:
        """Set active files for item from real-debrid.com"""
        active_stream = item.get("active_stream")
        if not active_stream or "id" not in active_stream:
            logger.error(f"Invalid active stream data for item: {item.log_string}")
            return

        info = self.get_torrent_info(active_stream["id"])
        if not info:
            logger.error(f"Failed to get torrent info for item: {item.log_string}")
            return

        item.active_stream["alternative_name"] = getattr(info, "original_filename", None)
        item.active_stream["name"] = getattr(info, "filename", None)

        if not item.folder or not item.alternative_folder:
            item.set("folder", item.active_stream.get("name"))
            item.set("alternative_folder", item.active_stream.get("alternative_name"))

        # this is only for Movie and Episode instances
        if isinstance(item, (Movie, Episode)):
            if not item.folder or not item.alternative_folder or not item.file:
                logger.error(f"Missing folder or alternative_folder or file for item: {item.log_string}")
                return
            
        if isinstance(item, Season) and item.folder:
            for episode in item.episodes:
                if episode.file and not episode.folder:
                    episode.set("folder", item.folder)
        
        if isinstance(item, Show) and item.folder:
            for season in item.seasons:
                for episode in season.episodes:
                    if episode.file and not episode.folder:
                        episode.set("folder", item.folder)

    def _is_wanted_item(self, item: Union[Movie, Episode, Season]) -> bool:
        """Check if item is wanted"""
        if isinstance(item, Movie):
            return self._is_wanted_movie(item.active_stream.get("files", {}), item)
        elif isinstance(item, Show):
            return self._is_wanted_show(item.active_stream.get("files", {}), item)
        elif isinstance(item, Season):
            return self._is_wanted_season(item.active_stream.get("files", {}), item)
        elif isinstance(item, Episode):
            return self._is_wanted_episode(item.active_stream.get("files", {}), item)
        else:
            logger.error(f"Unsupported item type: {type(item).__name__}")
            return False


    ### API Methods for Real-Debrid below

    def add_magnet(self, item: MediaItem) -> str:
        """Add magnet link to real-debrid.com"""
        if not item.active_stream.get("hash"):
            logger.error(f"No active stream or hash found for {item.log_string}")
            return None

        try:
            hash = item.active_stream.get("hash")
            response = post(
                f"{RD_BASE_URL}/torrents/addMagnet",
                {"magnet": f"magnet:?xt=urn:btih:{hash}&dn=&tr="},
                additional_headers=self.auth_headers,
                proxies=self.proxy
            )
            if response.is_ok:
                return response.data.id
            logger.error(f"Failed to add magnet: {response.data}")
        except Exception as e:
            logger.error(f"Error adding magnet for {item.log_string}: {e}")
        return None

    def get_torrent_info(self, request_id: str) -> dict:
        """Get torrent info from real-debrid.com"""
        if not request_id:
            logger.error("No request ID found")
            return {}

        try:
            response = get(
                f"{RD_BASE_URL}/torrents/info/{request_id}", 
                additional_headers=self.auth_headers,
                proxies=self.proxy
            )
            if response.is_ok:
                return response.data
        except Exception as e:
            logger.error(f"Error getting torrent info for {request_id or 'UNKNOWN'}: {e}")
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
                proxies=self.proxy
            )
            return response.is_ok
        except Exception as e:
            logger.error(f"Error selecting files for {item.log_string}: {e}")
            return False


    def get_torrents(self, limit: int) -> dict[str, SimpleNamespace]:
        """Get torrents from real-debrid.com"""
        try:
            response = get(
                f"{RD_BASE_URL}/torrents?limit={str(limit)}",
                additional_headers=self.auth_headers,
                proxies=self.proxy
            )
            if response.is_ok and response.data:
                # Example response.data: 
                # namespace(id='JXQWAQ5GPXJWG', filename='Kill Bill - The Whole Bloody Affair (2011) Reconstruction (1080p BluRay HEVC x265 10bit AC3 5.1)[DHB].mkv', hash='5336e4e408378d70593f3ec7ed7abf15480acedb', bytes=17253577745, host='real-debrid.com', split=2000, progress=100, status='downloaded', added='2024-06-01T15:18:44.000Z', links=['https://real-debrid.com/d/TWJXDFV2XS2T737NMKH4HISF24'], ended='2023-05-21T15:52:34.000Z')
                return {torrent.hash: torrent for torrent in response.data}
        except Exception as e:
            logger.error(f"Error getting torrents from Real-Debrid: {e}")
        return {}


## Helper functions for Real-Debrid below


def _matches_item(torrent_info: SimpleNamespace, item: MediaItem) -> bool:
    """Check if the downloaded torrent matches the item specifics."""
    logger.debug(f"Checking if torrent matches item: {item.log_string}")

    if not hasattr(torrent_info, "files"):
        logger.error(f"Torrent info for {item.log_string} does not have files attribute: {torrent_info}")
        return False

    def check_movie():
        for file in torrent_info.files:
            if file.selected == 1 and file.bytes > 200_000_000:
                file_size_mb = file.bytes / (1024 * 1024)
                if file_size_mb >= 1024:
                    file_size_gb = file_size_mb / 1024
                    logger.debug(f"Selected file: {Path(file.path).name} with size: {file_size_gb:.2f} GB")
                else:
                    logger.debug(f"Selected file: {Path(file.path).name} with size: {file_size_mb:.2f} MB")
                return True
        return False

    def check_episode():
        one_season = len(item.parent.parent.seasons) == 1
        item_number = item.number
        parent_number = item.parent.number
        for file in torrent_info.files:
            if file.selected == 1:
                file_episodes = extract_episodes(Path(file.path).name)
                if (item_number in file_episodes and parent_number in file_episodes) or (one_season and item_number in file_episodes):
                    logger.debug(f"File {Path(file.path).name} selected for episode {item_number} in season {parent_number}")
                    return True
        return False

    def check_season(season):
        season_number = season.number
        episodes_in_season = {episode.number for episode in season.episodes}
        matched_episodes = set()
        one_season = len(season.parent.seasons) == 1
        for file in torrent_info.files:
            if file.selected == 1:
                file_episodes = extract_episodes(Path(file.path).name)
                if season_number in file_episodes:
                    matched_episodes.update(file_episodes)
                elif one_season and file_episodes:
                    matched_episodes.update(file_episodes)
        return len(matched_episodes) >= len(episodes_in_season) // 2

    if isinstance(item, Movie):
        if check_movie():
            logger.info(f"{item.log_string} already exists in Real-Debrid account.")
            return True
    elif isinstance(item, Show):
        if all(check_season(season) for season in item.seasons):
            logger.info(f"{item.log_string} already exists in Real-Debrid account.")
            return True
    elif isinstance(item, Season):
        if check_season(item):
            logger.info(f"{item.log_string} already exists in Real-Debrid account.")
            return True
    elif isinstance(item, Episode):
        if check_episode():
            logger.info(f"{item.log_string} already exists in Real-Debrid account.")
            return True

    logger.debug(f"No matching item found for {item.log_string}")
    return False
