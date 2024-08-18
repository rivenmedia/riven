import contextlib
import time
from datetime import datetime
from os.path import splitext
from pathlib import Path
from types import SimpleNamespace
from typing import Generator, List

from sqlalchemy.orm import lazyload

from program.db.db import db
from program.db.db_functions import get_stream_count, load_streams_in_pages
from program.media.item import Episode, MediaItem, Movie, Season, Show
from program.media.state import States
from program.media.stream import Stream
from program.settings.manager import settings_manager
from requests import ConnectTimeout
from RTN.exceptions import GarbageTorrent
from RTN.parser import parse
from RTN.patterns import extract_episodes
from utils.logger import logger
from utils.ratelimiter import RateLimiter
from utils.request import get, ping, post

WANTED_FORMATS = {".mkv", ".mp4", ".avi"}
AD_BASE_URL = "https://api.alldebrid.com/v4"
AD_AGENT = "Riven"
AD_PARAM_AGENT = f"agent={AD_AGENT}"

class AllDebridDownloader:
    """All-Debrid API Wrapper"""

    def __init__(self):
        self.rate_limiter = None
        self.key = "alldebrid"
        self.settings = settings_manager.settings.downloaders.all_debrid
        self.download_settings = settings_manager.settings.downloaders
        self.auth_headers = {"Authorization": f"Bearer {self.settings.api_key}"}
        self.proxy = self.settings.proxy_url if self.settings.proxy_enabled else None
        self.inner_rate_limit = RateLimiter(12, 1)  # 12 requests per second
        self.overall_rate_limiter = RateLimiter(600, 60)  # 600 requests per minute
        self.initialized = self.validate()
        if not self.initialized:
            return
        logger.success("AllDebrid initialized!")

    def validate(self) -> bool:
        """Validate All-Debrid settings and API key"""
        if not self.settings.enabled:
            logger.warning("All-Debrid is set to disabled")
            return False
        if not self.settings.api_key:
            logger.warning("All-Debrid API key is not set")
            return False
        if not isinstance(self.download_settings.movie_filesize_min, int) or self.download_settings.movie_filesize_min < -1:
            logger.error("All-Debrid movie filesize min is not set or invalid.")
            return False
        if not isinstance(self.download_settings.movie_filesize_max, int) or self.download_settings.movie_filesize_max < -1:
            logger.error("All-Debrid movie filesize max is not set or invalid.")
            return False
        if not isinstance(self.download_settings.episode_filesize_min, int) or self.download_settings.episode_filesize_min < -1:
            logger.error("All-Debrid episode filesize min is not set or invalid.")
            return False
        if not isinstance(self.download_settings.episode_filesize_max, int) or self.download_settings.episode_filesize_max < -1:
            logger.error("All-Debrid episode filesize max is not set or invalid.")
            return False
        if self.settings.proxy_enabled and not self.settings.proxy_url:
            logger.error("Proxy is enabled but no proxy URL is provided.")
            return False
        try:
            response = ping(
                f"{AD_BASE_URL}/user?{AD_PARAM_AGENT}",
                additional_headers=self.auth_headers,
                proxies=self.proxy,
                specific_rate_limiter=self.inner_rate_limit,
                overall_rate_limiter=self.overall_rate_limiter)
            if response.is_ok:
                user_info = response.data.data.user
                expiration = user_info.premiumUntil or 0
                expiration_datetime = datetime.utcfromtimestamp(expiration)
                time_left = expiration_datetime - datetime.utcnow()
                days_left = time_left.days
                hours_left, minutes_left = divmod(time_left.seconds // 3600, 60)
                expiration_message = ""
    
                if days_left > 0:
                    expiration_message = f"Your account expires in {days_left} days."
                elif hours_left > 0:
                    expiration_message = f"Your account expires in {hours_left} hours and {minutes_left} minutes."
                else:
                    expiration_message = "Your account expires soon."
    
                if not user_info.isPremium or False:
                    logger.error("You are not a premium member.")
                    return False
                else:
                    logger.log("DEBRID", expiration_message)
    
                return user_info.isPremium or False
        except ConnectTimeout:
            logger.error("Connection to All-Debrid timed out.")
        except Exception as e:
            logger.exception(f"Failed to validate All-Debrid settings: {e}")
        return False

    def run(self, item: MediaItem) -> bool:
        """Download media item from all-debrid.com"""
        return_value = False
        if self.is_cached(item) and not self._is_downloaded(item):
            self._download_item(item)
            return_value = True
        self.log_item(item)
        return return_value

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
        """Check if item is cached on all-debrid.com"""
        if not item.get("streams", {}):
            return False
    
        logger.log("DEBRID", f"Processing streams for {item.log_string}")
    
        stream_count = get_stream_count(item._id)
        processed_stream_hashes = set()
        stream_hashes = {}  # This will store the infohash to Stream object mapping
    
        number_of_rows_per_page = 5
        total_pages = (stream_count // number_of_rows_per_page) + 1
    
        for page_number in range(total_pages):
            with db.Session() as session:
                for stream_id, infohash, stream in load_streams_in_pages(session, item._id, page_number, page_size=number_of_rows_per_page):
                    stream_hashes[infohash] = stream  # Store the Stream object
    
                    filtered_streams = [infohash for infohash in stream_hashes.keys() if infohash and infohash not in processed_stream_hashes]
                    if not filtered_streams:
                        logger.log("NOT_FOUND", f"No streams found from filtering: {item.log_string}")
                        return False
    
                    try:
                        params = {"agent": AD_AGENT}
                        for i, magnet in enumerate(filtered_streams):
                            params[f"magnets[{i}]"] = magnet
    
                        response = get(f"{AD_BASE_URL}/magnet/instant", params=params, additional_headers=self.auth_headers, proxies=self.proxy, response_type=dict, specific_rate_limiter=self.inner_rate_limit, overall_rate_limiter=self.overall_rate_limiter)
                        if response.is_ok and self._evaluate_stream_response(response.data, processed_stream_hashes, item, stream_hashes):
                            return True
                    except Exception as e:
                        logger.error(f"Error checking cache for streams: {str(e)}", exc_info=True)
    
        logger.log("NOT_FOUND", f"No wanted cached streams found for {item.log_string} after processing all chunks")
        return False

    def _evaluate_stream_response(self, data, processed_stream_hashes, item, stream_hashes):
        """Evaluate the response data from the stream availability check."""
        if data.get("status") != "success":
            logger.error("Failed to get a successful response")
            return False
    
        magnets = data.get("data", {}).get("magnets", [])
        for magnet in magnets:
            stream_hash = magnet.get("hash")
            stream_hash_lower = stream_hash.lower() if stream_hash else None
    
            # Skip if the stream has already been processed or if the hash is not valid
            if not stream_hash_lower or stream_hash_lower in processed_stream_hashes:
                continue
    
            # Mark the stream as processed
            processed_stream_hashes.add(stream_hash_lower)
    
            if not magnet.get("instant", False):
                continue
    
            stream = stream_hashes.get(stream_hash_lower)
            if self._process_providers(item, magnet, stream_hash_lower):
                return True
            else:
                if stream:
                    stream.blacklisted = True
    
        return False

    def _process_providers(self, item: MediaItem, magnet: dict, stream_hash: str) -> bool:
        """Process providers for an item"""
        if not magnet or not stream_hash:
            return False
    
        sorted_files = sorted(
            (file for file in magnet.get("files", [])),
            key=lambda file: file.get("s", 0),
            reverse=True
        )
    
        if isinstance(item, Movie):
            for file in sorted_files:
                if self._is_wanted_movie(file, item):
                    item.set("active_stream", {"hash": stream_hash, "files": magnet["files"], "id": None})
                    return True
        elif isinstance(item, Show):
            for file in sorted_files:
                if self._is_wanted_show(file, item):
                    item.set("active_stream", {"hash": stream_hash, "files": magnet["files"], "id": None})
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
            for file in sorted_files:
                if self._is_wanted_season(file, item):
                    item.set("active_stream", {"hash": stream_hash, "files": magnet["files"], "id": None})
                    return True
        elif isinstance(item, Episode):
            for file in sorted_files:
                if self._is_wanted_episode(file, item):
                    item.set("active_stream", {"hash": stream_hash, "files": magnet["files"], "id": None})
                    return True
        return False

    def _is_wanted_movie(self, file: dict, item: Movie) -> bool:
        """Check if file is wanted for a movie"""
        if not isinstance(item, Movie):
            logger.error(f"Item is not a Movie instance: {item.log_string}")
            return False
    
        min_size = self.download_settings.movie_filesize_min * 1_000_000
        max_size = self.download_settings.movie_filesize_max * 1_000_000 if self.download_settings.movie_filesize_max != -1 else float("inf")
    
        if not isinstance(file, dict) or file.get("s", 0) < min_size or file.get("s", 0) > max_size or splitext(file.get("n", "").lower())[1] not in WANTED_FORMATS:
            return False
    
        with contextlib.suppress(GarbageTorrent, TypeError):
            parsed_file = parse(file["n"], remove_trash=True)
            if parsed_file and parsed_file.type == "movie":
                item.set("folder", item.active_stream.get("name"))
                item.set("alternative_folder", item.active_stream.get("alternative_name", None))
                item.set("file", file["n"])
                return True
        return False

    def _is_wanted_episode(self, file: dict, item: Episode) -> bool:
        """Check if file is wanted for an episode"""
        if not isinstance(item, Episode):
            logger.error(f"Item is not an Episode instance: {item.log_string}")
            return False
    
        min_size = self.download_settings.episode_filesize_min * 1_000_000
        max_size = self.download_settings.episode_filesize_max * 1_000_000 if self.download_settings.episode_filesize_max != -1 else float("inf")
    
        if not isinstance(file, dict) or file.get("s", 0) < min_size or file.get("s", 0) > max_size or splitext(file.get("n", "").lower())[1] not in WANTED_FORMATS:
            return False
    
        one_season = len(item.parent.parent.seasons) == 1
    
        with contextlib.suppress(GarbageTorrent, TypeError):
            parsed_file = parse(file["n"], remove_trash=True)
            if parsed_file and item.number in parsed_file.episode and (item.parent.number in parsed_file.season or one_season):
                item.set("folder", item.active_stream.get("name"))
                item.set("alternative_folder", item.active_stream.get("alternative_name"))
                item.set("file", file["n"])
                return True
        return False

    def _is_wanted_season(self, files: list, item: Season) -> bool:
        """Check if files are wanted for a season"""
        if not isinstance(item, Season):
            logger.error(f"Item is not a Season instance: {item.log_string}")
            return False
    
        min_size = self.download_settings.episode_filesize_min * 1_000_000
        max_size = self.download_settings.episode_filesize_max * 1_000_000 if self.download_settings.episode_filesize_max != -1 else float("inf")
    
        filenames = [
            file for file in files
            if isinstance(file, dict) and file.get("s", 0) > min_size
               and file.get("s", 0) < max_size
               and splitext(file.get("n", "").lower())[1] in WANTED_FORMATS
        ]
    
        if not filenames:
            return False
    
        needed_episodes = {episode.number: episode for episode in item.episodes if episode.state in [States.Indexed, States.Scraped, States.Unknown, States.Failed]}
        one_season = len(item.parent.seasons) == 1
    
        matched_files = {}
        season_num = item.number
    
        for file in filenames:
            with contextlib.suppress(GarbageTorrent, TypeError):
                parsed_file = parse(file["n"], remove_trash=True)
                if parsed_file and (season_num in parsed_file.season or one_season):
                    for ep_num in parsed_file.episode:
                        if ep_num in needed_episodes:
                            matched_files[ep_num] = file["n"]
    
        if not matched_files:
            return False
    
        if needed_episodes.keys() == matched_files.keys():
            for ep_num, filename in matched_files.items():
                ep = needed_episodes[ep_num]
                ep.set("folder", item.active_stream.get("name"))
                ep.set("alternative_folder", item.active_stream.get("alternative_name"))
                ep.set("file", filename)
            return True
        return False

    def _is_wanted_show(self, files: list, item: Show) -> bool:
        """Check if files are wanted for a show"""
        if not isinstance(item, Show):
            logger.error(f"Item is not a Show instance: {item.log_string}")
            return False
    
        min_size = self.download_settings.episode_filesize_min * 1_000_000
        max_size = self.download_settings.episode_filesize_max * 1_000_000 if self.download_settings.episode_filesize_max != -1 else float("inf")
    
        filenames = [
            file for file in files
            if isinstance(file, dict) and file.get("s", 0) > min_size
               and file.get("s", 0) < max_size
               and splitext(file.get("n", "").lower())[1] in WANTED_FORMATS
        ]
    
        if not filenames:
            return False
    
        needed_episodes = {}
        acceptable_states = [States.Indexed, States.Scraped, States.Unknown, States.Failed]
    
        for season in item.seasons:
            if season.state in acceptable_states and season.is_released_nolog:
                needed_episode_numbers = {episode.number for episode in season.episodes if episode.state in acceptable_states and episode.is_released_nolog}
                if needed_episode_numbers:
                    needed_episodes[season.number] = needed_episode_numbers
        if not needed_episodes:
            return False
    
        matched_files = {}
        for file in filenames:
            with contextlib.suppress(GarbageTorrent, TypeError):
                parsed_file = parse(file["n"], remove_trash=True)
                if parsed_file:
                    for season_number, episodes in needed_episodes.items():
                        if season_number in parsed_file.season:
                            for episode_number in list(episodes):
                                if episode_number in parsed_file.episode:
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
                episode.set("file", file["n"])
            return True
        return False

    def _is_downloaded(self, item: MediaItem) -> bool:
        """Check if item is already downloaded after checking if it was cached"""
        hash_key = item.active_stream.get("hash", None)
        if not hash_key:
            logger.log("DEBRID", f"Item missing hash, skipping check: {item.log_string}")
            return False

        logger.debug(f"Checking if torrent is already downloaded for item: {item.log_string}")
        torrent = self.get_torrent(hash_key)
    
        if not torrent:
            logger.debug(f"No matching torrent found for hash: {hash_key}")
            return False
    
        if item.active_stream.get("id", None):
            logger.debug(f"Item already has an active stream ID: {item.active_stream.get('id')}")
            return True
    
        info = self.get_torrent_info(torrent.id)
        if not info or not hasattr(info, "links"):
            logger.debug(f"Failed to get torrent info for ID: {torrent.id}")
            return False
    
        if not self._matches_item(info, item):
            return False
    
        # Cache this as downloaded
        logger.debug(f"Marking torrent as downloaded for hash: {torrent.hash}")
        item.set("active_stream.id", torrent.id)
        self.set_active_files(item)
        logger.debug(f"Set active files for item: {item.log_string} with {len(item.active_stream.get('files', {}))} total files")
        return True

    def _download_item(self, item: MediaItem):
        """Download item from all-debrid.com"""
        logger.debug(f"Starting download for item: {item.log_string}")
        request_id = self.add_magnet(item)
        logger.debug(f"Magnet added to All-Debrid, request ID: {request_id} for {item.log_string}")
        item.set("active_stream.id", request_id)
        self.set_active_files(item)
        logger.debug(f"Active files set for item: {item.log_string} with {len(item.active_stream.get('files', {}))} total files")
        time.sleep(0.5)
        logger.debug(f"Item marked as downloaded: {item.log_string}")

    def set_active_files(self, item: MediaItem) -> None:
        """Set active files for item from all-debrid.com"""
        active_stream = item.get("active_stream")
        if not active_stream or "id" not in active_stream:
            logger.error(f"Invalid active stream data for item: {item.log_string}")
            return
    
        info = self.get_torrent_info(active_stream["id"])
        magnet_info = info.data.magnets
        if not info or not magnet_info or not magnet_info.filename:
            logger.error(f"Failed to get torrent info for item: {item.log_string}")
            return
    
        item.active_stream["alternative_name"] = magnet_info.filename
        item.active_stream["name"] = magnet_info.filename
    
        if not item.folder or not item.alternative_folder:
            item.set("folder", item.active_stream.get("name"))
            item.set("alternative_folder", item.active_stream.get("alternative_name"))
    
        # Ensure that the folder and file attributes are set
        if isinstance(item, (Movie, Episode)):
            if not item.file:
                for link in magnet_info.links:
                    if hasattr(link, "files"):
                        for file in link.files:
                            if isinstance(file, SimpleNamespace) and hasattr(file, "e"):
                                for subfile in file.e:
                                    if isinstance(item, Movie) and self._is_wanted_movie(subfile, item) or isinstance(item, Episode) and self._is_wanted_episode(subfile, item):
                                        item.set("file", subfile.n)
                                        break
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
    
        # Handle nested files in the links
        for link in magnet_info.links:
            if hasattr(link, "files"):
                for file in link.files:
                    if isinstance(file, SimpleNamespace) and hasattr(file, "e"):
                        for subfile in file.e:
                            if isinstance(item, Season) and self._is_wanted_season(link.files, item) or isinstance(item, Show) and self._is_wanted_show(link.files, item):
                                break
    
        if isinstance(item, Season) and item.folder:
            for episode in item.episodes:
                if episode.file and not episode.folder:
                    episode.set("folder", item.folder)
    
        if isinstance(item, Show) and item.folder:
            for season in item.seasons:
                for episode in season.episodes:
                    if episode.file and not episode.folder:
                        episode.set("folder", item.folder)
    
        # Handle nested files in the links
        for link in magnet_info.links:
            if hasattr(link, "files"):
                for file in link.files:
                    if isinstance(file, SimpleNamespace) and hasattr(file, "e"):
                        for subfile in file.e:
                            if isinstance(item, Season) and self._is_wanted_season(link.files, item) or isinstance(item, Show) and self._is_wanted_show(link.files, item):
                                break

    ### API Methods for All-Debrid below
    def add_magnet(self, item: MediaItem) -> str:
        """Add magnet link to All-Debrid"""
        if not item.active_stream.get("hash"):
            logger.error(f"No active stream or hash found for {item.log_string}")
            return None
    
        try:
            hash = item.active_stream.get("hash")
            params = {"agent": AD_AGENT}
            params["magnets[0]"] = hash
            response = post(
                f"{AD_BASE_URL}/magnet/upload",
                params=params,
                additional_headers=self.auth_headers,
                proxies=self.proxy,
                specific_rate_limiter=self.inner_rate_limit,
                overall_rate_limiter=self.overall_rate_limiter
            )
            if response.is_ok:
                data = response.data.data
                magnets = data.magnets or []
                if magnets:
                    return magnets[0].id
            logger.error(f"Failed to add magnet: {response.data}")
        except Exception as e:
            logger.error(f"Error adding magnet for {item.log_string}: {e}")
        return None

    def get_torrent_info(self, request_id: str) -> SimpleNamespace:
        """Get torrent info from All-Debrid"""
        if not request_id:
            logger.error("No request ID found")
            return SimpleNamespace()

        try:
            response = get(
                f"{AD_BASE_URL}/magnet/status?{AD_PARAM_AGENT}&id={request_id}",
                additional_headers=self.auth_headers,
                proxies=self.proxy,
                specific_rate_limiter=self.inner_rate_limit,
                overall_rate_limiter=self.overall_rate_limiter
            )
            if response.is_ok:
                return response.data
        except Exception as e:
            logger.error(f"Error getting torrent info for {request_id or 'UNKNOWN'}: {e}")
        return SimpleNamespace()

    def get_torrent(self, hash_key: str) -> dict[str, SimpleNamespace]:
        """Get torrents from All-Debrid"""
        try:
            response = get(
                f"{AD_BASE_URL}/magnet/status?{AD_PARAM_AGENT}&id={hash_key}",
                additional_headers=self.auth_headers,
                proxies=self.proxy,
                specific_rate_limiter=self.inner_rate_limit,
                overall_rate_limiter=self.overall_rate_limiter
            )
            if response.is_ok and response.data:
                magnets = getattr(response.data, "magnets", [])
                return {magnet.hash: SimpleNamespace(**magnet) for magnet in magnets}
        except Exception as e:
            logger.error(f"Error getting torrents from All-Debrid: {e}")
        return {}

    def _matches_item(torrent_info: SimpleNamespace, item: MediaItem) -> bool:
        """Check if the downloaded torrent matches the item specifics."""
        logger.debug(f"Checking if torrent matches item: {item.log_string}")
    
        if not hasattr(torrent_info, "files"):
            logger.error(f"Torrent info for {item.log_string} does not have files attribute: {torrent_info}")
            return False
    
        def check_movie():
            for file in torrent_info.files:
                if file["selected"] == 1 and file["size"] > 200_000_000:
                    file_size_mb = file["size"] / (1024 * 1024)
                    if file_size_mb >= 1024:
                        file_size_gb = file_size_mb / 1024
                        logger.debug(f"Selected file: {Path(file['path']).name} with size: {file_size_gb:.2f} GB")
                    else:
                        logger.debug(f"Selected file: {Path(file['path']).name} with size: {file_size_mb:.2f} MB")
                    return True
            return False
    
        def check_episode():
            one_season = len(item.parent.parent.seasons) == 1
            item_number = item.number
            parent_number = item.parent.number
            for file in torrent_info.files:
                if file["selected"] == 1:
                    file_episodes = extract_episodes(Path(file["path"]).name)
                    if (item_number in file_episodes and parent_number in file_episodes) or (one_season and item_number in file_episodes):
                        logger.debug(f"File {Path(file['path']).name} selected for episode {item_number} in season {parent_number}")
                        return True
            return False
    
        def check_season(season):
            season_number = season.number
            episodes_in_season = {episode.number for episode in season.episodes}
            matched_episodes = set()
            one_season = len(season.parent.seasons) == 1
            for file in torrent_info.files:
                if file["selected"] == 1:
                    file_episodes = extract_episodes(Path(file["path"]).name)
                    if season_number in file_episodes or one_season and file_episodes:
                        matched_episodes.update(file_episodes)
            return len(matched_episodes) >= len(episodes_in_season) // 2
    
        if isinstance(item, Movie):
            if check_movie():
                logger.info(f"{item.log_string} already exists in All-Debrid account.")
                return True
        elif isinstance(item, Show):
            if all(check_season(season) for season in item.seasons):
                logger.info(f"{item.log_string} already exists in All-Debrid account.")
                return True
        elif isinstance(item, Season):
            if check_season(item):
                logger.info(f"{item.log_string} already exists in All-Debrid account.")
                return True
        elif isinstance(item, Episode) and check_episode():
            logger.info(f"{item.log_string} already exists in All-Debrid account.")
            return True
    
        logger.debug(f"No matching item found for {item.log_string}")
        return False