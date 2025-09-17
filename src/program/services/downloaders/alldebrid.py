import time
from datetime import datetime
from typing import List, Optional

from loguru import logger
from requests.exceptions import ConnectTimeout

from program.services.downloaders.models import (
    DebridFile,
    InvalidDebridFileException,
    TorrentContainer,
    TorrentInfo,
)
from program.settings.manager import settings_manager
from program.utils.request import CircuitBreakerOpen, SmartSession

from .shared import DownloaderBase, premium_days_left


class AllDebridError(Exception):
    """Base exception for AllDebrid related errors"""

class AllDebridAPI:
    """Handles AllDebrid API communication"""
    BASE_URL = "https://api.alldebrid.com/v4"
    AGENT = "Riven"

    def __init__(self, api_key: str, proxy_url: Optional[str] = None):
        self.api_key = api_key

        rate_limits = {
            "api.alldebrid.com": {"rate": 12, "capacity": 600}  # 12 calls per second, 600 per minute
        }
        
        self.session = SmartSession(
            base_url=self.BASE_URL,
            rate_limits=rate_limits,
            retries=3,
            backoff_factor=0.3
        )
        self.session.headers.update({
            "Authorization": f"Bearer {api_key}"
        })
        if proxy_url:
            self.session.proxies = {"http": proxy_url, "https": proxy_url}


class AllDebridDownloader(DownloaderBase):
    """Main AllDebrid downloader class implementing DownloaderBase"""

    def __init__(self):
        self.key = "alldebrid"
        self.settings = settings_manager.settings.downloaders.all_debrid
        self.api = None
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
            proxy_url=self.PROXY_URL if self.PROXY_URL else None
        )

        if not self._validate_premium():
            return False

        logger.success("AllDebrid initialized!")
        return True

    def _validate_settings(self) -> bool:
        """Validate configuration settings"""
        if not self.settings.enabled:
            return False
        if not self.settings.api_key:
            logger.warning("AllDebrid API key is not set")
            return False
        return True

    def _validate_premium(self) -> bool:
        """Validate premium status"""
        try:
            user_info = self.api.session.get("user")
            user = user_info.data.get("user", {})

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

    def get_instant_availability(self, infohash: str, item_type: str) -> Optional[TorrentContainer]:
        """
        Get instant availability for a single infohash
        Required by DownloaderBase
        """
        torrent_id = None
        return_value = None

        try:
            torrent_id = self.add_torrent(infohash)
            time.sleep(1)
            info = self.get_torrent_info(torrent_id)
            if info.status == "Ready":
                files = self.get_files_and_links(torrent_id)
                processed_files = []
                
                def process_entry(entry):
                    if isinstance(entry, dict):
                        # file entries
                        if "n" in entry and "s" in entry and "l" in entry:
                            if debrid_file := DebridFile.create(
                                filename=entry["n"],
                                filesize_bytes=entry["s"],
                                filetype=item_type
                            ):
                                # AllDebrid provides direct download links in the 'l' field
                                debrid_file.download_url = entry['l']
                                processed_files.append(debrid_file)
                        # directory entries
                        elif "e" in entry:
                            for sub_entry in entry["e"]:
                                process_entry(sub_entry)

                for file_entry in files:
                    process_entry(file_entry)

                if processed_files:
                    return_value = TorrentContainer(infohash=infohash, files=processed_files)
        except CircuitBreakerOpen as e:
            logger.warning(f"Circuit breaker OPEN for AllDebrid API, skipping {infohash}: {e}")
            raise  # Re-raise to be handled by the calling service
        except InvalidDebridFileException as e:
            logger.debug(f"{infohash}: {e}")
        except Exception as e:
            logger.error(f"Failed to get instant availability: {e}")
        finally:
            if torrent_id:
                self.delete_torrent(torrent_id)
            return return_value

    def add_torrent(self, infohash: str) -> str:
        """
        Add a torrent by infohash
        Required by DownloaderBase
        """
        if not self.initialized:
            raise AllDebridError("Downloader not properly initialized")

        try:
            response = self.api.session.get(
                "magnet/upload",
                params={"magnets[]": infohash}
            )
            magnet_info = response.data.get("magnets", [])[0]
            torrent_id = magnet_info.get("id")

            if not torrent_id:
                raise AllDebridError("No torrent ID in response")

            return str(torrent_id)

        except CircuitBreakerOpen as e:
            logger.warning(f"Circuit breaker OPEN for AllDebrid API, cannot add torrent {infohash}: {e}")
            raise  # Re-raise to be handled by the calling service
        except Exception as e:
            logger.error(f"Failed to add torrent {infohash}: {e}")
            raise

    def select_files(self, torrent_id: str, _: List[str] = None) -> None:
        """
        Select files from a torrent
        Required by DownloaderBase
        """
        try:
            # AllDebrid doesn't have a separate file selection endpoint
            # All files are automatically selected when adding the torrent
            pass
        except Exception as e:
            logger.error(f"Failed to select files for torrent {torrent_id}: {e}")
            raise

    def get_torrent_info(self, torrent_id: str) -> TorrentInfo:
        """
        Get information about a torrent
        Required by DownloaderBase
        """
        if not self.initialized:
            raise AllDebridError("Downloader not properly initialized")

        try:
            response = self.api.session.get("magnet/status", params={"id": torrent_id})
            info = response.data.get("magnets", {})
            if "filename" not in info:
                raise AllDebridError("Invalid torrent info response")
            return TorrentInfo(
                id=info["id"],
                name=info["filename"],
                status=info["status"],
                bytes=info["size"],
                created_at=info["uploadDate"],
                progress=(info["size"] / info["downloaded"]) if info["downloaded"] != 0 else 0
            )
        except CircuitBreakerOpen as e:
            logger.warning(f"Circuit breaker OPEN for AllDebrid API, cannot get torrent info for {torrent_id}: {e}")
            raise  # Re-raise to be handled by the calling service
        except Exception as e:
            logger.error(f"Failed to get torrent info for {torrent_id}: {e}")
            raise

    def delete_torrent(self, torrent_id: str):
        """
        Delete a torrent
        Required by DownloaderBase
        """
        try:
            self.api.session.get("magnet/delete", params={"id": torrent_id})
        except CircuitBreakerOpen as e:
            logger.warning(f"Circuit breaker OPEN for AllDebrid API, cannot delete torrent {torrent_id}: {e}")
            raise  # Re-raise to be handled by the calling service
        except Exception as e:
            logger.error(f"Failed to delete torrent {torrent_id}: {e}")
            raise

    def get_files_and_links(self, torrent_id: str) -> List[DebridFile]:
        """
        Get torrent files and links by id
        """
        try:
            response = self.api.session.get(
                "magnet/files",
                params={"id[]": torrent_id}
            )
            magnet_info = next((info for info in response.data.get("magnets") if info["id"] == torrent_id), {})
            return magnet_info.get("files", {})

        except CircuitBreakerOpen as e:
            logger.warning(f"Circuit breaker OPEN for AllDebrid API, cannot get files for {torrent_id}: {e}")
            raise  # Re-raise to be handled by the calling service
        except Exception as e:
            logger.error(f"Failed to get files for {torrent_id}: {e}")
            raise

    def get_download_url(self, torrent_id: str, file_link: str) -> Optional[str]:
        """Get download URL for a specific file - AllDebrid already provides direct links"""
        # AllDebrid provides direct download links in the 'l' field of get_files_and_links
        return file_link