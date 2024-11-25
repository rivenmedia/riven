import time
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Set, Tuple, Union
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
    CLEANUP_INTERVAL = 60  # Check every minute instead of 5 minutes
    CLEANUP_MINIMAL_PROGRESS_TIME = 900  # 15 minutes instead of 30
    CLEANUP_MINIMAL_PROGRESS_THRESHOLD = 5  # 5% instead of 1%
    CLEANUP_STUCK_UPLOAD_TIME = 1800  # 30 minutes instead of 1 hour
    CLEANUP_STUCK_COMPRESSION_TIME = 900  # 15 minutes instead of 30
    CLEANUP_BATCH_SIZE = 10  # Process deletions in batches
    CLEANUP_SPEED_THRESHOLD = 50000  # 50 KB/s minimum speed
    CLEANUP_INACTIVE_TIME = 300  # 5 minutes of inactivity
    MAX_CONCURRENT_TOTAL = 5  # Reduced from 10 to 5
    MAX_CONCURRENT_PER_CONTENT = 2  # Reduced from 3 to 2

    def __init__(self, api_key: str, proxy_url: Optional[str] = None):
        super().__init__()
        self.api = RealDebridAPI(api_key, proxy_url)
        self.initialized = True
        self.download_complete = {}
        self.active_downloads = defaultdict(set)
        self.queue_attempts = {}
        self.last_cleanup_time = datetime.now()
        self.scraping_settings = settings_manager.get("scraping")

    def _cleanup(self) -> int:
        """Clean up torrents that are no longer needed"""
        try:
            current_time = datetime.now()
            if (current_time - self.last_cleanup_time).total_seconds() < self.CLEANUP_INTERVAL:
                return 0

            # Get current torrents
            torrents = self.api.request_handler.execute(HttpMethod.GET, "torrents")
            if not torrents:
                return 0

            # Get current downloads
            downloads = self.api.request_handler.execute(HttpMethod.GET, "downloads")

            # Get active torrents by status
            active_by_status = defaultdict(list)
            for torrent in torrents:
                status = torrent.get("status", "")
                active_by_status[status].append(torrent)

            # Get active torrent count by status
            active_count = defaultdict(int)
            for status, torrents in active_by_status.items():
                active_count[status] = len(torrents)

            # Get total active torrents
            total_active = sum(active_count.values())

            # Get limit from settings
            limit = self.MAX_CONCURRENT_TOTAL

            # Mark torrents for deletion
            to_delete = []
            for status, torrents in active_by_status.items():
                for torrent in torrents:
                    torrent_id = torrent.get("id", "")
                    filename = torrent.get("filename", "")
                    status = torrent.get("status", "")
                    progress = torrent.get("progress", 0)
                    speed = torrent.get("speed", 0)
                    seeders = torrent.get("seeders", 0)
                    time_elapsed = torrent.get("time_elapsed", 0)

                    # Case 1: Completed torrents
                    if status == RDTorrentStatus.DOWNLOADED:
                        reason = "download completed"
                        to_delete.append((0, torrent_id, reason, time_elapsed))

                    # Case 2: Stuck torrents
                    elif status == RDTorrentStatus.DOWNLOADING and speed == 0 and time_elapsed > self.CLEANUP_INACTIVE_TIME:
                        reason = "download is stuck (zero speed)"
                        to_delete.append((1, torrent_id, reason, time_elapsed))

                    # Case 3: Torrents with zero progress
                    elif status == RDTorrentStatus.DOWNLOADING and progress == 0 and time_elapsed > self.CLEANUP_MINIMAL_PROGRESS_TIME:
                        reason = "download has zero progress"
                        to_delete.append((2, torrent_id, reason, time_elapsed))

                    # Case 4: Torrents with minimal progress
                    elif status == RDTorrentStatus.DOWNLOADING and progress < self.CLEANUP_MINIMAL_PROGRESS_THRESHOLD and time_elapsed > self.CLEANUP_MINIMAL_PROGRESS_TIME:
                        reason = f"download has minimal progress ({progress}%)"
                        to_delete.append((3, torrent_id, reason, time_elapsed))

                    # Case 5: Stuck uploading torrents
                    elif status == RDTorrentStatus.UPLOADING and speed == 0 and time_elapsed > self.CLEANUP_STUCK_UPLOAD_TIME:
                        reason = "upload is stuck (zero speed)"
                        to_delete.append((4, torrent_id, reason, time_elapsed))

                    # Case 6: Stuck compressing torrents
                    elif status == RDTorrentStatus.COMPRESSING and speed == 0 and time_elapsed > self.CLEANUP_STUCK_COMPRESSION_TIME:
                        reason = "compression is stuck (zero speed)"
                        to_delete.append((5, torrent_id, reason, time_elapsed))

                    # Case 7: Torrents with no seeders
                    elif status == RDTorrentStatus.DOWNLOADING and seeders == 0 and time_elapsed > self.CLEANUP_INACTIVE_TIME:
                        reason = "download has no seeders"
                        to_delete.append((6, torrent_id, reason, time_elapsed))

                    # Case 8: Waiting files selection
                    elif status == RDTorrentStatus.WAITING_FILES:
                        reason = "waiting files selection"
                        to_delete.append((7, torrent_id, reason, time_elapsed))

            # If no torrents were marked for deletion but we're still over limit,
            # force delete the slowest/least progressed torrents
            if not to_delete and total_active > active_count["limit"]:
                logger.info("No torrents met deletion criteria but still over limit, using fallback cleanup")
                
                # First try to clean up just duplicates
                duplicates_only = True
                cleanup_attempts = 2  # Try duplicates first, then all torrents if needed
                
                while cleanup_attempts > 0:
                    # Collect all active torrents into a single list for sorting
                    all_active = []
                    seen_filenames = set()
                    
                    for status, torrents in active_by_status.items():
                        for t in torrents:
                            filename = t["filename"]
                            
                            # Skip non-duplicates on first pass
                            is_duplicate = filename in seen_filenames
                            if duplicates_only and not is_duplicate:
                                continue
                            
                            seen_filenames.add(filename)
                            
                            score = 0
                            # Prioritize keeping torrents with more progress
                            score += t["progress"] * 100
                            # And those with higher speeds
                            score += min(t["speed"] / 1024, 1000)  # Cap speed bonus at 1000
                            # And those with more seeders
                            score += t["seeders"] * 10
                            # Penalize older torrents slightly
                            score -= min(t["time_elapsed"] / 60, 60)  # Cap age penalty at 60 minutes
                            # Heavy penalty for duplicates
                            if is_duplicate:
                                score -= 5000  # Ensure duplicates are cleaned up first
                            
                            all_active.append({
                                "id": t["id"],
                                "score": score,
                                "stats": t,
                                "status": status,
                                "is_duplicate": is_duplicate
                            })
                    
                    if all_active:
                        # Sort by score (lowest first - these will be deleted)
                        all_active.sort(key=lambda x: x["score"])
                        
                        # Take enough torrents to get under the limit
                        to_remove = min(
                            len(all_active),  # Don't try to remove more than we have
                            total_active - active_count["limit"] + 1  # +1 for safety margin
                        )
                        
                        for torrent in all_active[:to_remove]:
                            stats = torrent["stats"]
                            reason = (f"fallback cleanup{' (duplicate)' if duplicates_only else ''} - {torrent['status']} "
                                    f"(progress: {stats['progress']}%, "
                                    f"speed: {stats['speed']/1024:.1f} KB/s, "
                                    f"seeders: {stats['seeders']}, "
                                    f"age: {stats['time_elapsed']/60:.1f}m)")
                            to_delete.append((0, torrent["id"], reason, stats["time_elapsed"]))
                            logger.info(f"Fallback cleanup marking: {stats['filename']} - {reason}")
                        
                        # If we found enough torrents to delete, we're done
                        if len(to_delete) >= (total_active - active_count["limit"]):
                            break
                    
                    # If we get here and duplicates_only is True, try again with all torrents
                    duplicates_only = False
                    cleanup_attempts -= 1
                
                # Log what we're about to delete
                if to_delete:
                    logger.info(f"Found {len(to_delete)} torrents to clean up, processing in batches of {self.CLEANUP_BATCH_SIZE}")
                    for _, _, reason, _ in to_delete[:5]:  # Log first 5 for debugging
                        logger.debug(f"Will delete: {reason}")
            
            # Convert to final format
            to_delete = [(t[1], t[2]) for t in to_delete]
            
            # Process deletion in batches
            while to_delete:
                batch = to_delete[:self.CLEANUP_BATCH_SIZE]
                to_delete = to_delete[self.CLEANUP_BATCH_SIZE:]
                cleaned += self._batch_delete_torrents(batch)
            
            # Update last cleanup time if any torrents were cleaned
            if cleaned > 0:
                self.last_cleanup_time = current_time
                logger.info(f"Cleaned up {cleaned} torrents")
            else:
                logger.warning("No torrents were cleaned up despite being over the limit!")
            
            return cleaned
            
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")
            return 0

    def _batch_delete_torrents(self, torrents: List[Tuple[str, str]]) -> int:
        """Delete a batch of torrents efficiently.
        Args:
            torrents: List of (torrent_id, reason) tuples
        Returns:
            Number of successfully deleted torrents
        """
        deleted = 0
        for torrent_id, reason in torrents:
            try:
                # First try to delete associated downloads
                try:
                    downloads = self.api.request_handler.execute(HttpMethod.GET, "downloads")
                    for download in downloads:
                        if download.get("torrent_id") == torrent_id:
                            try:
                                self.api.request_handler.execute(HttpMethod.DELETE, f"downloads/delete/{download['id']}")
                                logger.debug(f"Deleted download {download['id']} associated with torrent {torrent_id}")
                            except Exception as e:
                                logger.warning(f"Failed to delete download {download['id']}: {e}")
                except Exception as e:
                    logger.warning(f"Failed to cleanup downloads for torrent {torrent_id}: {e}")

                # Then delete the torrent
                self.api.request_handler.execute(HttpMethod.DELETE, f"torrents/delete/{torrent_id}")
                logger.info(f"Deleted torrent {torrent_id}: {reason}")
                deleted += 1
            except Exception as e:
                if "404" in str(e):
                    # Torrent was already deleted, count it as success
                    logger.debug(f"Torrent {torrent_id} was already deleted")
                    deleted += 1
                elif "401" in str(e):
                    logger.error("API token expired or invalid")
                    break  # Stop processing batch
                elif "403" in str(e):
                    logger.error("Account locked or permission denied")
                    break  # Stop processing batch
                else:
                    logger.error(f"Failed to delete torrent {torrent_id}: {e}")
        return deleted

    def _cleanup_downloads(self) -> int:
        """Clean up old downloads that are no longer needed.
        Returns number of downloads cleaned up."""
        try:
            downloads = self.api.request_handler.execute(HttpMethod.GET, "downloads")
            if not isinstance(downloads, list):
                logger.error(f"Unexpected downloads response type: {type(downloads)}")
                return 0
                
            deleted = 0
            
            # Get current torrents for reference
            try:
                torrents = {t["id"]: t for t in self.api.request_handler.execute(HttpMethod.GET, "torrents")}
            except Exception as e:
                logger.warning(f"Failed to get torrents list for reference: {e}")
                torrents = {}
            
            # Track active downloads to update our counters
            active_by_content = {}
            
            for download in downloads:
                try:
                    if not isinstance(download, dict):
                        logger.warning(f"Unexpected download entry type: {type(download)}")
                        continue
                        
                    download_id = download.get("id")
                    torrent_id = download.get("torrent_id")
                    filename = download.get("filename", "unknown")
                    status = download.get("status", "unknown")
                    progress = download.get("progress", 0)
                    speed = download.get("speed", 0)
                    
                    # Find content ID for this download
                    content_id = None
                    for cid, downloads in self.active_downloads.items():
                        if download_id in downloads:
                            content_id = cid
                            break
                    
                    # Track active downloads
                    if status in ("downloading", "queued"):
                        if content_id:
                            active_by_content.setdefault(content_id, set()).add(download_id)
                    
                    # Never delete successfully downloaded files
                    if status == "downloaded":
                        if content_id:
                            self.download_complete[content_id] = True
                        continue
                    
                    reason = None
                    
                    # Case 1: No associated torrent ID (but not if downloaded)
                    if not torrent_id and status != "downloaded":
                        reason = "orphaned download (no torrent ID)"
                    
                    # Case 2: Associated torrent no longer exists (but not if downloaded)
                    elif torrent_id and torrent_id not in torrents and status != "downloaded":
                        reason = f"orphaned download (torrent {torrent_id} no longer exists)"
                    
                    # Case 3: Download failed or errored
                    elif status in ("error", "magnet_error", "virus", "dead", "waiting_files_selection"):
                        reason = f"download in {status} state"
                    
                    # Case 4: Zero progress downloads (excluding queued and downloaded)
                    elif progress == 0 and status not in ("queued", "downloaded") and speed == 0:
                        reason = "download has zero progress and speed"
                    
                    # Case 5: Stuck downloads (but not if already downloaded)
                    elif status == "downloading" and speed == 0 and progress < 100 and status != "downloaded":
                        reason = "download is stuck (zero speed)"
                    
                    if reason:
                        # Double check status hasn't changed to downloaded
                        try:
                            current = self.api.request_handler.execute(HttpMethod.GET, f"downloads/info/{download_id}")
                            if isinstance(current, dict) and current.get("status") == "downloaded":
                                logger.debug(f"Skipping deletion of {download_id} ({filename}): status changed to downloaded")
                                if content_id:
                                    self.download_complete[content_id] = True
                                continue
                        except Exception as e:
                            logger.debug(f"Failed to double-check download status for {download_id}: {e}")
                        
                        try:
                            self.api.request_handler.execute(HttpMethod.DELETE, f"downloads/delete/{download_id}")
                            deleted += 1
                            logger.info(f"Deleted download {download_id} ({filename}): {reason}, status: {status}")
                            
                            # Update our tracking
                            if content_id:
                                if download_id in self.active_downloads[content_id]:
                                    self.active_downloads[content_id].remove(download_id)
                        except Exception as e:
                            if "404" in str(e):
                                deleted += 1  # Already deleted
                                logger.debug(f"Download {download_id} was already deleted")
                                # Update our tracking
                                if content_id and download_id in self.active_downloads[content_id]:
                                    self.active_downloads[content_id].remove(download_id)
                            elif "401" in str(e):
                                logger.error("API token expired or invalid")
                                break  # Stop processing
                            elif "403" in str(e):
                                logger.error("Account locked or permission denied")
                                break  # Stop processing
                            else:
                                logger.warning(f"Failed to delete download {download_id}: {e}")
                
                except Exception as e:
                    logger.warning(f"Failed to process download {download.get('id')}: {e}")
            
            # Update our active downloads tracking
            for content_id in list(self.active_downloads.keys()):
                actual_active = active_by_content.get(content_id, set())
                self.active_downloads[content_id] = actual_active
            
            if deleted:
                logger.info(f"Cleaned up {deleted} downloads")
                # Log current download counts
                total = sum(len(downloads) for downloads in self.active_downloads.values())
                logger.debug(f"Current download counts - Total: {total}, By content: {dict((k, len(v)) for k, v in self.active_downloads.items())}")
            return deleted
            
        except Exception as e:
            logger.error(f"Failed to cleanup downloads: {e}")
            return 0

    def select_files(self, torrent_id: str, files: List[str]):
        """
        Select files from a torrent
        Required by DownloaderBase
        """
        if not self.initialized:
            raise RealDebridError("Downloader not properly initialized")

        MAX_RETRIES = 5
        RETRY_DELAY = 2.0
        MAX_WAIT_TIME = 30

        last_error = None
        start_time = time.time()

        for attempt in range(MAX_RETRIES):
            try:
                # First verify the torrent exists and is ready
                try:
                    torrent_info = self.get_torrent_info(torrent_id)
                    status = torrent_info.get("status", "")
                    
                    # Wait for magnet conversion to complete
                    while status == "magnet_conversion":
                        if time.time() - start_time > MAX_WAIT_TIME:
                            raise RealDebridError("Magnet conversion timeout")
                        logger.debug(f"Waiting for magnet conversion... (status: {status})")
                        time.sleep(2)
                        torrent_info = self.get_torrent_info(torrent_id)
                        status = torrent_info.get("status", "")

                    # Check if torrent is in a state where we can select files
                    if status not in ["waiting_files_selection", "downloaded"]:
                        logger.warning(f"Torrent in unexpected state: {status}, retrying...")
                        time.sleep(RETRY_DELAY)
                        continue

                except Exception as e:
                    if "404" in str(e):
                        logger.error(f"Torrent {torrent_id} no longer exists on Real-Debrid servers")
                        raise TorrentNotFoundError(f"Torrent {torrent_id} not found") from e
                    raise

                # Get available files
                available_files = torrent_info.get("files", [])
                if not available_files:
                    if time.time() - start_time > MAX_WAIT_TIME:
                        raise RealDebridError("Timeout waiting for files to become available")
                    logger.debug("No files available yet, waiting...")
                    time.sleep(RETRY_DELAY)
                    continue

                # Handle special "all" files case or no specific files requested
                if not files or (files and "all" in files):
                    files = [str(f["id"]) for f in available_files]
                    logger.debug(f"Selecting all available files: {files}")

                # Verify file IDs are valid
                valid_ids = {str(f["id"]) for f in available_files}
                invalid_files = set(files) - valid_ids
                if invalid_files:
                    logger.error(f"Invalid file IDs for torrent {torrent_id}: {invalid_files}")
                    logger.debug(f"Available file IDs: {valid_ids}")
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
                    logger.debug(f"Successfully selected files for torrent {torrent_id}")
                    return  # Success, exit retry loop
                except Exception as e:
                    if "404" in str(e):
                        logger.error(f"Torrent {torrent_id} was removed while selecting files")
                        raise TorrentNotFoundError(f"Torrent {torrent_id} was removed") from e
                    if "422" in str(e):
                        logger.error(f"Invalid file selection request: {data}")
                        logger.debug(f"Available files: {available_files}")
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
            files = response.get('files', [])
            
            speed_mb = speed / 1000000 if speed else 0  # Convert to MB/s
            
            logger.debug(
                f"Torrent: {filename}\n"
                f"Status: \033[94m{status}\033[0m, "
                f"Progress: \033[95m{progress}%\033[0m, "
                f"Speed: \033[92m{speed_mb:.2f}MB/s\033[0m, "
                f"Seeders: \033[93m{seeders}\033[0m\n"
                f"Files: {len(files)} available"
            )
            
            # Log file details if available
            if files:
                logger.debug("Available files:")
                for f in files:
                    logger.debug(f"- {f.get('path', 'unknown')} ({f.get('bytes', 0)} bytes)")
        
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
            elif "401" in str(e):
                logger.error(f"Failed to delete torrent {torrent_id}: Bad token (expired/invalid)")
                raise
            elif "403" in str(e):
                logger.error(f"Failed to delete torrent {torrent_id}: Permission denied (account locked)")
                raise
            else:
                logger.error(f"Failed to delete torrent {torrent_id}: {error_str}")
                raise

    def _process_files(self, files: List[dict]) -> Dict[str, dict]:
        """Process and filter valid video files"""
        logger.debug(f"Processing {len(files)} files from Real-Debrid")
        result = {}
        
        # If no files yet, return empty result to trigger retry
        if not files:
            logger.debug("No files available yet, will retry")
            return {}
        
        # Process all video files
        valid_videos = []
        
        for file in files:
            path = file.get("path", "")
            name = path.lower()
            size = file.get("bytes", 0)
            file_id = str(file.get("id", ""))
            
            # Skip if no valid ID
            if not file_id:
                logger.debug(f"✗ Skipped file with no ID: {path}")
                continue
        
            # Skip sample files and unwanted files
            if "/sample/" in name.lower() or "sample" in name.lower():
                logger.debug(f"✗ Skipped sample file: {name}")
                continue
            
            if any(name.endswith(f".{ext}") for ext in VIDEO_EXTENSIONS):
                valid_videos.append(file)
                logger.debug(f"✓ Found valid video file: {name} (size: {size} bytes, id: {file_id})")
            else:
                # Log why file was rejected
                logger.debug(f"✗ Skipped non-video file: {name}")
    
        # Sort videos by size (largest first) to ensure main episodes are prioritized
        valid_videos.sort(key=lambda x: x.get("bytes", 0), reverse=True)
        
        # Add all valid video files
        for video in valid_videos:
            path = video.get("path", "")
            file_id = str(video.get("id", ""))
            size = video.get("bytes", 0)
            
            # Extract parent folder name from path
            path_parts = path.split("/")
            parent_path = path_parts[-2] if len(path_parts) > 1 else ""
            
            result[file_id] = {
                "filename": path,
                "filesize": size,
                "parent_path": parent_path
            }
            logger.debug(f"✓ Selected file for download: {path} (size: {size} bytes, id: {file_id})")
    
        if not result:
            # Log all files for debugging
            logger.debug("No valid video files found. Available files:")
            for file in files:
                logger.debug(f"- {file.get('path', '')} ({file.get('bytes', 0)} bytes)")
        else:
            logger.debug(f"Selected {len(result)} video files for download")
    
        return result

    def _can_start_download(self, content_id: str) -> bool:
        """Check if we can start a new download for this content."""
        # Get total active downloads across all content
        total_downloads = sum(len(downloads) for downloads in self.active_downloads.values())
        current_content_downloads = len(self.active_downloads.get(content_id, set()))
        
        logger.debug(f"Download count check - Total: {total_downloads}/{self.MAX_CONCURRENT_TOTAL}, "
                    f"Content {content_id}: {current_content_downloads}/{self.MAX_CONCURRENT_PER_CONTENT}")
        
        # Check both total and per-content limits
        if total_downloads >= self.MAX_CONCURRENT_TOTAL:
            if not self._cleanup_if_needed():
                return False
            # Recalculate after cleanup
            total_downloads = sum(len(downloads) for downloads in self.active_downloads.values())
            current_content_downloads = len(self.active_downloads.get(content_id, set()))
            
        if current_content_downloads >= self.MAX_CONCURRENT_PER_CONTENT:
            logger.warning(f"Too many concurrent downloads for content {content_id} "
                         f"({current_content_downloads}/{self.MAX_CONCURRENT_PER_CONTENT})")
            return False
            
        return True

    def _cleanup_if_needed(self) -> bool:
        """Check active count and cleanup if needed.
        Returns True if cleanup was successful in reducing count below limit."""
        total_downloads = sum(len(downloads) for downloads in self.active_downloads.values())
        if total_downloads >= self.MAX_CONCURRENT_TOTAL:
            logger.debug(f"At max concurrent downloads ({total_downloads}/{self.MAX_CONCURRENT_TOTAL}), attempting cleanup...")
            
            # First try to clean up any completed downloads that might still be tracked
            try:
                downloads = self.api.request_handler.execute(HttpMethod.GET, "downloads")
                if isinstance(downloads, list):
                    for download in downloads:
                        if isinstance(download, dict):
                            download_id = download.get("id")
                            status = download.get("status")
                            if status == "downloaded":
                                # Find and remove from any content's active downloads
                                for content_id, active_set in self.active_downloads.items():
                                    if download_id in active_set:
                                        active_set.remove(download_id)
                                        logger.debug(f"Removed completed download {download_id} from content {content_id} tracking")
                                        self.download_complete[content_id] = True
            except Exception as e:
                logger.warning(f"Failed to check for completed downloads: {e}")
            
            # Recalculate after removing completed downloads
            total_downloads = sum(len(downloads) for downloads in self.active_downloads.values())
            if total_downloads < self.MAX_CONCURRENT_TOTAL:
                logger.debug(f"Cleanup of completed downloads successful, now at {total_downloads}/{self.MAX_CONCURRENT_TOTAL}")
                return True
            
            # If still at limit, try regular cleanup
            for attempt in range(2):
                cleaned = self._cleanup_downloads()
                if cleaned:
                    # Recalculate total after cleanup
                    total_downloads = sum(len(downloads) for downloads in self.active_downloads.values())
                    if total_downloads < self.MAX_CONCURRENT_TOTAL:
                        logger.debug(f"Cleanup successful, now at {total_downloads}/{self.MAX_CONCURRENT_TOTAL} downloads")
                        return True
                    else:
                        logger.debug(f"Cleanup removed {cleaned} downloads but still at limit ({total_downloads}/{self.MAX_CONCURRENT_TOTAL})")
                else:
                    logger.debug(f"Cleanup attempt {attempt + 1} removed no downloads")
                if attempt == 0:  # Wait between attempts
                    time.sleep(2)
            
            # Do one final check of our tracking vs reality
            try:
                downloads = self.api.request_handler.execute(HttpMethod.GET, "downloads")
                if isinstance(downloads, list):
                    actual_active = set()
                    for download in downloads:
                        if isinstance(download, dict):
                            download_id = download.get("id")
                            status = download.get("status")
                            if status not in ("downloaded", "error", "magnet_error", "virus", "dead"):
                                actual_active.add(download_id)
                    
                    # Update our tracking to match reality
                    for content_id in list(self.active_downloads.keys()):
                        self.active_downloads[content_id] = {
                            d_id for d_id in self.active_downloads[content_id] 
                            if d_id in actual_active
                        }
                        if not self.active_downloads[content_id]:
                            del self.active_downloads[content_id]
                    
                    total_downloads = sum(len(downloads) for downloads in self.active_downloads.values())
                    logger.debug(f"After final tracking sync: {total_downloads}/{self.MAX_CONCURRENT_TOTAL} downloads")
                    return total_downloads < self.MAX_CONCURRENT_TOTAL
            except Exception as e:
                logger.warning(f"Failed final tracking check: {e}")
            
            logger.warning(f"Could not reduce download count below limit ({total_downloads}/{self.MAX_CONCURRENT_TOTAL}) after cleanup")
            return False
        return True

    def download_cached_stream(self, item: MediaItem, stream: Stream) -> DownloadCachedStreamResult:
        """Download a stream from Real-Debrid"""
        if not self.initialized:
            raise RealDebridError("Downloader not properly initialized")

        content_id = str(item.id)
        torrent_id = None

        try:
            # Check and cleanup if needed before adding magnet
            if not self._cleanup_if_needed():
                logger.warning(f"Cannot start download for {content_id} - max concurrent downloads reached even after cleanup")
                return DownloadCachedStreamResult(None, torrent_id, None, stream.infohash)

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

    def _add_active_download(self, content_id: str, torrent_id: str):
        """Add a download to active downloads tracking."""
        self.active_downloads[content_id].add(torrent_id)
        logger.debug(f"Added download {torrent_id} to content {content_id} tracking")

    def _remove_active_download(self, content_id: str, torrent_id: str):
        """Remove a download from active downloads tracking."""
        if content_id in self.active_downloads:
            self.active_downloads[content_id].discard(torrent_id)
            logger.debug(f"Removed download {torrent_id} from content {content_id} tracking")
            if not self.active_downloads[content_id]:
                del self.active_downloads[content_id]
                logger.debug(f"Removed empty content {content_id} from tracking")

    def _mark_content_complete(self, content_id: str):
        """Mark a content as having completed download."""
        self.download_complete[content_id] = True
        logger.debug(f"Marked content {content_id} as complete")

    def _is_content_complete(self, content_id: str) -> bool:
        """Check if content has completed download."""
        is_complete = content_id in self.download_complete and self.download_complete[content_id]
        logger.debug(f"Content {content_id} complete status: {is_complete}")
        return is_complete

    def __init__(self):
        self.key = "realdebrid"
        self.settings = settings_manager.settings.downloaders.real_debrid
        self.scraping_settings = settings_manager.settings.scraping
        self.api = None
        self.file_finder = None
        self.initialized = self.validate()
        self.active_downloads = defaultdict(set)  # {content_id: set(torrent_ids)}
        self.download_complete = {}  # Track if a content's download is complete
        self.queue_attempts = {}  # Track number of queued attempts per content
        self.last_cleanup_time = datetime.now()
        
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
        Note: Returns all torrents as available to attempt download of everything
        """
        # Return all infohashes as available with a dummy file entry
        result = {}
        for infohash in infohashes:
            result[infohash] = [{
                "files": [{
                    "id": 1,
                    "path": "pending.mkv",
                    "bytes": 1000000000
                }]
            }]
        return result

    def add_torrent(self, infohash: str) -> str:
        """Add a torrent to Real-Debrid and return its ID."""
        # Check and cleanup if needed before adding torrent
        if not self._cleanup_if_needed():
            raise Exception("Cannot add torrent - max concurrent downloads reached even after cleanup")

        attempts = 3
        last_error = None

        for attempt in range(attempts):
            try:
                # First try to add directly
                try:
                    result = self.api.request_handler.execute(
                        HttpMethod.POST,
                        "torrents/addMagnet",
                        data={"magnet": f"magnet:?xt=urn:btih:{infohash}"}
                    )
                    return result["id"]
                except Exception as e:
                    error_str = str(e).lower()
                    if "404" in error_str:
                        # If 404, try adding raw hash
                        result = self.api.request_handler.execute(
                            HttpMethod.POST,
                            "torrents/addMagnet",
                            data={"magnet": infohash}
                        )
                        return result["id"]
                    elif "403" in error_str or "forbidden" in error_str:
                        # Force cleanup on 403/Forbidden
                        logger.debug(f"Got 403/Forbidden error, forcing cleanup (attempt {attempt + 1}/{attempts})")
                        self._cleanup_downloads()
                        time.sleep(2)  # Wait before retry
                    elif "509" in error_str or "active limit exceeded" in error_str.lower():
                        # Force cleanup on active limit
                        logger.debug(f"Active limit exceeded, forcing cleanup (attempt {attempt + 1}/{attempts})")
                        self._cleanup_downloads()
                        time.sleep(2)  # Wait before retry
                    elif "429" in error_str or "too many requests" in error_str.lower():
                        # Rate limit - wait longer
                        wait_time = 5 if attempt == 0 else 10
                        logger.debug(f"Rate limited, waiting {wait_time}s (attempt {attempt + 1}/{attempts})")
                        time.sleep(wait_time)
                    else:
                        raise

            except Exception as e:
                last_error = e
                if attempt < attempts - 1:  # Don't log on last attempt
                    logger.warning(f"Failed to add torrent {infohash} (attempt {attempt + 1}/{attempts}): {e}")
                    time.sleep(2)  # Wait before retry
                continue

        # If we get here, all attempts failed
        logger.error(f"Failed to add torrent {infohash} after {attempts} attempts: {last_error}")
        raise last_error

    def _is_active_status(self, status: str) -> bool:
        """Check if a torrent status counts as active."""
        return status in ("downloading", "uploading", "compressing", "magnet_conversion", "waiting_files_selection")

    def _cleanup_inactive_torrents(self) -> int:
        """Clean up inactive, errored, or stalled torrents to free up slots.
        Returns number of torrents cleaned up."""
        
        # Check if enough time has passed since last cleanup
        current_time = datetime.now()
        if (current_time - self.last_cleanup_time).total_seconds() < self.CLEANUP_INTERVAL:
            return 0
            
        try:
            # First check active torrent count
            try:
                active_count = self.api.request_handler.execute(HttpMethod.GET, "torrents/activeCount")
                logger.debug(f"Active torrents: {active_count['nb']}/{active_count['limit']}")
                if active_count["nb"] < active_count["limit"]:
                    return 0
                
                # Calculate how aggressive we should be based on how far over the limit we are
                overage = active_count["nb"] - active_count["limit"]
                logger.warning(f"Over active torrent limit by {overage} torrents")
                # If we're over by more than 5, be extremely aggressive
                extremely_aggressive = overage >= 5
                # If we're over by any amount, be somewhat aggressive
                aggressive_cleanup = overage > 0
            except Exception as e:
                logger.warning(f"Failed to get active torrent count: {e}")
                extremely_aggressive = True  # Be extremely aggressive if we can't check
                aggressive_cleanup = True
            
            # Get list of all torrents
            torrents = self.api.request_handler.execute(HttpMethod.GET, "torrents")
            to_delete = []  # List of (priority, torrent_id, reason) tuples
            cleaned = 0
            
            # Count active torrents by status and collect stats
            active_by_status = defaultdict(list)
            magnet_times = []  # Track magnet conversion times
            downloading_stats = []  # Track download stats
            total_active = 0
            
            # Track duplicates by filename
            filename_to_torrents = defaultdict(list)
            
            for torrent in torrents:
                status = torrent.get("status", "")
                if self._is_active_status(status):
                    # Calculate time_elapsed first
                    time_elapsed = 0
                    try:
                        added = torrent.get("added", "")
                        if added:
                            # Convert to UTC, then to local time
                            added_time = datetime.fromisoformat(added.replace("Z", "+00:00"))
                            added_time = added_time.astimezone().replace(tzinfo=None)
                            time_elapsed = (current_time - added_time).total_seconds()
                    except (ValueError, TypeError):
                        logger.warning(f"Invalid timestamp format for torrent: {torrent.get('added')}")
                    
                    torrent_stats = {
                        "status": status,
                        "filename": torrent.get("filename", "unknown"),
                        "progress": torrent.get("progress", 0),
                        "speed": torrent.get("speed", 0),
                        "seeders": torrent.get("seeders", 0),
                        "time_elapsed": time_elapsed,
                        "id": torrent.get("id", "")
                    }
                    
                    active_by_status[status].append(torrent_stats)
                    filename_to_torrents[torrent_stats["filename"]].append(torrent_stats)
                    total_active += 1
                    
                    if status == "magnet_conversion" and time_elapsed > 0:
                        magnet_times.append(time_elapsed)
                    elif status == "downloading":
                        downloading_stats.append(torrent_stats)
            
            # First handle duplicates - keep only the most progressed version of each file
            for filename, dupes in filename_to_torrents.items():
                if len(dupes) > 1:
                    logger.info(f"Found {len(dupes)} duplicates of {filename}")
                    # Sort by progress (highest first), then by speed (highest first)
                    dupes.sort(key=lambda x: (x["progress"], x["speed"]), reverse=True)
                    
                    # Keep the best one, mark others for deletion
                    best = dupes[0]
                    logger.info(f"Keeping best duplicate: {best['progress']}% @ {best['speed']/1024:.1f} KB/s")
                    
                    for dupe in dupes[1:]:
                        reason = (f"duplicate of {filename} "
                                f"(keeping: {best['progress']}% @ {best['speed']/1024:.1f} KB/s, "
                                f"removing: {dupe['progress']}% @ {dupe['speed']/1024:.1f} KB/s)")
                        to_delete.append((150, dupe["id"], reason, dupe["time_elapsed"]))  # Highest priority for duplicates
                        logger.info(f"Marking duplicate for deletion: {reason}")
            
            # Find stalled or problematic torrents
            stalled_threshold = 60  # 1 minute without progress
            near_complete_threshold = 95.0  # Protect torrents above this %
            min_speed_threshold = 100 * 1024  # 100 KB/s minimum speed
            
            for status, torrents in active_by_status.items():
                for t in torrents:
                    # Skip nearly complete downloads unless they're completely stalled
                    if t["progress"] >= near_complete_threshold:
                        if t["speed"] == 0:
                            logger.warning(f"Nearly complete torrent stalled: {t['filename']} at {t['progress']}%")
                            reason = f"stalled at {t['progress']}% complete (no speed for {t['time_elapsed']/60:.1f}m)"
                            to_delete.append((90, t["id"], reason, t["time_elapsed"]))
                        continue
                    
                    # Check for stalled downloads
                    if status == "downloading":
                        if t["speed"] < min_speed_threshold:
                            time_stalled = t["time_elapsed"]
                            if time_stalled > stalled_threshold:
                                reason = (f"stalled download: {t['filename']} "
                                        f"(progress: {t['progress']}%, "
                                        f"speed: {t['speed']/1024:.1f} KB/s, "
                                        f"stalled for: {time_stalled/60:.1f}m)")
                                priority = 120 if t["progress"] < 10 else 100  # Higher priority for early stalls
                                to_delete.append((priority, t["id"], reason, time_stalled))
                                logger.info(f"Marking stalled download for deletion: {reason}")
                    
                    # Handle stuck magnet conversions more aggressively
                    elif status == "magnet_conversion":
                        if t["time_elapsed"] > 300:  # 5 minutes
                            reason = f"stuck in magnet conversion for {t['time_elapsed']/60:.1f} minutes"
                            to_delete.append((130, t["id"], reason, t["time_elapsed"]))
                            logger.info(f"Marking stuck magnet for deletion: {reason}")
            
            # Log active torrent distribution and detailed stats
            logger.info("=== Active Torrent Stats ===")
            for status, active_torrents in active_by_status.items():
                count = len(active_torrents)
                logger.info(f"\n{status.upper()} ({count} torrents):")
                
                # Sort by time elapsed
                active_torrents.sort(key=lambda x: x["time_elapsed"], reverse=True)
                
                for t in active_torrents:
                    stats = []
                    if t["progress"] > 0:
                        stats.append(f"progress: {t['progress']}%")
                    if t["speed"] > 0:
                        stats.append(f"speed: {t['speed']/1024:.1f} KB/s")
                    if t["seeders"] > 0:
                        stats.append(f"seeders: {t['seeders']}")
                    if t["time_elapsed"] > 0:
                        stats.append(f"age: {t['time_elapsed']/60:.1f}m")
                    
                    stats_str = ", ".join(stats) if stats else f"age: {t['time_elapsed']/60:.1f}m"
                    logger.info(f"  - {t['filename']} ({stats_str})")
            
            # Calculate duplicate ratio and adjust aggressiveness
            unique_filenames = set()
            for status, torrents in active_by_status.items():
                for t in torrents:
                    unique_filenames.add(t["filename"])
            
            duplicate_ratio = (total_active - len(unique_filenames)) / total_active if total_active > 0 else 0
            if duplicate_ratio > 0.5:  # If more than 50% are duplicates
                extremely_aggressive = True
                logger.info(f"High duplicate ratio ({duplicate_ratio:.1%}), using extremely aggressive cleanup")
            
            # Set base thresholds
            if extremely_aggressive:
                magnet_threshold = 30  # 30 seconds
                time_threshold = self.CLEANUP_INACTIVE_TIME / 4
            elif aggressive_cleanup:
                magnet_threshold = 60  # 1 minute
                time_threshold = self.CLEANUP_INACTIVE_TIME / 2
            else:
                magnet_threshold = 300  # 5 minutes
                time_threshold = self.CLEANUP_INACTIVE_TIME
            
            logger.debug(f"Using thresholds - Magnet: {magnet_threshold/60:.1f}m, General: {time_threshold/60:.1f}m")
            
            # Process all torrents for cleanup
            for status, torrents in active_by_status.items():
                for torrent_stats in torrents:
                    should_delete = False
                    reason = ""
                    priority = 0
                    time_elapsed = torrent_stats["time_elapsed"]
                    
                    # 1. Error states (highest priority)
                    if status in ("error", "magnet_error", "virus", "dead"):
                        should_delete = True
                        reason = f"error status: {status}"
                        priority = 100
                    
                    # 2. Magnet conversion (high priority if taking too long)
                    elif status == "magnet_conversion":
                        if time_elapsed > magnet_threshold:
                            should_delete = True
                            reason = f"stuck in magnet conversion for {time_elapsed/60:.1f} minutes"
                            priority = 95  # Very high priority since we have so many
                    
                    # 3. Stalled or slow downloads
                    elif status == "downloading":
                        progress = torrent_stats["progress"]
                        speed = torrent_stats["speed"]
                        seeders = torrent_stats["seeders"]
                        
                        if progress == 0 and time_elapsed > time_threshold:
                            should_delete = True
                            reason = f"no progress after {time_elapsed/60:.1f} minutes"
                            priority = 85
                        elif progress < self.CLEANUP_MINIMAL_PROGRESS_THRESHOLD and time_elapsed > time_threshold:
                            should_delete = True
                            reason = f"minimal progress ({progress}%) after {time_elapsed/60:.1f} minutes"
                            priority = 80
                        elif speed < self.CLEANUP_SPEED_THRESHOLD:
                            should_delete = True
                            reason = f"slow speed ({speed/1024:.1f} KB/s)"
                            priority = 75
                        elif seeders == 0:
                            should_delete = True
                            reason = f"no seeders"
                            priority = 85
                    
                    # 4. Stuck uploads/compression
                    elif status in ("uploading", "compressing"):
                        speed = torrent_stats["speed"]
                        if time_elapsed > time_threshold or speed < self.CLEANUP_SPEED_THRESHOLD:
                            should_delete = True
                            reason = f"stuck in {status} for {time_elapsed/60:.1f} minutes"
                            priority = 60
                    
                    # 5. Other states
                    elif status in ("waiting_files_selection", "queued"):
                        if time_elapsed > time_threshold:
                            should_delete = True
                            reason = f"stuck in {status} for {time_elapsed/60:.1f} minutes"
                            priority = 50
                    
                    if should_delete:
                        filename = torrent_stats["filename"]
                        progress = torrent_stats["progress"]
                        speed = torrent_stats["speed"]
                        full_reason = f"{reason} (file: {filename}, progress: {progress}%, speed: {speed/1024:.1f} KB/s)"
                        to_delete.append((priority, torrent_stats["id"], full_reason, time_elapsed))
            
            # Sort by priority (highest first) and extract torrent_id and reason
            to_delete.sort(reverse=True)
            
            # If we're extremely aggressive, take more torrents
            batch_size = self.CLEANUP_BATCH_SIZE * 2 if extremely_aggressive else self.CLEANUP_BATCH_SIZE
            
            # If no torrents were marked for deletion but we're still over limit,
            # force delete the slowest/least progressed torrents
            if not to_delete and total_active > active_count["limit"]:
                logger.info("No torrents met deletion criteria but still over limit, using fallback cleanup")
                
                # First try to clean up just duplicates
                duplicates_only = True
                cleanup_attempts = 2  # Try duplicates first, then all torrents if needed
                
                while cleanup_attempts > 0:
                    # Collect all active torrents into a single list for sorting
                    all_active = []
                    seen_filenames = set()
                    
                    for status, torrents in active_by_status.items():
                        for t in torrents:
                            filename = t["filename"]
                            
                            # Skip non-duplicates on first pass
                            is_duplicate = filename in seen_filenames
                            if duplicates_only and not is_duplicate:
                                continue
                            
                            seen_filenames.add(filename)
                            
                            score = 0
                            # Prioritize keeping torrents with more progress
                            score += t["progress"] * 100
                            # And those with higher speeds
                            score += min(t["speed"] / 1024, 1000)  # Cap speed bonus at 1000
                            # And those with more seeders
                            score += t["seeders"] * 10
                            # Penalize older torrents slightly
                            score -= min(t["time_elapsed"] / 60, 60)  # Cap age penalty at 60 minutes
                            # Heavy penalty for duplicates
                            if is_duplicate:
                                score -= 5000  # Ensure duplicates are cleaned up first
                            
                            all_active.append({
                                "id": t["id"],
                                "score": score,
                                "stats": t,
                                "status": status,
                                "is_duplicate": is_duplicate
                            })
                    
                    if all_active:
                        # Sort by score (lowest first - these will be deleted)
                        all_active.sort(key=lambda x: x["score"])
                        
                        # Take enough torrents to get under the limit
                        to_remove = min(
                            len(all_active),  # Don't try to remove more than we have
                            total_active - active_count["limit"] + 1  # +1 for safety margin
                        )
                        
                        for torrent in all_active[:to_remove]:
                            stats = torrent["stats"]
                            reason = (f"fallback cleanup{' (duplicate)' if duplicates_only else ''} - {torrent['status']} "
                                    f"(progress: {stats['progress']}%, "
                                    f"speed: {stats['speed']/1024:.1f} KB/s, "
                                    f"seeders: {stats['seeders']}, "
                                    f"age: {stats['time_elapsed']/60:.1f}m)")
                            to_delete.append((0, torrent["id"], reason, stats["time_elapsed"]))
                            logger.info(f"Fallback cleanup marking: {stats['filename']} - {reason}")
                        
                        # If we found enough torrents to delete, we're done
                        if len(to_delete) >= (total_active - active_count["limit"]):
                            break
                    
                    # If we get here and duplicates_only is True, try again with all torrents
                    duplicates_only = False
                    cleanup_attempts -= 1
                
                # Log what we're about to delete
                if to_delete:
                    logger.info(f"Found {len(to_delete)} torrents to clean up, processing in batches of {batch_size}")
                    for _, _, reason, _ in to_delete[:5]:  # Log first 5 for debugging
                        logger.debug(f"Will delete: {reason}")
            
            # Convert to final format and process deletions
            to_delete = [(t[1], t[2]) for t in to_delete]
            
            # Process deletion in batches
            while to_delete:
                batch = to_delete[:batch_size]
                to_delete = to_delete[batch_size:]
                
                for torrent_id, reason in batch:
                    try:
                        self.api.request_handler.execute(HttpMethod.DELETE, f"torrents/delete/{torrent_id}")
                        cleaned += 1
                        logger.info(f"Cleaned up torrent: {reason}")
                    except Exception as e:
                        logger.error(f"Failed to delete torrent {torrent_id}: {e}")
                
                if to_delete:  # If we have more to process, wait briefly
                    time.sleep(0.5)
            
            self.last_cleanup_time = current_time
            return cleaned
            
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")
            return 0