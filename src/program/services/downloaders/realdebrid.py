import time
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Union
from collections import defaultdict

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
    QUEUED = "queued"

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
        self.active_downloads = defaultdict(set)  # {content_id: set(torrent_ids)}
        self.download_complete = {}  # Track if a content's download is complete
        self.MAX_CONCURRENT_TOTAL = 10
        self.MAX_CONCURRENT_PER_CONTENT = 3

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

        max_retries = 5
        base_delay = 2  # Start with 2 seconds delay
        
        for attempt in range(max_retries):
            try:
                # Try to add the torrent and immediately select files
                magnet = f"magnet:?xt=urn:btih:{infohash}"
                logger.debug(f"Adding torrent with magnet: {magnet}")
                
                response = self.api.request_handler.execute(
                    HttpMethod.POST,
                    "torrents/addMagnet",
                    data={"magnet": magnet}
                )
                
                torrent_id = response.get("id")
                if not torrent_id:
                    logger.error(f"Invalid response from Real-Debrid: {response}")
                    raise RealDebridError("No torrent ID in response")

                # Get initial torrent info
                info = self.get_torrent_info(torrent_id)
                filename = info.get("filename", "Unknown")
                logger.debug(f"Add torrent response for '{filename}': {response}")
                logger.debug(f"Initial torrent info: {info}")

                # Immediately select all files to prevent torrent removal
                try:
                    self.select_files(torrent_id, [])
                except Exception as e:
                    logger.error(f"Failed to select files for '{filename}': {str(e)}")
                    # If selection fails, try to clean up
                    try:
                        self.delete_torrent(torrent_id)
                    except Exception as delete_error:
                        logger.error(f"Failed to delete torrent '{filename}': {str(delete_error)}")
                    raise e

                return torrent_id

            except Exception as e:
                if "Rate limit exceeded" in str(e):
                    if attempt < max_retries - 1:
                        delay = base_delay * (2 ** attempt)  # Exponential backoff
                        logger.warning(f"Rate limit hit, retrying in {delay} seconds (attempt {attempt + 1}/{max_retries})")
                        time.sleep(delay)
                        continue
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

        response = self.api.request_handler.execute(
            HttpMethod.GET,
            f"torrents/info/{torrent_id}"
        )
        
        # Log a cleaner version with just the important info
        if response:
            status = response.get('status', 'unknown')
            progress = response.get('progress', 0)
            speed = response.get('speed', 0)
            seeders = response.get('seeders', 0)
            filename = response.get('filename', 'unknown')
            
            speed_mb = speed / 1000000 if speed else 0  # Convert to MB/s
            
            logger.debug(
                f"Torrent: {filename}\n"
                f"Status: \033[94m{status}\033[0m, "
                f"Progress: \033[95m{progress}%\033[0m, "
                f"Speed: \033[92m{speed_mb:.2f}MB/s\033[0m, "
                f"Seeders: \033[93m{seeders}\033[0m"
            )
            
        return response

    def delete_torrent(self, torrent_id: str):
        """
        Delete a torrent
        Required by DownloaderBase
        """
        if not self.initialized:
            raise RealDebridError("Downloader not properly initialized")

        try:
            self.api.request_handler.execute(
                HttpMethod.DELETE,
                f"torrents/delete/{torrent_id}"
            )
        except Exception as e:
            error_str = str(e)
            if "404" in error_str:
                # Could mean: already deleted, invalid ID, or never existed
                logger.warning(f"Could not delete torrent {torrent_id}: Unknown resource (404)")
                return
            elif "401" in error_str:
                logger.error(f"Failed to delete torrent {torrent_id}: Bad token (expired/invalid)")
                raise
            elif "403" in error_str:
                logger.error(f"Failed to delete torrent {torrent_id}: Permission denied (account locked)")
                raise
            else:
                logger.error(f"Failed to delete torrent {torrent_id}: {error_str}")
                raise

    def _process_files(self, files: List[dict]) -> Dict[str, dict]:
        """Process and filter valid video files"""
        result = {}
        for file in files:
            path = file.get("path", "")
            name = path.lower()
            size = file.get("bytes", 0)
            if any(name.endswith(f".{ext}") for ext in VIDEO_EXTENSIONS):
                # Extract parent folder name from path
                path_parts = path.split("/")
                parent_path = path_parts[-2] if len(path_parts) > 1 else ""
                
                result[str(file["id"])] = {
                    "filename": path,
                    "filesize": size,
                    "parent_path": parent_path
                }
                logger.debug(f"Found valid video file: {name} (size: {size} bytes, parent: {parent_path})")
        
        if not result:
            logger.debug(f"No valid video files found among: {[f.get('path', '') for f in files]}")
        return result

    def _can_start_download(self, content_id: str) -> bool:
        """Check if we can start a new download for this content."""
        # If any download for this content is complete, don't start new ones
        if content_id in self.download_complete and self.download_complete[content_id]:
            return False
            
        # Check content-specific concurrent limit
        if len(self.active_downloads[content_id]) >= self.MAX_CONCURRENT_PER_CONTENT:
            return False
            
        # Check total concurrent limit
        total_downloads = sum(len(downloads) for downloads in self.active_downloads.values())
        return total_downloads < self.MAX_CONCURRENT_TOTAL

    def _add_active_download(self, content_id: str, torrent_id: str):
        """Add a download to active downloads tracking."""
        self.active_downloads[content_id].add(torrent_id)

    def _remove_active_download(self, content_id: str, torrent_id: str):
        """Remove a download from active downloads tracking."""
        if content_id in self.active_downloads:
            self.active_downloads[content_id].discard(torrent_id)
            if not self.active_downloads[content_id]:
                del self.active_downloads[content_id]

    def _mark_content_complete(self, content_id: str):
        """Mark a content as having completed download."""
        self.download_complete[content_id] = True

    def _is_content_complete(self, content_id: str) -> bool:
        """Check if content has completed download."""
        return content_id in self.download_complete and self.download_complete[content_id]

    def download_cached_stream(self, item: MediaItem, stream: Stream) -> DownloadCachedStreamResult:
        """Download a stream from Real-Debrid"""
        if not self.initialized:
            raise RealDebridError("Downloader not properly initialized")

        content_id = str(item.id)

        # Check if content already has a successful download
        if self._is_content_complete(content_id):
            logger.info(f"Skipping download for {item.log_string} - another download already completed")
            return DownloadCachedStreamResult(None, None, None, stream.infohash)

        # Check if we can start a new download for this content
        if not self._can_start_download(content_id):
            logger.warning(f"Cannot start download for {item.log_string} - max concurrent downloads reached")
            return DownloadCachedStreamResult(None, None, None, stream.infohash)

        torrent_id = None
        try:
            # Add torrent and get initial info
            torrent_id = self.add_torrent(stream.infohash)
            self._add_active_download(content_id, torrent_id)
            
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
            
            # Mark content as complete since download succeeded
            self._mark_content_complete(content_id)
            
            return DownloadCachedStreamResult(container, torrent_id, info, stream.infohash)
            
        except Exception as e:
            # Clean up torrent if something goes wrong
            if torrent_id:
                try:
                    self.delete_torrent(torrent_id)
                except Exception as delete_error:
                    logger.error(f"Failed to delete torrent {torrent_id} after error: {delete_error}")
            raise
        finally:
            if torrent_id:
                self._remove_active_download(content_id, torrent_id)

    def wait_for_download(self, torrent_id: str) -> dict:
        """Wait for torrent to finish downloading"""
        start_time = time.time()
        last_check_time = time.time()
        zero_seeder_count = 0  # Track consecutive zero seeder checks
        
        while True:
            info = self.get_torrent_info(torrent_id)
            status = RDTorrentStatus(info.get("status", ""))
            seeders = info.get("seeders", 0)
            filename = info.get("filename", "Unknown")
            progress = info.get("progress", 0)
            current_time = time.time()
            
            # Skip queued torrents immediately
            if status == RDTorrentStatus.QUEUED:
                logger.debug(f"{filename} is queued, skipping to next stream")
                raise DownloadFailedError(f"{filename} is queued on Real-Debrid")
            
            # Check status and seeders every minute
            if current_time - last_check_time >= 60:  # Check every minute
                logger.debug(f"{filename} status: {status}, seeders: {seeders}")
                if "progress" in info:
                    logger.debug(f"{filename} progress: \033[95m{progress}%\033[0m")
                    
                # Only check seeders if download is not complete
                if progress < 100 and status == RDTorrentStatus.DOWNLOADING:
                    if seeders == 0:
                        zero_seeder_count += 1
                        logger.debug(f"{filename} has no seeders ({zero_seeder_count}/2 checks)")
                        if zero_seeder_count >= 2:  # Give up after 2 consecutive zero seeder checks
                            logger.error(f"{filename} has no seeders available after 2 consecutive checks")
                            self.delete_torrent(torrent_id)
                            raise DownloadFailedError(f"{filename} has no seeders available after 2 consecutive checks")
                    else:
                        zero_seeder_count = 0  # Reset counter if we find seeders
                    
                last_check_time = current_time

            if status == RDTorrentStatus.DOWNLOADED:
                return info
            elif status in (RDTorrentStatus.ERROR, RDTorrentStatus.MAGNET_ERROR, RDTorrentStatus.DEAD):
                logger.error(f"{filename} failed with status: {status}")
                self.delete_torrent(torrent_id)
                raise DownloadFailedError(f"{filename} failed with status: {status}")

            # Check if we've exceeded the timeout
            if current_time - start_time > self.DOWNLOAD_TIMEOUT:
                logger.error(f"{filename} download timed out after {self.DOWNLOAD_TIMEOUT} seconds")
                self.delete_torrent(torrent_id)
                raise DownloadFailedError(f"{filename} download timed out")

            time.sleep(self.DOWNLOAD_POLL_INTERVAL)