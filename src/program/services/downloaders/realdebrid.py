import time
from datetime import datetime
from enum import Enum
from typing import List, Optional, Union

from loguru import logger
from pydantic import BaseModel
from requests import Session

from program.services.downloaders.models import (
    VALID_VIDEO_EXTENSIONS,
    DebridFile,
    InvalidDebridFileException,
    TorrentContainer,
    TorrentInfo,
)
from program.settings.manager import settings_manager
from program.utils.request import (
    BaseRequestHandler,
    HttpMethod,
    ResponseType,
    create_service_session,
    get_rate_limit_params,
)

from .shared import DownloaderBase, premium_days_left


class RDTorrentStatus(str, Enum):
    """Real-Debrid torrent status enumeration"""
    MAGNET_ERROR = "magnet_error"
    MAGNET_CONVERSION = "magnet_conversion"
    WAITING_FILES = "waiting_files_selection"
    DOWNLOADING = "downloading"
    DOWNLOADED = "downloaded"
    ERROR = "error"
    SEEDING = "seeding"
    DEAD = "dead"
    UPLOADING = "uploading"
    COMPRESSING = "compressing"

class RDTorrent(BaseModel):
    """Real-Debrid torrent model"""
    id: str
    hash: str
    filename: str
    bytes: int
    status: RDTorrentStatus
    added: datetime
    links: List[str]
    ended: Optional[datetime] = None
    speed: Optional[int] = None
    seeders: Optional[int] = None

class RealDebridError(Exception):
    """Base exception for Real-Debrid related errors"""

class RealDebridRequestHandler(BaseRequestHandler):
    def __init__(self, session: Session, base_url: str, request_logging: bool = False):
        super().__init__(session, response_type=ResponseType.DICT, base_url=base_url, custom_exception=RealDebridError, request_logging=request_logging)

    def execute(self, method: HttpMethod, endpoint: str, **kwargs) -> Union[dict, list]:
        response = super()._request(method, endpoint, **kwargs)
        if response.status_code == 204:
            return {}
        if not response.data and not response.is_ok:
            raise RealDebridError("Invalid JSON response from RealDebrid")
        return response.data

class RealDebridAPI:
    """Handles Real-Debrid API communication"""
    BASE_URL = "https://api.real-debrid.com/rest/1.0"

    def __init__(self, api_key: str, proxy_url: Optional[str] = None):
        self.api_key = api_key
        rate_limit_params = get_rate_limit_params(per_minute=60)
        self.session = create_service_session(rate_limit_params=rate_limit_params)
        self.session.headers.update({"Authorization": f"Bearer {api_key}"})
        if proxy_url:
            self.session.proxies = {"http": proxy_url, "https": proxy_url}
        self.request_handler = RealDebridRequestHandler(self.session, self.BASE_URL)

