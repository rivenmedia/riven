import time
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Union

from loguru import logger
from pydantic import BaseModel
from requests import Session

from program.media.item import MediaItem
from program.media.stream import Stream
from program.settings.manager import settings_manager
from program.utils.request import (
    BaseRequestHandler,
    HttpMethod,
    ResponseType,
    create_service_session,
    get_rate_limit_params,
)

from .shared import (
    VIDEO_EXTENSIONS,
    DownloadCachedStreamResult,
    DownloaderBase,
    FileFinder,
    premium_days_left,
)

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

class TorrentNotFoundError(RealDebridError):
    """Raised when a torrent is not found on Real-Debrid servers"""

class InvalidFileIDError(RealDebridError):
    """Raised when invalid file IDs are provided"""

class DownloadFailedError(RealDebridError):
    """Raised when a torrent download fails"""

class RealDebridRequestHandler(BaseRequestHandler):
    def __init__(self, session: Session, base_url: str, request_logging: bool = False):
        super().__init__(session, response_type=ResponseType.DICT, base_url=base_url, custom_exception=RealDebridError, request_logging=request_logging)

    def execute(self, method: HttpMethod, endpoint: str, **kwargs) -> Union[dict, list]:
        response = super()._request(method, endpoint, **kwargs)
        # Handle 202 (action already done) as success
        if response.status_code in (204, 202):
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
    MAX_RETRIES = 3
    RETRY_DELAY = 1.0
    DOWNLOAD_POLL_INTERVAL = 5  # seconds
    DOWNLOAD_TIMEOUT = 300  # 5 minutes

    def __init__(self):
        self.key = "realdebrid"
        self.settings = settings_manager.settings.downloaders.real_debrid
        self.api = None
        self.file_finder = None
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
            proxy_url=self.settings.proxy_url if self.settings.proxy_enabled else None
        )
        self.file_finder = FileFinder("filename", "filesize")

        return self._validate_premium()

    def _validate_settings(self) -> bool:
        """Validate configuration settings"""
        if not self.settings.enabled:
            return False
        if not self.settings.api_key:
            logger.warning("Real-Debrid API key is not set")
            return False
        if self.settings.proxy_enabled and not self.settings.proxy_url:
            logger.error("Proxy is enabled but no proxy URL is provided")
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

    def get_instant_availability(self, infohashes: List[str]) -> Dict[str, list]:
        """
        Get instant availability for multiple infohashes
        Required by DownloaderBase
        Note: Cache checking disabled - returns empty dict to skip cache check
        """
        return {}

    def add_torrent(self, infohash: str) -> str:
        """
        Add a torrent to Real-Debrid
        Required by DownloaderBase
        """
        if not self.initialized:
            raise RealDebridError("Downloader not properly initialized")

        try:
            # Try to add the torrent and immediately select files
            magnet = f"magnet:?xt=urn:btih:{infohash}"
            logger.debug(f"Adding torrent with magnet: {magnet}")
            
            response = self.api.request_handler.execute(
                HttpMethod.POST,
                "torrents/addMagnet",
                data={"magnet": magnet}
            )
            logger.debug(f"Add torrent response: {response}")
            
            torrent_id = response.get("id")
            if not torrent_id:
                logger.error(f"Invalid response from Real-Debrid: {response}")
                raise RealDebridError("No torrent ID in response")

            # Get initial torrent info
            info = self.get_torrent_info(torrent_id)
            logger.debug(f"Initial torrent info: {info}")

            # Immediately select all files to prevent torrent removal
            try:
                self.select_files(torrent_id, [])
            except Exception as e:
                logger.error(f"Failed to select files: {str(e)}")
                # If selection fails, try to clean up
                try:
                    self.delete_torrent(torrent_id)
                except Exception as delete_error:
                    logger.error(f"Failed to delete torrent: {str(delete_error)}")
                raise e

            return torrent_id

        except Exception as e:
            logger.error(f"Failed to add torrent {infohash}: {str(e)}")
            raise

    def select_files(self, torrent_id: str, files: List[str]):
        """
        Select files from a torrent
        Required by DownloaderBase
        """
        if not self.initialized:
            raise RealDebridError("Downloader not properly initialized")

        MAX_RETRIES = 3
        RETRY_DELAY = 1.0

        last_error = None
        for attempt in range(MAX_RETRIES):
            try:
                # First verify the torrent exists by getting its info
                try:
                    torrent_info = self.get_torrent_info(torrent_id)
                    logger.debug(f"Got torrent info (attempt {attempt + 1}): {torrent_info}")
                except Exception as e:
                    if "404" in str(e):
                        logger.error(f"Torrent {torrent_id} no longer exists on Real-Debrid servers")
                        raise TorrentNotFoundError(f"Torrent {torrent_id} not found") from e
                    raise

                # If no specific files requested, select all files
                if not files:
                    files = [str(f["id"]) for f in torrent_info.get("files", [])]
                    logger.debug(f"Selecting all files: {files}")

                # Verify file IDs are valid
                available_files = {str(f["id"]) for f in torrent_info.get("files", [])}
                invalid_files = set(files) - available_files
                if invalid_files:
                    logger.error(f"Invalid file IDs for torrent {torrent_id}: {invalid_files}")
                    raise InvalidFileIDError(f"Invalid file IDs: {invalid_files}")

                # Select the files
                try:
                    data = {"files": ",".join(files)}
                    logger.debug(f"Selecting files with data: {data}")
                    self.api.request_handler.execute(
                        HttpMethod.POST,
                        f"torrents/selectFiles/{torrent_id}",
                        data=data
                    )
                    return  # Success, exit retry loop
                except Exception as e:
                    if "404" in str(e):
                        logger.error(f"Torrent {torrent_id} was removed while selecting files")
                        raise TorrentNotFoundError(f"Torrent {torrent_id} was removed") from e
                    raise

            except (TorrentNotFoundError, InvalidFileIDError):
                raise  # Don't retry these errors
            except Exception as e:
                last_error = e
                if attempt < MAX_RETRIES - 1:
                    logger.warning(f"Failed to select files (attempt {attempt + 1}/{MAX_RETRIES}): {str(e)}")
                    time.sleep(RETRY_DELAY)
                continue

        logger.error(f"Failed to select files for torrent {torrent_id} after {MAX_RETRIES} attempts")
        raise last_error if last_error else RealDebridError("Failed to select files")

    def get_torrent_info(self, torrent_id: str) -> dict:
        """
        Get information about a torrent
        Required by DownloaderBase
        """
        if not self.initialized:
            raise RealDebridError("Downloader not properly initialized")

        try:
            info = self.api.request_handler.execute(HttpMethod.GET, f"torrents/info/{torrent_id}")
            logger.debug(f"Torrent info response: {info}")
            return info
        except Exception as e:
            logger.error(f"Failed to get torrent info for {torrent_id}: {str(e)}")
            raise

    def delete_torrent(self, torrent_id: str):
        """
        Delete a torrent
        Required by DownloaderBase
        """

        if not self.initialized:
            raise RealDebridError("Downloader not properly initialized")

        try:
            self.api.request_handler.execute(HttpMethod.DELETE, f"torrents/delete/{torrent_id}")
        except Exception as e:
            logger.error(f"Failed to delete torrent {torrent_id}: {str(e)}")
            raise

    def _process_files(self, files: List[dict]) -> Dict[str, dict]:
        """Process and filter valid video files"""
        result = {}
        for file in files:
            name = file.get("path", "").lower()
            size = file.get("bytes", 0)
            if any(name.endswith(f".{ext}") for ext in VIDEO_EXTENSIONS):
                result[str(file["id"])] = {"filename": file["path"], "filesize": size}
                logger.debug(f"Found valid video file: {name} (size: {size} bytes)")
        
        if not result:
            logger.debug(f"No valid video files found among: {[f.get('path', '') for f in files]}")
        return result

    def wait_for_download(self, torrent_id: str) -> dict:
        """Wait for torrent to finish downloading"""
        start_time = time.time()
        
        while True:
            info = self.get_torrent_info(torrent_id)
            status = RDTorrentStatus(info.get("status", ""))
            seeders = info.get("seeders", 0)
            logger.debug(f"Torrent {torrent_id} status: {status}, seeders: {seeders}")

            if status == RDTorrentStatus.DOWNLOADED:
                return info
            elif status in (RDTorrentStatus.ERROR, RDTorrentStatus.MAGNET_ERROR, RDTorrentStatus.DEAD):
                logger.error(f"Download failed with status: {status}")
                raise DownloadFailedError(f"Download failed with status: {status}")
            
            # Check at 1-minute mark if download hasn't completed and has no seeders
            elapsed_time = time.time() - start_time
            if elapsed_time > 60 and seeders == 0:  # 5 minutes = 300 seconds
                logger.error(f"Torrent {torrent_id} not completed in 5 minutes and has no seeders")
                self.delete_torrent(torrent_id)
                raise DownloadFailedError("Download not completed in 5 minutes and no seeders available")
            elif elapsed_time > self.DOWNLOAD_TIMEOUT:
                logger.error("Download timeout exceeded")
                self.delete_torrent(torrent_id)
                raise DownloadFailedError("Download timeout exceeded")

            # Log progress if available
            if "progress" in info:
                logger.debug(f"Download progress for {torrent_id}: {info['progress']}%")

            time.sleep(self.DOWNLOAD_POLL_INTERVAL)

    def download_cached_stream(self, item: MediaItem, stream: Stream) -> DownloadCachedStreamResult:
        """Download a stream from Real-Debrid"""
        if not self.initialized:
            raise RealDebridError("Downloader not properly initialized")

        torrent_id = None
        try:
            # Add torrent and get initial info
            torrent_id = self.add_torrent(stream.infohash)
            info = self.get_torrent_info(torrent_id)

            # Process files to find valid video files
            files = info.get("files", [])
            container = self._process_files(files)
            if not container:
                logger.debug(f"No valid video files found in torrent {torrent_id}")
                return DownloadCachedStreamResult(None, torrent_id, info, stream.infohash)

            # Select all files by default
            self.select_files(torrent_id, list(container.keys()))

            # Wait for download to complete
            info = self.wait_for_download(torrent_id)
            
            logger.log("DEBRID", f"Downloading {item.log_string} from '{stream.raw_title}' [{stream.infohash}]")
            return DownloadCachedStreamResult(container, torrent_id, info, stream.infohash)
            
        except Exception as e:
            # Clean up torrent if something goes wrong
            if torrent_id:
                try:
                    self.delete_torrent(torrent_id)
                except Exception as delete_error:
                    logger.error(f"Failed to delete torrent {torrent_id} after error: {delete_error}")
            raise