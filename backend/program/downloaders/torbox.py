import contextlib
from datetime import datetime
import time
from typing import Generator

from RTN import parse
from RTN.exceptions import GarbageTorrent

from program.media.item import MediaItem, Movie
from program.settings.manager import settings_manager
from utils.logger import logger
from utils.request import get, post


class TorBoxDownloader:
    """TorBox Downloader"""

    def __init__(self, hash_cache):
        self.key = "torbox_downloader"
        self.settings = settings_manager.settings.downloaders.torbox
        self.api_key = self.settings.api_key
        self.base_url = "https://api.torbox.app/v1/api"
        self.headers = {"Authorization": f"Bearer {self.api_key}"}
        self.initialized = self.validate()
        if not self.initialized:
            return
        self.hash_cache = hash_cache
        logger.success("TorBox Downloader initialized!")

    def validate(self) -> bool:
        """Validate the TorBox Downloader as a service"""
        if not self.settings.enabled:
            logger.info("Torbox downloader is not enabled")
            return False
        if not self.settings.api_key:
            logger.error("Torbox API key is not set")
        try:
            return self.get_expiry_date() > datetime.now()
        except:
            return False

    def run(self, item: MediaItem) -> Generator[MediaItem, None, None]:
        """Download media item from TorBox"""   
        logger.info(f"Downloading {item.log_string} from TorBox")
        if self.is_cached(item):
            self.download(item)
        yield item


    def is_cached(self, item: MediaItem):
        streams = [hash for hash in item.streams]
        data = self.get_web_download_cached(streams)
        for hash in data:
            item.active_stream=data[hash]
            return True

    def download(self, item: MediaItem):
        # Support only movies for now
        if item.type == "movie":

            # Check if the torrent already exists
            exists = False
            torrent_list = self.get_torrent_list()
            for torrent in torrent_list:
                if item.active_stream["hash"] == torrent["hash"]:
                    id = torrent["id"]
                    exists = True
                    break
            # If it doesnt, lets download it and refresh the torrent_list
            if not exists:
                id = self.create_torrent(item.active_stream["hash"])
                torrent_list = self.get_torrent_list()

            # Find the torrent, correct file and we gucci
            for torrent in torrent_list:
                if torrent["id"] == id:
                    with contextlib.suppress(GarbageTorrent, TypeError):
                        for file in torrent["files"]:
                            if file["size"] > 10000:
                                parsed_file = parse(file["short_name"])
                                if parsed_file.type == "movie":
                                    item.set("folder", ".")
                                    item.set("alternative_folder", ".")
                                    item.set("file", file["short_name"])
                                    return True

    def get_expiry_date(self):
        expiry = datetime.fromisoformat(self.get_user_data().premium_expires_at)
        expiry = expiry.replace(tzinfo=None)
        return expiry

    def get_web_download_cached(self, hash_list):
        hash_string = ",".join(hash_list)
        response = get(f"{self.base_url}/torrents/checkcached?hash={hash_string}", additional_headers=self.headers, response_type=dict)
        return response.data["data"]

    def get_user_data(self):
        response = get(f"{self.base_url}/user/me", additional_headers=self.headers, retry_if_failed=False)
        return response.data.data

    def create_torrent(self, hash) -> int:
        magnet_url = f"magnet:?xt=urn:btih:{hash}&dn=&tr="
        response = post(f"{self.base_url}/torrents/createtorrent", data={"magnet": magnet_url}, additional_headers=self.headers)
        return response.data.data.torrent_id
    
    def get_torrent_list(self) -> list:
        response = get(f"{self.base_url}/torrents/mylist", additional_headers=self.headers, response_type=dict)
        return response.data["data"]
