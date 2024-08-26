from datetime import datetime
from RTN import parse
from requests import ConnectTimeout
from program.media.item import MediaItem
from utils.ratelimiter import RateLimiter
from .shared import get_needed_media
import utils.request as request
from loguru import logger
from program.settings.manager import settings_manager as settings
import concurrent.futures

BASE_URL = "https://api.real-debrid.com/rest/1.0"
VIDEO_EXTENSIONS = [
    'mp4', 'mkv', 'avi', 'mov', 'wmv', 'flv', 'm4v', 'webm', 'mpg', 'mpeg', 'm2ts', 'ts'
]
torrent_limiter = RateLimiter(1, 1)
overall_limiter = RateLimiter(60, 60)

class RealDebridDownloader:
    def __init__(self):
        self.key = "realdebrid"
        self.existing_hashes = [torrent["hash"] for torrent in get_torrents(1000)]
        self.settings = settings.settings.downloaders.real_debrid
        self.initialized = self.validate()

    def validate(self) -> bool:
        """Validate Real-Debrid settings and API key"""
        if not self.settings.enabled:
            logger.warning("Real-Debrid is set to disabled")
            return False
        if not self.settings.api_key:
            logger.warning("Real-Debrid API key is not set")
            return False
        if self.settings.proxy_enabled and not self.settings.proxy_url:
            logger.error("Proxy is enabled but no proxy URL is provided.")
            return False
        try:
            user_info = get("/user")
            if user_info:
                expiration = user_info.get("expiration", "")
                expiration_datetime = datetime.fromisoformat(expiration.replace("Z", "+00:00")).replace(tzinfo=None)
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
                    logger.error("You are not a premium member.")
                    return False
                else:
                    logger.log("DEBRID", expiration_message)

                return user_info.get("premium", 0) > 0
        except ConnectTimeout:
            logger.error("Connection to Real-Debrid timed out.")
        except Exception as e:
            logger.exception(f"Failed to validate Real-Debrid settings: {e}")
        except:
            logger.error("Couldn't parse user data response from Real-Debrid.")
        return False

    def is_cached(self, item: MediaItem) -> bool:
        needed_media = get_needed_media(item)
        hashes = [stream.infohash for stream in item.streams]
        # Avoid duplicate torrents
        for hash in hashes:
            if hash in self.existing_hashes:
                hashes.remove(hash)
        chunks = [hashes[i:i + 5] for i in range(0, len(hashes), 5)]
        # Using a list to share the state, booleans are immutable
        break_pointer = [False]

        with concurrent.futures.ThreadPoolExecutor(thread_name_prefix="RealDebridDownloader") as executor:
            futures = []
            for chunk in chunks:
                future = executor.submit(process_hashes_chunk, chunk, needed_media, break_pointer)
                futures.append(future)

            # Wait for all futures to be done
            for future in concurrent.futures.as_completed(futures):
                result = future.result()
                if isinstance(result, dict):
                    item.active_stream = result
                    for future in futures:
                        future.cancel()

        if not item.active_stream.get("infohash", False):
            for stream in item.streams:
                item.blacklist_stream(stream)

        return break_pointer[0]

    def download_cached(self, item: MediaItem):
        torrent_id = add_torrent(item.active_stream.get("infohash"))
        select_files(torrent_id, [file for file in item.active_stream.get("all_files").keys()])
        info = torrent_info(torrent_id)
        update_item_attributes(item, info)


def get(url):
    return request.get(
        url=f"{BASE_URL}/{url}",
        additional_headers={"Authorization": f"Bearer {settings.settings.downloaders.real_debrid.api_key}"},
        response_type=dict,
        specific_rate_limiter=torrent_limiter,
        overall_rate_limiter=overall_limiter,
        proxies=settings.settings.downloaders.real_debrid.proxy_url if settings.settings.downloaders.real_debrid.proxy_enabled else None
    ).data

def post(url, data):
    return request.post(
        url=f"{BASE_URL}/{url}",
        data=data,
        response_type=dict,
        additional_headers={"Authorization": f"Bearer {settings.settings.downloaders.real_debrid.api_key}"},
        specific_rate_limiter=torrent_limiter,
        overall_rate_limiter=overall_limiter,
        proxies=settings.settings.downloaders.real_debrid.proxy_url if settings.settings.downloaders.real_debrid.proxy_enabled else None
    ).data

