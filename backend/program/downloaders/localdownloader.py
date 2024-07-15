import contextlib
import time
from datetime import datetime
from typing import Generator

from program.media.item import MediaItem, Movie, Show, Season, Episode
from program.settings.manager import settings_manager
from utils.logger import logger
from utils.request import get, post

class LocalDownloader:
    """Local Downloader for SabNZB and qBittorrent"""

    def __init__(self, hash_cache):
        self.key = "local_downloader"
        self.settings = settings_manager.settings.downloaders.local
        self.sabnzbd_enabled = self.settings.sabnzbd_enabled
        self.sabnzbd_url = self.settings.sabnzbd_url
        self.sabnzbd_api_key = self.settings.sabnzbd_api_key
        self.qbittorrent_enabled = self.settings.qbittorrent_enabled
        self.qbittorrent_url = self.settings.qbittorrent_url
        self.qbittorrent_username = self.settings.qbittorrent_username
        self.qbittorrent_password = self.settings.qbittorrent_password
        self.initialized = self.validate()
        if not self.initialized:
            return
        self.hash_cache = hash_cache
        logger.success("Local Downloader initialized!")

    def validate(self) -> bool:
        if not self.settings.enabled:
            logger.warning("Local downloader is set to disabled.")
            return False
        if self.sabnzbd_enabled and (not self.sabnzbd_url or not self.sabnzbd_api_key):
            logger.error("SabNZB URL or API key is not set")
            return False
        if self.qbittorrent_enabled and (not self.qbittorrent_url or not self.qbittorrent_username or not self.qbittorrent_password):
            logger.error("qBittorrent credentials are not set")
            return False
        return True

    def run(self, item: MediaItem) -> Generator[MediaItem, None, None]:
        logger.info(f"Downloading {item.log_string} using Local Downloader")
        if self.is_cached(item):
            self.download(item)
        yield item

    def is_cached(self, item: MediaItem) -> bool:
        if self.sabnzbd_enabled and self.is_cached_in_sabnzbd(item):
            return True
        if self.qbittorrent_enabled and self.is_cached_in_qbittorrent(item):
            return True
        return False

    def is_cached_in_sabnzbd(self, item: MediaItem) -> bool:
        try:
            response = get(
                f"{self.sabnzbd_url}/api?mode=queue&apikey={self.sabnzbd_api_key}&output=json"
            )
            if response.is_ok:
                queue = response.data.get("queue", {}).get("slots", [])
                for slot in queue:
                    if item.active_stream["url"] in slot.get("filename", ""):
                        logger.info(f"{item.log_string} is already in SabNZB queue")
                        return True
            return False
        except Exception as e:
            logger.error(f"Error checking SabNZB queue: {e}")
            return False

    def is_cached_in_qbittorrent(self, item: MediaItem) -> bool:
        try:
            auth_response = post(
                f"{self.qbittorrent_url}/api/v2/auth/login",
                {
                    "username": self.qbittorrent_username,
                    "password": self.qbittorrent_password
                }
            )
            if not auth_response.is_ok:
                logger.error(f"Failed to authenticate with qBittorrent: {auth_response.data}")
                return False

            response = get(
                f"{self.qbittorrent_url}/api/v2/torrents/info",
                cookies=auth_response.cookies
            )
            if response.is_ok:
                torrents = response.data
                for torrent in torrents:
                    if item.active_stream["url"] in torrent.get("magnet_uri", ""):
                        logger.info(f"{item.log_string} is already in qBittorrent")
                        return True
            return False
        except Exception as e:
            logger.error(f"Error checking qBittorrent: {e}")
            return False

    def download(self, item: MediaItem):
        if item.type == "movie":
            self.download_movie(item)
        elif item.type == "show":
            self.download_show(item)
        elif item.type == "season":
            self.download_season(item)
        elif item.type == "episode":
            self.download_episode(item)

    def download_movie(self, item: Movie):
        if self.sabnzbd_enabled and self.download_with_sabnzbd(item):
            return
        if self.qbittorrent_enabled and self.download_with_qbittorrent(item):
            return

    def download_show(self, item: Show):
        for season in item.seasons:
            self.download_season(season)

    def download_season(self, item: Season):
        for episode in item.episodes:
            self.download_episode(episode)

    def download_episode(self, item: Episode):
        if self.sabnzbd_enabled and self.download_with_sabnzbd(item):
            return
        if self.qbittorrent_enabled and self.download_with_qbittorrent(item):
            return

    def download_with_sabnzbd(self, item: MediaItem) -> bool:
        try:
            response = post(
                f"{self.sabnzbd_url}/api",
                {
                    "mode": "addurl",
                    "name": item.active_stream["url"],
                    "apikey": self.sabnzbd_api_key,
                    "output": "json"
                }
            )
            if response.is_ok:
                logger.info(f"Successfully added {item.log_string} to SabNZB")
                return True
            else:
                logger.error(f"Failed to add {item.log_string} to SabNZB: {response.data}")
        except Exception as e:
            logger.error(f"Error adding {item.log_string} to SabNZB: {e}")
        return False

    def download_with_qbittorrent(self, item: MediaItem) -> bool:
        try:
            auth_response = post(
                f"{self.qbittorrent_url}/api/v2/auth/login",
                {
                    "username": self.qbittorrent_username,
                    "password": self.qbittorrent_password
                }
            )
            if not auth_response.is_ok:
                logger.error(f"Failed to authenticate with qBittorrent: {auth_response.data}")
                return False

            response = post(
                f"{self.qbittorrent_url}/api/v2/torrents/add",
                {
                    "urls": item.active_stream["url"]
                },
                cookies=auth_response.cookies
            )
            if response.is_ok:
                logger.info(f"Successfully added {item.log_string} to qBittorrent")
                return True
            else:
                logger.error(f"Failed to add {item.log_string} to qBittorrent: {response.data}")
        except Exception as e:
            logger.error(f"Error adding {item.log_string} to qBittorrent: {e}")
        return False