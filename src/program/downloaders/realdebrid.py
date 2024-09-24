from datetime import datetime

from loguru import logger
from requests import ConnectTimeout

import utils.request as request
from program.media.item import MediaItem
from program.settings.manager import settings_manager as settings
from utils.ratelimiter import RateLimiter

from .shared import VIDEO_EXTENSIONS, FileFinder

BASE_URL = "https://api.real-debrid.com/rest/1.0"

torrent_limiter = RateLimiter(1, 1)
overall_limiter = RateLimiter(60, 60)

class RealDebridDownloader:
    def __init__(self):
        self.key = "realdebrid"
        self.settings = settings.settings.downloaders.real_debrid
        self.initialized = self.validate()
        if self.initialized:
            self.existing_hashes = [torrent["hash"] for torrent in get_torrents(1000)]
            self.file_finder = FileFinder("filename", "filesize")

    def validate(self) -> bool:
        """Validate Real-Debrid settings and API key"""
        if not self.settings.enabled:
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

    def process_hashes(self, chunk: list[str], needed_media: dict, break_pointer: list[bool]) -> dict:
        cached_containers = self.get_cached_containers(chunk, needed_media, break_pointer)
        return cached_containers

    def download_cached(self, active_stream: dict) -> str:
        torrent_id = add_torrent(active_stream.get("infohash"))
        if torrent_id:
            self.existing_hashes.append(active_stream.get("infohash"))
            select_files(torrent_id, [file for file in active_stream.get("all_files").keys()])
            return torrent_id
        raise Exception("Failed to download torrent.")

    def get_cached_containers(self, infohashes: list[str], needed_media: dict, break_pointer: list[bool]) -> dict:
        cached_containers = {}
        response = get_instant_availability(infohashes)

        for infohash in infohashes:
            cached_containers[infohash] = {}
            if break_pointer[1] and break_pointer[0]:
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
                if break_pointer[1] and break_pointer[0]:
                    break
                if all_files_valid(container):
                    cached_containers[infohash] = self.file_finder.get_cached_container(needed_media, break_pointer, container)
                    if cached_containers[infohash]:
                        break_pointer[0] = True
                        if break_pointer[1]:
                            break
        return cached_containers

    def get_torrent_names(self, id: str) -> dict:
        info = torrent_info(id)
        return (info["filename"], info["original_filename"])

    def delete_torrent_with_infohash(self, infohash: str):
        id = next(torrent["id"] for torrent in get_torrents(1000) if torrent["hash"] == infohash)
        if id:
            delete_torrent(id)

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

def delete(url):
    return request.delete(
        url=f"{BASE_URL}/{url}",
        additional_headers={
        "Authorization": f"Bearer {settings.settings.downloaders.real_debrid.api_key}"},
        response_type=dict,
        specific_rate_limiter=torrent_limiter,
        overall_rate_limiter=overall_limiter,
        proxies=settings.settings.downloaders.real_debrid.proxy_url if settings.settings.downloaders.real_debrid.proxy_enabled else None
    ).data

def add_torrent(infohash: str) -> int:
    try:
        id = post(f"torrents/addMagnet", data={"magnet": f"magnet:?xt=urn:btih:{infohash}"})["id"]
    except:
        logger.warning(f"Failed to add torrent with infohash {infohash}")
        id = None
    return id

def select_files(id: str, files: list[str]):
    try:
        post(f"torrents/selectFiles/{id}", data={"files": ','.join(files)})
    except:
        logger.warning(f"Failed to select files for torrent with id {id}")

def torrent_info(id: str) -> dict:
    try:
        info = get(f"torrents/info/{id}")
    except:
        logger.warning(f"Failed to get info for torrent with id {id}")
        info = {}
    return info

def get_torrents(limit: int) -> list[dict]:
    try:
        torrents = get(f"torrents?limit={str(limit)}")
    except:
        logger.warning("Failed to get torrents.")
        torrents = []
    return torrents

def get_instant_availability(infohashes: list[str]) -> dict:
    try:
        data = get(f"torrents/instantAvailability/{'/'.join(infohashes)}")
        if isinstance(data, list):
            data = {}
    except:
        logger.warning("Failed to get instant availability.")
        data = {}
    return data

def delete_torrent(id):
    try:
        delete(f"torrents/delete/{id}")
    except:
        logger.warning(f"Failed to delete torrent with id {id}")