def add_torrent(infohash: str) -> int:
    return post(f"torrents/addMagnet", data={"magnet": f"magnet:?xt=urn:btih:{infohash}"})["id"]

def select_files(id: str, files: list[str]):
    post(f"torrents/selectFiles/{id}", data={"files": ','.join(files)})

def torrent_info(id: str) -> dict:
    return get(f"torrents/info/{id}")

def get_torrents(limit: int) -> list[dict]:
    return get(f"torrents?limit={str(limit)}")

def process_hashes_chunk(chunk: list[str], needed_media: dict, break_pointer: list[bool]) -> dict | bool:
    cached_containers = get_cached_chunked_containers(chunk, needed_media, break_pointer)
    for infohash, container in cached_containers.items():
        if container.get("matched_files"):
            return {"infohash": infohash, **container}
    return break_pointer[0]

def get_cached_chunked_containers(infohashes: list[str], needed_media: dict, break_pointer: list[bool] = [False]) -> dict:
    cached_containers = {}
    response = get(f"torrents/instantAvailability/{'/'.join(infohashes)}") or {}

    for infohash in infohashes:
        if break_pointer[0]:
            break
        data = response.get(infohash, {})
        if isinstance(data, list):
            containers = data
        elif isinstance(data, dict):
            containers = data.get("rd", [])
        else:
            containers = []
        # We avoid compressed downloads this way
        def all_files_valid(file_dict: dict) -> bool:
            return all(
                any(
                    file["filename"].endswith(f'.{ext}') and "sample" not in file["filename"].lower()
                    for ext in VIDEO_EXTENSIONS
                )
                for file in file_dict.values()
            )
        # Sort the container to have the longest length first
        containers.sort(key=lambda x: len(x), reverse=True)
        for container in containers:
            if break_pointer[0]:
                break
            if all_files_valid(container):
                if not needed_media or len(container) >= len([episode for season in needed_media for episode in needed_media[season]]):
                    matched_files = cache_matches(container, needed_media, break_pointer)
                    if matched_files:
                        cached_containers[infohash] = {"all_files": container, "matched_files": matched_files}
                        break_pointer[0] = True
                        break
        if not cached_containers.get(infohash):
            cached_containers[infohash] = {}
    return cached_containers

def filename_matches_show(filename):
    try:
        parsed_data = parse(filename)
        return parsed_data.season[0], parsed_data.episode
    except Exception:
        return None, None

def filename_matches_movie(filename):
    try:
        parsed_data = parse(filename)
        return parsed_data.type == "movie"
    except Exception:
        return None

def cache_matches(cached_files: dict, needed_media: dict[int, list[int]], break_pointer: list[bool] = [False]):
    if needed_media:
        # Convert needed_media to a set of (season, episode) tuples
        needed_episodes = {(season, episode) for season in needed_media for episode in needed_media[season]}
        matches_dict = {}

        for file in cached_files.values():
            if break_pointer[0]:
                break
            matched_season, matched_episodes = filename_matches_show(file["filename"])
            if matched_season and matched_episodes:
                for episode in matched_episodes:
                    if (matched_season, episode) in needed_episodes:
                        if matched_season not in matches_dict:
                            matches_dict[matched_season] = {}
                        matches_dict[matched_season][episode] = file
                        needed_episodes.remove((matched_season, episode))

        if not needed_episodes:
            return matches_dict
    else:
        for file in cached_files.values():
            matched_movie = filename_matches_movie(file["filename"])
            if matched_movie:
                return {1: {1: file}}

def update_item_attributes(item: MediaItem, info: dict):
    """ Update the item attributes with the downloaded files and active stream """
    matches_dict = item.active_stream.get("matched_files")
    item.folder = info["filename"]
    item.alternative_folder = info["original_filename"]
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
                    episode.folder = info["filename"]
                    episode.alternative_folder = info["original_filename"]
                    episode.active_stream = {**item.active_stream, "files": [ episode.file ] }
    elif item.type == "season":
        for episode in item.episodes:
            file = matches_dict.get(item.number, {}).get(episode.number, {})
            if file:
                episode.file = file["filename"]
                episode.folder = info["filename"]
                episode.alternative_folder = info["original_filename"]
                episode.active_stream = {**item.active_stream, "files": [ episode.file ] }
