import time
from datetime import datetime
from typing import List, Optional

from loguru import logger
from requests import Session
from requests.exceptions import ConnectTimeout

from program.services.downloaders.models import (
    DebridFile,
    InvalidDebridFileException,
    TorrentContainer,
    TorrentInfo,
)
from program.settings.manager import settings_manager
from program.utils.request import (
    BaseRequestHandler,
    BaseRequestParameters,
    HttpMethod,
    ResponseType,
    create_service_session,
    get_rate_limit_params,
)

from .shared import DownloaderBase, premium_days_left


class AllDebridError(Exception):
    """Base exception for AllDebrid related errors"""

class AllDebridBaseRequestParameters(BaseRequestParameters):
    """AllDebrid base request parameters"""
    agent: Optional[str] = None

class AllDebridRequestHandler(BaseRequestHandler):
    def __init__(self, session: Session, base_url: str, base_params: AllDebridBaseRequestParameters, request_logging: bool = False):
        super().__init__(session, response_type=ResponseType.DICT, base_url=base_url, base_params=base_params, custom_exception=AllDebridError, request_logging=request_logging)

    def execute(self, method: HttpMethod, endpoint: str, **kwargs) -> dict:
        response = super()._request(method, endpoint, **kwargs)
        if not response.is_ok or not response.data or "data" not in response.data:
            raise AllDebridError("Invalid response from AllDebrid")
        return response.data["data"]

class AllDebridAPI:
    """Handles AllDebrid API communication"""
    BASE_URL = "https://api.alldebrid.com/v4"
    AGENT = "Riven"

    def __init__(self, api_key: str, proxy_url: Optional[str] = None):
        self.api_key = api_key
        rate_limit_params = get_rate_limit_params(per_minute=600, per_second=12)
        self.session = create_service_session(rate_limit_params=rate_limit_params)
        self.session.headers.update({
            "Authorization": f"Bearer {api_key}"
        })
        if proxy_url:
            self.session.proxies = {"http": proxy_url, "https": proxy_url}
        base_params = AllDebridBaseRequestParameters()
        base_params.agent = self.AGENT
        self.request_handler = AllDebridRequestHandler(self.session, self.BASE_URL, base_params)


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
            user_info = self.api.request_handler.execute(HttpMethod.GET, "user")
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
                        if 'n' in entry and 's' in entry and 'l' in entry:
                            if debrid_file := DebridFile.create(
                                filename=entry['n'],
                                filesize_bytes=entry['s'],
                                filetype=item_type
                            ):
                                processed_files.append(debrid_file)
                        # directory entries
                        elif 'e' in entry:
                            for sub_entry in entry['e']:
                                process_entry(sub_entry)

                for file_entry in files:
                    process_entry(file_entry)

                if processed_files:
                    return_value = TorrentContainer(infohash=infohash, files=processed_files)
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
            response = self.api.request_handler.execute(
                HttpMethod.GET,
                "magnet/upload",
                params={"magnets[]": infohash}
            )
            magnet_info = response.get("magnets", [])[0]
            torrent_id = magnet_info.get("id")

            if not torrent_id:
                raise AllDebridError("No torrent ID in response")

            return str(torrent_id)

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
            response = self.api.request_handler.execute(HttpMethod.GET, "magnet/status", params={"id": torrent_id})
            info = response.get("magnets", {})
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
        except Exception as e:
            logger.error(f"Failed to get torrent info for {torrent_id}: {e}")
            raise

    def delete_torrent(self, torrent_id: str):
        """
        Delete a torrent
        Required by DownloaderBase
        """
        try:
            self.api.request_handler.execute(HttpMethod.GET, "magnet/delete", params={"id": torrent_id})
        except Exception as e:
            logger.error(f"Failed to delete torrent {torrent_id}: {e}")
            raise

    def get_files_and_links(self, torrent_id: str) -> List[DebridFile]:
        """
        Get torrent files and links by id
        """
        try:
            response = self.api.request_handler.execute(
                HttpMethod.GET,
                "magnet/files",
                params={"id[]": torrent_id}
            )
            magnet_info = next((info for info in response.get("magnets") if info["id"] == torrent_id), {})
            return magnet_info.get("files", {})

        except Exception as e:
            logger.error(f"Failed to get files for {torrent_id}: {e}")
            raise