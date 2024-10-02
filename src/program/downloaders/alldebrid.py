from datetime import datetime

from loguru import logger
from program.settings.manager import settings_manager as settings
from requests import ConnectTimeout
from typing import Optional
from utils import request
from utils.ratelimiter import RateLimiter

from .shared import VIDEO_EXTENSIONS, FileFinder, DownloaderBase, premium_days_left, hash_from_uri
from .shared import DebridTorrentId, InfoHash # Types

AD_BASE_URL = "https://api.alldebrid.com/v4"
AD_AGENT = "Riven"

inner_rate_limit = RateLimiter(12, 1)  # 12 requests per second
overall_rate_limiter = RateLimiter(600, 60)  # 600 requests per minute


class AllDebridDownloader(DownloaderBase):
    """All-Debrid API Wrapper"""

    def __init__(self):
        self.key = "alldebrid"
        self.settings = settings.settings.downloaders.all_debrid
        self.initialized = self.validate()
        if self.initialized:
            self.existing_hashes = [torrent["hash"] for torrent in get_torrents()]
            self.file_finder = FileFinder("filename", "filesize")
            logger.success("AllDebrid initialized!")

    def validate(self) -> bool:
        """Validate All-Debrid settings and API key"""
        if not self.settings.enabled:
            return False
        if not self.settings.api_key:
            logger.warning("All-Debrid API key is not set")
            return False
        if self.settings.proxy_enabled and not self.settings.proxy_url:
            logger.error("Proxy is enabled but no proxy URL is provided.")
            return False
        try:
            user_info = get_user()
            if user_info:
                user = user_info.get("data", {}).get("user", {})
                expiration = user.get("premiumUntil", 0)
                expiration_datetime = datetime.utcfromtimestamp(expiration)
                expiration_message = premium_days_left(expiration_datetime)

                premium = bool(user.get("isPremium", False))
                if not premium:
                    logger.error("You are not a premium member.")
                    return False
                else:
                    logger.log("DEBRID", expiration_message)

                return premium
        except ConnectTimeout:
            logger.error("Connection to All-Debrid timed out.")
        except Exception as e:
            logger.exception(f"Failed to validate All-Debrid settings: {e}")
        return False

    def process_hashes(
        self, chunk: list[InfoHash], needed_media: dict, break_pointer: list[bool]
    ) -> dict:
        return self.get_cached_containers(chunk, needed_media, break_pointer)

    def download_cached(self, active_stream: dict) -> DebridTorrentId:
        torrent_id = add_torrent(active_stream.get("infohash"))
        if torrent_id:
            self.existing_hashes.append(active_stream.get("infohash"))
            return str(torrent_id)
        raise Exception("Failed to download torrent.")

    def add_torrent_magnet(self, magnet_uri: str) -> DebridTorrentId:
        hash = hash_from_uri(magnet_uri)
        if not hash:
            raise Exception(f"Bad magnet: {magnet_uri}")
        torrent_id = add_torrent(hash)
        if torrent_id:
            self.existing_hashes.append(hash)
            return str(torrent_id)
        raise Exception("Failed to download torrent.")

    def get_cached_containers(
        self, infohashes: list[InfoHash], needed_media: dict, break_pointer: list[bool]
    ) -> dict:
        """
        Get containers that are available in the debrid cache containing `needed_media`

        Parameters:
        - infohashes: a list of hashes that might contain the data we need
        - needed_media: a dict of seasons, with lists of episodes, indicating what content is needed
        - break_pointer: first bool indicates if the needed content was found yet, 2nd pointer indicates if we should break once it's found.
        """
        cached_containers = {}
        response = get_instant_availability(infohashes)
        magnets = {m.get("hash"): m for m in response}

        for infohash in infohashes:
            if all(break_pointer):
                break
            cached_containers[infohash] = {}
            magnet = magnets.get(infohash, {})
            files = magnet.get("files", [])
            if not files:
                continue

            # We avoid compressed downloads this way
            def all_files_valid(files: list) -> bool:
                filenames = [f.lower() for f, _ in walk_alldebrid_files(files)]
                return all(
                    "sample" not in file and file.rsplit(".", 1)[-1] in VIDEO_EXTENSIONS
                    for file in filenames
                )

            if all_files_valid(files):
                # The file_finder needs files to be in a dict, but it doesn't care about the keys
                container = {
                    i: dict(filename=name, filesize=size)
                    for i, (name, size) in enumerate(walk_alldebrid_files(files))
                }
                cached_containers[infohash] = self.file_finder.get_cached_container(
                    needed_media, break_pointer, container
                )
                if cached_containers[infohash]:
                    break_pointer[0] = True
                    if break_pointer[1]:
                        break

        return cached_containers

    def get_torrent_names(self, id: DebridTorrentId) -> tuple[str, Optional[str]]:
        info = get_status(id)
        return info["filename"], None

    def delete_torrent_with_infohash(self, infohash: InfoHash):
        id = next(
            torrent["id"] for torrent in get_torrents() if torrent["hash"] == infohash
        )
        if id:
            delete_torrent(id)


    def get_torrent_info(self, torrent_id: DebridTorrentId) -> dict:
        return get_status(torrent_id)

def walk_alldebrid_files(files: list[dict]) -> (str, int):
    """Walks alldebrid's `files` nested dicts and returns (filename, filesize) for each file, discarding path information"""
    dirs = []
    for f in files:
        try:
            size = int(f.get("s", ""))
            yield f.get("n", "UNKNOWN"), size
        except ValueError:
            dirs.append(f)

    for d in dirs:
        walk_alldebrid_files(d.get("e", []))


def get(url, **params) -> dict:
    params["agent"] = AD_AGENT  # Add agent parameter per AllDebrid API requirement
    return request.get(
        url=f"{AD_BASE_URL}/{url}",
        params=params,
        additional_headers={
            "Authorization": f"Bearer {settings.settings.downloaders.all_debrid.api_key}"
        },
        response_type=dict,
        specific_rate_limiter=inner_rate_limit,
        overall_rate_limiter=overall_rate_limiter,
        proxies=settings.settings.downloaders.all_debrid.proxy_url
        if settings.settings.downloaders.all_debrid.proxy_enabled
        else None,
    ).data


def get_user() -> dict:
    return get("user")


def get_instant_availability(infohashes: list[InfoHash]) -> list[dict]:
    try:
        params = dict(
            (f"magnets[{i}]", infohash) for i, infohash in enumerate(infohashes)
        )
        data = get("magnet/instant", **params)
        magnets = data.get("data", {}).get("magnets", [])
    except Exception as e:
        logger.warning("Failed to get instant availability.")
        magnets = [e]
    return magnets


def add_torrent(infohash: str) -> DebridTorrentId:
    try:
        params={"magnets[]": infohash}
        id = get(
            "magnet/upload", **params
        )["data"]["magnets"][0]["id"]
    except Exception:
        logger.warning(f"Failed to add torrent with infohash {infohash}")
        id = None
    return id


def get_status(id: str) -> dict:
    try:
        info = get("magnet/status", id=id)["data"]["magnets"]
        # Error if filename not present
        info.get("filename")
    except Exception:
        logger.warning(f"Failed to get info for torrent with id {id}")
        info = {}
    return info


def get_torrents() -> list[dict]:
    try:
        torrents = get("magnet/status")
        torrents = torrents.get("data", {}).get("magnets", [])
    except Exception:
        logger.warning("Failed to get torrents.")
        torrents = []
    return torrents

def delete_torrent(id: str):
    try:
        get("magnet/delete", id=id)
    except Exception:
        logger.warning(f"Failed to delete torrent with id {id}")
