import time
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Union
from collections import defaultdict
from datetime import timedelta

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

class QueuedTooManyTimesError(RealDebridError):
    """Raised when a torrent is queued too many times"""

class RealDebridActiveLimitError(RealDebridError):
    """Raised when Real-Debrid's active torrent limit is exceeded"""

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
    BASE_TIMEOUT = 300  # 5 minutes
    MAX_TIMEOUT = 1800  # 30 minutes
    TIMEOUT_PER_50MB = 10  # 10 seconds per 50MB
    MAX_QUEUE_ATTEMPTS = 6  # Maximum number of queued torrents before retrying item later
    
    def __init__(self):
        self.key = "realdebrid"
        self.settings = settings_manager.settings.downloaders.real_debrid
        self.scraping_settings = settings_manager.settings.scraping
        self.api = None
        self.file_finder = None
        self.initialized = self.validate()
        self.active_downloads = defaultdict(set)  # {content_id: set(torrent_ids)}
        self.download_complete = {}  # Track if a content's download is complete
        self.queue_attempts = defaultdict(int)  # Track number of queued attempts per content
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
        """Add a torrent to Real-Debrid and return the torrent ID"""
        if not self.initialized:
            raise RealDebridError("Downloader not properly initialized")

        magnet = f"magnet:?xt=urn:btih:{infohash}"
        logger.debug(f"Adding torrent with magnet: {magnet}")
        
        try:
            response = self.api.request_handler.execute(HttpMethod.POST, "torrents/addMagnet", data={"magnet": magnet})
            return response["id"]
        except RealDebridError as e:
            if "509 Server Error: Active Limit Exceeded" in str(e):
                # Try to clean up inactive torrents
                cleaned = self._cleanup_inactive_torrents()
                if cleaned > 0:
                    # Try adding the torrent again if we cleaned some up
                    try:
                        response = self.api.request_handler.execute(HttpMethod.POST, "torrents/addMagnet", data={"magnet": magnet})
                        logger.info(f"Successfully added torrent after cleaning up {cleaned} inactive/stalled torrents")
                        return response["id"]
                    except:
                        pass  # If it fails again, raise the original error
                
                logger.warning(f"Real-Debrid active torrent limit exceeded for {infohash}")
                raise RealDebridActiveLimitError(f"Real-Debrid active torrent limit exceeded") from e
            
            # Handle rate limit errors
            if "429" in str(e):
                delay = 1.0
                if isinstance(e, RealDebridError) and e.retry_after:
                    delay = e.retry_after
                logger.warning(f"Rate limited by Real-Debrid, waiting {delay}s before retry")
                time.sleep(delay)
                return self.add_torrent(infohash)
                
            logger.error(f"Failed to add torrent {infohash}: {e}")
            raise

    def _cleanup_inactive_torrents(self) -> int:
        """Clean up inactive, errored, or stalled torrents to free up slots.
        Returns number of torrents cleaned up."""
        try:
            # Get list of all torrents
            torrents = self.api.request_handler.execute(HttpMethod.GET, "torrents")
            cleaned = 0
            
            for torrent in torrents:
                status = torrent.get("status", "")
                
                # Clean up error states, unknown status, and queued torrents
                if status in ("error", "magnet_error", "virus", "dead", "unknown", "queued"):
                    try:
                        self.delete_torrent(torrent["id"])
                        cleaned += 1
                        logger.debug(f"Cleaned up torrent {torrent['id']} with status {status}")
                        continue
                    except Exception as e:
                        logger.error(f"Failed to delete torrent {torrent['id']}: {e}")
                
                # Clean up stalled downloads (0% progress)
                if status == "downloading":
                    progress = torrent.get("progress", 0)
                    if progress == 0:
                        try:
                            self.delete_torrent(torrent["id"])
                            cleaned += 1
                            logger.debug(f"Cleaned up stalled torrent {torrent['id']} with 0% progress")
                        except Exception as e:
                            logger.error(f"Failed to delete torrent {torrent['id']}: {e}")
            
            if cleaned > 0:
                logger.info(f"Cleaned up {cleaned} inactive/stalled torrents")
            return cleaned
            
        except Exception as e:
            logger.error(f"Failed to cleanup inactive torrents: {e}")
            return 0

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
                except Exception as e:
                    if "404" in str(e):
                        logger.error(f"Torrent {torrent_id} no longer exists on Real-Debrid servers")
                        raise TorrentNotFoundError(f"Torrent {torrent_id} not found") from e
                    raise

                # If no specific files requested, select all files
                if not files:
                    files = [str(f["id"]) for f in torrent_info.get("files", [])]

                # Verify file IDs are valid
                available_files = {str(f["id"]) for f in torrent_info.get("files", [])}
                invalid_files = set(files) - available_files
                if invalid_files:
                    logger.error(f"Invalid file IDs for torrent {torrent_id}: {invalid_files}")
                    raise InvalidFileIDError(f"Invalid file IDs: {invalid_files}")

                # Select the files
                try:
                    data = {"files": ",".join(files)}
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
        logger.debug(f"Processing {len(files)} files from Real-Debrid")
        result = {}
        for file in files:
            path = file.get("path", "")
            name = path.lower()
            size = file.get("bytes", 0)
            
            # Log each file being checked
            logger.debug(f"Checking file: {path} (size: {size} bytes)")
            
            if any(name.endswith(f".{ext}") for ext in VIDEO_EXTENSIONS):
                # Extract parent folder name from path
                path_parts = path.split("/")
                parent_path = path_parts[-2] if len(path_parts) > 1 else ""
                
                result[str(file["id"])] = {
                    "filename": path,
                    "filesize": size,
                    "parent_path": parent_path
                }
                logger.debug(f"✓ Found valid video file: {name} (size: {size} bytes, parent: {parent_path})")
            else:
                # Log why file was rejected
                extensions = [ext for ext in VIDEO_EXTENSIONS if name.endswith(f".{ext}")]
                if not extensions:
                    logger.debug(f"✗ Skipped file: {name} - not a video file (valid extensions: {VIDEO_EXTENSIONS})")
        
        if not result:
            logger.debug("No valid video files found. Files received:")
            for file in files:
                logger.debug(f"- {file.get('path', '')} ({file.get('bytes', 0)} bytes)")
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
        torrent_id = None

        try:
            # Add torrent and get initial info to check files
            torrent_id = self.add_torrent(stream.infohash)
            info = self.get_torrent_info(torrent_id)

            # Process files to find valid video files
            files = info.get("files", [])
            container = self._process_files(files)
            if not container:
                logger.debug(f"No valid video files found in torrent {torrent_id}")
                return DownloadCachedStreamResult(None, torrent_id, info, stream.infohash)

            # Check if we can start a new download for this content
            if not self._can_start_download(content_id):
                logger.warning(f"Cannot start download for {item.log_string} - max concurrent downloads reached")
                return DownloadCachedStreamResult(container, torrent_id, info, stream.infohash)

            # If content is complete but we found valid files, proceed with download
            if self._is_content_complete(content_id):
                logger.info(f"Content {item.log_string} marked as complete but valid files found - proceeding with download")
            
            self._add_active_download(content_id, torrent_id)

            # Select all files by default
            self.select_files(torrent_id, list(container.keys()))

            # Wait for download to complete
            info = self.wait_for_download(torrent_id, content_id, item)
            
            logger.log("DEBRID", f"Downloading {item.log_string} from '{stream.raw_title}' [{stream.infohash}]")
            
            # Mark content as complete since download succeeded
            self._mark_content_complete(content_id)
            # Reset queue attempts on successful download
            self.queue_attempts[content_id] = 0
            
            return DownloadCachedStreamResult(container, torrent_id, info, stream.infohash)
            
        except RealDebridActiveLimitError:
            # Don't blacklist the stream, mark for retry after a short delay
            retry_time = datetime.now() + timedelta(minutes=30)  # Retry after 30 minutes
            logger.warning(f"Real-Debrid active limit exceeded for {item.log_string}, will retry after 30 minutes")
            item.set("retry_after", retry_time)
            return DownloadCachedStreamResult(None, torrent_id, None, stream.infohash)
        except QueuedTooManyTimesError:
            # Don't blacklist the stream, but mark the item for retry later based on scrape count
            retry_hours = self._get_retry_hours(item.scraped_times)
            retry_time = datetime.now() + timedelta(hours=retry_hours)
            logger.warning(f"Too many queued attempts for {item.log_string}, will retry after {retry_hours} hours")
            item.set("retry_after", retry_time)
            return DownloadCachedStreamResult(container if 'container' in locals() else None, torrent_id, None, stream.infohash)
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

    def _get_retry_hours(self, scrape_times: int) -> float:
        """Get retry hours based on number of scrape attempts."""
        if scrape_times >= 10:
            return self.scraping_settings.after_10
        elif scrape_times >= 5:
            return self.scraping_settings.after_5
        elif scrape_times >= 2:
            return self.scraping_settings.after_2
        return 2.0  # Default to 2 hours

    def wait_for_download(self, torrent_id: str, content_id: str, item: MediaItem) -> dict:
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
            
            # Handle queued torrents
            if status == RDTorrentStatus.QUEUED:
                self.queue_attempts[content_id] += 1
                if self.queue_attempts[content_id] >= self.MAX_QUEUE_ATTEMPTS:
                    logger.warning(f"Hit maximum queue attempts ({self.MAX_QUEUE_ATTEMPTS}) for content {content_id}")
                    raise QueuedTooManyTimesError(f"Too many queued attempts for {filename}")
                
                logger.debug(f"{filename} is queued on Real-Debrid (attempt {self.queue_attempts[content_id]}/{self.MAX_QUEUE_ATTEMPTS}), blacklisting and trying next stream")
                raise DownloadFailedError(f"{filename} is queued on Real-Debrid")
            
            # Use dynamic timeout based on file size and progress
            file_size_mb = info.get("bytes", 0) / (1024 * 1024)  # Convert to MB
            size_based_timeout = (file_size_mb / 50) * self.TIMEOUT_PER_50MB  # 10 seconds per 50MB
            timeout = min(
                self.BASE_TIMEOUT + size_based_timeout,
                self.MAX_TIMEOUT
            )
            
            # Log timeout calculation on first check
            if not hasattr(self, '_logged_timeout') and size_based_timeout > 0:
                logger.debug(
                    f"Timeout calculation for {filename}:\n"
                    f"  File size: {file_size_mb:.1f}MB\n"
                    f"  Base timeout: {self.BASE_TIMEOUT}s\n"
                    f"  Size-based addition: {size_based_timeout:.1f}s\n"
                    f"  Total timeout: {timeout:.1f}s"
                )
                self._logged_timeout = True
            
            if current_time - start_time > timeout:
                logger.warning(f"{filename} download taking too long ({int(timeout)} seconds), skipping and trying next stream")
                # Don't delete torrent, just break and let Real-Debrid continue in background
                break

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
                            logger.warning(f"{filename} has no seeders available after 2 consecutive checks, skipping and trying next stream")
                            break
                    else:
                        zero_seeder_count = 0  # Reset counter if we find seeders
                    
                last_check_time = current_time

            if status == RDTorrentStatus.DOWNLOADED:
                return info
            elif status in (RDTorrentStatus.ERROR, RDTorrentStatus.MAGNET_ERROR, RDTorrentStatus.DEAD):
                logger.error(f"{filename} failed with status: {status}")
                # Don't delete torrent, just skip and try next stream
                break

            time.sleep(self.DOWNLOAD_POLL_INTERVAL)
        
        # If we broke out of loop due to timeout, no seeders, or error status
        if current_time - start_time > timeout:
            raise DownloadFailedError(f"{filename} download taking too long")
        elif zero_seeder_count >= 2:
            raise DownloadFailedError(f"{filename} has no seeders available")
        elif status in (RDTorrentStatus.ERROR, RDTorrentStatus.MAGNET_ERROR, RDTorrentStatus.DEAD):
            raise DownloadFailedError(f"{filename} failed with status: {status}")