from datetime import datetime
from typing import Optional, List, Dict, Iterator, Tuple
from pydantic import BaseModel
from loguru import logger
import requests
from requests.exceptions import RequestException, ConnectTimeout

from .shared import (
    VIDEO_EXTENSIONS,
    FileFinder,
    DownloaderBase,
    premium_days_left
)
from program.settings.manager import settings_manager

class AllDebridError(Exception):
    """Base exception for AllDebrid related errors"""
    pass

class AllDebridAPI:
    """Handles AllDebrid API communication"""
    BASE_URL = "https://api.alldebrid.com/v4"
    AGENT = "Riven"

    def __init__(self, api_key: str, proxy_url: Optional[str] = None):
        self.api_key = api_key
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {api_key}"
        })
        if proxy_url:
            self.session.proxies = {"http": proxy_url, "https": proxy_url}

    def _request(self, method: str, endpoint: str, **params) -> dict:
        """Generic request handler with error handling"""
        try:
            params["agent"] = self.AGENT
            url = f"{self.BASE_URL}/{endpoint}"
            response = self.session.request(method, url, params=params)
            response.raise_for_status()
            data = response.json() if response.content else {}

            if not data or "data" not in data:
                raise AllDebridError("Invalid response from AllDebrid")

            return data["data"]
        except requests.exceptions.JSONDecodeError as e:
            logger.error(f"Failed to decode JSON response: {e}")
            raise AllDebridError("Invalid JSON response") from e
        except RequestException as e:
            logger.error(f"Request failed: {e}")
            raise

class AllDebridDownloader(DownloaderBase):
    """Main AllDebrid downloader class implementing DownloaderBase"""

    def __init__(self):
        self.key = "alldebrid"
        self.settings = settings_manager.settings.downloaders.all_debrid
        self.api = None
        self.file_finder = None
        self.initialized = self.validate()

    def validate(self) -> bool:
        """
        Validate AllDebrid settings and premium status
        Required by DownloaderBase
        """
        if not self._validate_settings():
            return False

        self.api = AllDebridAPI(
            api_key=self.settings.api_key,
            proxy_url=self.settings.proxy_url if self.settings.proxy_enabled else None
        )

        if not self._validate_premium():
            return False

        self.file_finder = FileFinder("filename", "filesize")
        logger.success("AllDebrid initialized!")
        return True

    def _validate_settings(self) -> bool:
        """Validate configuration settings"""
        if not self.settings.enabled:
            return False
        if not self.settings.api_key:
            logger.warning("AllDebrid API key is not set")
            return False
        if self.settings.proxy_enabled and not self.settings.proxy_url:
            logger.error("Proxy is enabled but no proxy URL is provided")
            return False
        return True

    def _validate_premium(self) -> bool:
        """Validate premium status"""
        try:
            user_info = self.api._request("GET", "user")
            user = user_info.get("user", {})

            if not user.get("isPremium", False):
                logger.error("Premium membership required")
                return False

            expiration = datetime.utcfromtimestamp(user.get("premiumUntil", 0))
            logger.log("DEBRID", premium_days_left(expiration))
            return True

        except ConnectTimeout:
            logger.error("Connection to AllDebrid timed out")
        except Exception as e:
            logger.error(f"Failed to validate premium status: {e}")
        return False

    def get_instant_availability(self, infohashes: List[str]) -> Dict[str, list]:
        """
        Get instant availability for multiple infohashes
        Required by DownloaderBase
        """
        if not self.initialized:
            logger.error("Downloader not properly initialized")
            return {}

        try:
            params = {f"magnets[{i}]": infohash for i, infohash in enumerate(infohashes)}
            response = self.api._request("GET", "magnet/instant", **params)
            magnets = response.get("magnets", [])

            availability = {}
            for magnet in magnets:
                if not isinstance(magnet, dict) or "files" not in magnet:
                    continue

                files = magnet.get("files", [])
                valid_files = self._process_files(files)

                if valid_files:
                    availability[magnet["hash"]] = [valid_files]

            return availability

        except Exception as e:
            logger.error(f"Failed to get instant availability: {e}")
            return {}

    def _walk_files(self, files: List[dict]) -> Iterator[Tuple[str, int]]:
        """Walks nested files structure and yields filename, size pairs"""
        dirs = []
        for file in files:
            try:
                size = int(file.get("s", ""))
                yield file.get("n", "UNKNOWN"), size
            except ValueError:
                dirs.append(file)

        for directory in dirs:
            yield from self._walk_files(directory.get("e", []))

    def _process_files(self, files: List[dict]) -> Dict[str, dict]:
        """Process and filter valid video files"""
        result = {}
        for i, (name, size) in enumerate(self._walk_files(files)):
            if (
                any(name.lower().endswith(ext) for ext in VIDEO_EXTENSIONS)
                and "sample" not in name.lower()
            ):
                result[str(i)] = {"filename": name, "filesize": size}
        return result

    def add_torrent(self, infohash: str) -> str:
        """
        Add a torrent by infohash
        Required by DownloaderBase
        """
        if not self.initialized:
            raise AllDebridError("Downloader not properly initialized")

        try:
            response = self.api._request(
                "GET",
                "magnet/upload",
                **{"magnets[]": infohash}
            )
            magnet_info = response.get("magnets", [])[0]
            torrent_id = magnet_info.get("id")

            if not torrent_id:
                raise AllDebridError("No torrent ID in response")

            return str(torrent_id)

        except Exception as e:
            logger.error(f"Failed to add torrent {infohash}: {e}")
            raise

    def select_files(self, torrent_id: str, files: List[str]):
        """
        Select files from a torrent
        Required by DownloaderBase
        """
        if not self.initialized:
            raise AllDebridError("Downloader not properly initialized")

        try:
            # AllDebrid doesn't have a separate file selection endpoint
            # All files are automatically selected when adding the torrent
            pass
        except Exception as e:
            logger.error(f"Failed to select files for torrent {torrent_id}: {e}")
            raise

    def get_torrent_info(self, torrent_id: str) -> dict:
        """
        Get information about a torrent
        Required by DownloaderBase
        """
        if not self.initialized:
            raise AllDebridError("Downloader not properly initialized")

        try:
            response = self.api._request("GET", "magnet/status", id=torrent_id)
            info = response.get("magnets", {})
            if "filename" not in info:
                raise AllDebridError("Invalid torrent info response")
            return info
        except Exception as e:
            logger.error(f"Failed to get torrent info for {torrent_id}: {e}")
            raise

    def delete_torrent(self, torrent_id: str):
        """
        Delete a torrent
        Required by DownloaderBase
        """
        if not self.initialized:
            raise AllDebridError("Downloader not properly initialized")

        try:
            self.api._request("GET", "magnet/delete", id=torrent_id)
        except Exception as e:
            logger.error(f"Failed to delete torrent {torrent_id}: {e}")
            raise