class RealDebridDownloader(DownloaderBase):
    """Main Real-Debrid downloader class implementing DownloaderBase"""

    def __init__(self):
        self.key = "realdebrid"
        self.settings = settings_manager.settings.downloaders.real_debrid
        self.api = None
        self.initialized = self.validate()

    def validate(self) -> bool:
        """
        Validate Real-Debrid settings and premium status
        Required by DownloaderBase
        """
        if not self._validate_settings():
            return False

        self.api = RealDebridAPI(
            api_key=self.settings.api_key,
            proxy_url=self.PROXY_URL if self.PROXY_URL else None
        )

        return self._validate_premium()

    def _validate_settings(self) -> bool:
        """Validate configuration settings"""
        if not self.settings.enabled:
            return False
        if not self.settings.api_key:
            logger.warning("Real-Debrid API key is not set")
            return False
        return True

    def _validate_premium(self) -> bool:
        """Validate premium status"""
        try:
            user_info = self.api.request_handler.execute(HttpMethod.GET, "user")
            if not user_info.get("premium"):
                logger.error("Premium membership required")
                return False

            expiration = datetime.fromisoformat(
                user_info["expiration"].replace("Z", "+00:00")
            ).replace(tzinfo=None)
            logger.info(premium_days_left(expiration))
            return True
        except Exception as e:
            logger.error(f"Failed to validate premium status: {e}")
            return False

    def get_instant_availability(self, infohash: str, item_type: str) -> Optional[TorrentContainer]:
        """
        Checks the instant availability of a torrent by adding it, processing its details to select valid video files, and subsequently deleting it.
        
        Due to the removal of native instant availability support by Real-Debrid, this method performs a makeshift availability check by:
          1. Adding the torrent using its infohash.
          2. Processing the torrent to filter and select valid files based on the provided item type.
          3. Deleting the torrent regardless of the outcome to ensure resource cleanup.
        
        Parameters:
            infohash (str): The unique identifier (infohash) of the torrent.
            item_type (str): The type or category of the torrent, used to determine appropriate file selection.
        
        Returns:
            Optional[TorrentContainer]: A container with valid torrent and file information if available; returns None if no valid files are found or an error occurs.
        
        Notes:
            - Exceptions are handled internally:
                * Logs a debug message if an InvalidDebridFileException occurs.
                * Logs an error message for any other exceptions.
            - This method always attempts to delete the torrent to avoid leaving unused entries.
        """
        valid_container: Optional[TorrentContainer] = None
        torrent_id = None

        try:
            torrent_id = self.add_torrent(infohash)
            container = self._process_torrent(torrent_id, infohash, item_type)
            if container:
                valid_container = container
        except InvalidDebridFileException as e:
            logger.debug(f"{infohash}: {e}")
        except Exception as e:
            logger.error(f"Failed to get instant availability for {infohash}: {e}")
        finally:
            if torrent_id is not None:
                self.delete_torrent(torrent_id)

        return valid_container

    def _process_torrent(self, torrent_id: str, infohash: str, item_type: str) -> Optional[TorrentContainer]:
        """
        Processes a single torrent and returns a TorrentContainer containing valid video files, or None if no valid files are found.
        
        This method first retrieves the torrent's details using get_torrent_info. If the torrent's status is "waiting_files_selection", it filters
        the torrent's files to identify those whose filenames end with any of the valid video extensions defined by VALID_VIDEO_EXTENSIONS (case insensitive).
        If no such video files are found, the method logs a debug message and returns None. Otherwise, it selects the identified video files by calling
        select_files, refreshes the torrent information, and ensures that the torrent status is "downloaded" (cached). If the torrent is not cached or if
        there are no files, the method returns None.
        
        If valid files are present, each file is processed using DebridFile.create to construct a file object, and the method returns a TorrentContainer
        with the provided infohash and a list of these processed files.
        
        Parameters:
            torrent_id (str): The unique identifier of the torrent.
            infohash (str): The unique hash representing the torrent's info.
            item_type (str): A string indicating the type of the item, used when creating file objects.
        
        Returns:
            Optional[TorrentContainer]: A TorrentContainer with the infohash and a list of valid video files if available; otherwise, None.
        
        Raises:
            Any exceptions raised by get_torrent_info or select_files are propagated.
        """
        torrent_info = self.get_torrent_info(torrent_id)
        
        if torrent_info.status == "waiting_files_selection":
            video_file_ids = [
                file_id for file_id, file_info in torrent_info.files.items()
                if file_info["filename"].endswith(tuple(ext.lower() for ext in VALID_VIDEO_EXTENSIONS))
            ]

            if not video_file_ids:
                logger.debug(f"No video files found in torrent {torrent_id} with infohash {infohash}")
                return None

            self.select_files(torrent_id, video_file_ids)
            torrent_info = self.get_torrent_info(torrent_id)

            if torrent_info.status != "downloaded":
                logger.debug(f"Torrent {torrent_id} with infohash {infohash} is not cached")
                return None

        if not torrent_info.files:
            return None

        torrent_files = [
            file for file in (
                DebridFile.create(
                    file_info["filename"],
                    file_info["bytes"],
                    item_type,
                    file_id
                )
                for file_id, file_info in torrent_info.files.items()
            ) if file is not None
        ]

        return TorrentContainer(infohash=infohash, files=torrent_files) if torrent_files else None

    def add_torrent(self, infohash: str) -> str:
        """Add a torrent by infohash"""
        try:
            magnet = f"magnet:?xt=urn:btih:{infohash}"
            response = self.api.request_handler.execute(
                HttpMethod.POST,
                "torrents/addMagnet",
                data={"magnet": magnet.lower()}
            )
            return response["id"]
        except Exception as e:
            logger.error(f"Failed to add torrent {infohash}: {e}")
            raise

    def select_files(self, torrent_id: str, ids: List[int] = None) -> None:
        """Select files from a torrent"""
        try:
            selection = ",".join(str(file_id) for file_id in ids) if ids else "all"
            self.api.request_handler.execute(
                HttpMethod.POST,
                f"torrents/selectFiles/{torrent_id}",
                data={"files": selection}
            )
            time.sleep(1)
        except Exception as e:
            logger.error(f"Failed to select files for torrent {torrent_id}: {e}")
            raise

    def get_torrent_info(self, torrent_id: str) -> TorrentInfo:
        """Get information about a torrent"""
        try:
            data = self.api.request_handler.execute(HttpMethod.GET, f"torrents/info/{torrent_id}")
            files = {file["id"]: {"filename": file["path"].split("/")[-1], "bytes": file["bytes"]} for file in data["files"]}
            return TorrentInfo(
                id=data["id"],
                name=data["filename"],
                status=data["status"],
                infohash=data["hash"],
                bytes=data["bytes"],
                created_at=data["added"],
                alternative_filename=data.get("original_filename", None),
                progress=data.get("progress", None),
                files=files,
            )
        except Exception as e:
            logger.error(f"Failed to get torrent info for {torrent_id}: {e}")
            raise

    def delete_torrent(self, torrent_id: str) -> None:
        """Delete a torrent"""
        try:
            self.api.request_handler.execute(HttpMethod.DELETE, f"torrents/delete/{torrent_id}")
        except Exception as e:
            logger.error(f"Failed to delete torrent {torrent_id}: {e}")
            raise
