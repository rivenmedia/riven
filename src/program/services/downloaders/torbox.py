from datetime import datetime
from typing import Dict, List, Optional

from loguru import logger

from program.services.downloaders.models import (
    DebridFile,
    InvalidDebridFileException,
    TorrentContainer,
    TorrentInfo,
    UserInfo,
)
from program.settings.manager import settings_manager
from program.utils import get_version
from program.utils.request import CircuitBreakerOpen, SmartResponse, SmartSession

from .shared import DownloaderBase, premium_days_left


class TorBoxError(Exception):
    """Base exception for TorBox related errors"""

class TorBoxAPI:
    """Handles TorBox API communication"""
    BASE_URL = "https://api.torbox.app/v1/api"

    def __init__(self, api_key: str, proxy_url: Optional[str] = None):
        self.api_key = api_key
        
        # Configure rate limiting for TorBox (60 calls per minute)
        rate_limits = {
            "api.torbox.app": {"rate": 1, "capacity": 60}  # 60 calls per minute
        }
        
        self.session = SmartSession(
            base_url=self.BASE_URL,
            rate_limits=rate_limits,
            retries=3,
            backoff_factor=0.3
        )
        self.session.headers.update({"Authorization": f"Bearer {api_key}"})
        try:
            version = get_version()
        except Exception:
            version = "Unknown"
        self.session.headers.update({"User-Agent": f"Riven/{version} TorBox/1.0"})
        if proxy_url:
            self.session.proxies = {"http": proxy_url, "https": proxy_url}

class TorBoxDownloader(DownloaderBase):
    """Main TorBox downloader class implementing DownloaderBase"""

    def __init__(self):
        self.key = "torbox"
        self.settings = settings_manager.settings.downloaders.torbox
        self.api = None
        self.initialized = self.validate()

    def validate(self) -> bool:
        """
        Validate TorBox settings and premium status
        Required by DownloaderBase
        """
        if not self._validate_settings():
            return False

        self.api = TorBoxAPI(
            api_key=self.settings.api_key,
            proxy_url=self.PROXY_URL if self.PROXY_URL else None
        )

        return self._validate_premium()

    def _validate_settings(self) -> bool:
        """Validate configuration settings"""
        if not self.settings.enabled:
            return False
        if not self.settings.api_key:
            logger.warning("TorBox API key is not set")
            return False
        return True

    def _validate_premium(self) -> bool:
        """Validate premium status"""
        user_info = self.get_user_info()
        if not user_info.premium_status:
            logger.error("Premium membership required")
            return False
        
        logger.info(premium_days_left(user_info.premium_expires_at))
        return True
        
    def select_files(self, torrent_id: str, _: List[str] = None) -> None:
        pass

    def get_instant_availability(self, infohash: str, item_type: str) -> Optional[TorrentContainer]:
        """
        Get instant availability for a single infohash.
        """
        try:
            resp: SmartResponse = self.api.session.get(
                f"torrents/checkcached?hash={infohash}&format=object&list_files=true",
            )
            if not resp.ok:
                logger.debug(f"Failed to check cache for {infohash}: {self._handle_error(resp)}")
                return None

            data = resp.data.data

            if not data:
                logger.debug(f"Torrent {infohash} is not cached")
                return None

            # Access the infohash key from the response data
            response_data = getattr(data, infohash, None)
            if not response_data:
                logger.debug(f"Torrent {infohash} is not cached")
                return None


            torrent_files = []

            files = getattr(response_data, "files", [])
            for file_id, file in enumerate(files):
                try:
                    debrid_file = DebridFile.create(
                        path=file.name,
                        filename=file.name.split("/")[-1],
                        filesize_bytes=file.size,
                        filetype=item_type,
                        file_id=file_id
                    )
                    if isinstance(debrid_file, DebridFile):
                        torrent_files.append(debrid_file)
                except InvalidDebridFileException as e:
                    logger.debug(f"{infohash}: {e}")
                    continue

            if not torrent_files:
                logger.debug(f"No valid files found in cached torrent {infohash}")
                return None

            return TorrentContainer(infohash=infohash, files=torrent_files)
        except CircuitBreakerOpen as e:
            logger.warning(f"Circuit breaker OPEN for TorBox API, skipping {infohash}: {e}")
            raise  # Re-raise to be handled by the calling service
        except Exception as e:
            logger.error(f"Failed to get instant availability for {infohash}: {e}")
            return None

    def _process_torrent(self, torrent_id: str, infohash: str, item_type: str) -> Optional[TorrentContainer]:
        """Process a single torrent and return a TorrentContainer if valid."""
        torrent_info = self.get_torrent_info(torrent_id)
        if not torrent_info:
            logger.debug(f"No torrent info found for {torrent_id} with infohash {infohash}")
            return None

        torrent_files = []

        if not torrent_info.files:
            logger.debug(f"No files found in torrent {torrent_id} with infohash {infohash}")
            return None

        if torrent_info.status:
            for file_id, file_info in torrent_info.files.items():
                try:
                    debrid_file = DebridFile.create(
                        path=file_info["path"],
                        filename=file_info["filename"],
                        filesize_bytes=file_info["bytes"],
                        filetype=item_type,
                        file_id=file_id
                    )

                    if isinstance(debrid_file, DebridFile):
                        torrent_files.append(debrid_file)
                except InvalidDebridFileException as e:
                    logger.debug(f"{infohash}: {e}")
                    continue

            if not torrent_files:
                logger.debug(f"No valid files found after validating files in torrent {torrent_id} with infohash {infohash}")
                return None

            return TorrentContainer(infohash=infohash, files=torrent_files)

        if torrent_info.status in ("downloading", "queued"):
            # TODO: add support for downloading torrents
            logger.debug(f"Skipping torrent {torrent_id} with infohash {infohash} because it is downloading. Torrent status on TorBox: {torrent_info.status}")
            return None

        logger.debug(f"Torrent {torrent_id} with infohash {infohash} is invalid. Torrent status on Real-Debrid: {torrent_info.status}")
        return None

    def add_torrent(self, infohash: str) -> str:
        """
        Add a torrent by infohash.

        Returns:
            TorBox torrent id.

        Raises:
            CircuitBreakerOpen: If the per-domain breaker is OPEN.
            TorBoxError: If the API returns a failing status.
        """
        magnet = f"magnet:?xt=urn:btih:{infohash}"
        resp: SmartResponse = self.api.session.post(
            "torrents/createtorrent",
            data={"magnet": magnet.lower()}
        )
        self._maybe_backoff(resp)
        if not resp.ok:
            raise TorBoxError(self._handle_error(resp))
        
        data = resp.data.data

        tid = getattr(data, "torrent_id", None)
        if not tid:
            raise TorBoxError("No torrent ID returned by TorBox.")
        return str(tid)  # must be a string

    def get_torrent_info(self, torrent_id: str) -> Optional[TorrentInfo]:
        """
        Retrieve torrent information and normalize into TorrentInfo.
        Returns None on API-level failure (non-OK) to match current behavior.
        """
        if not torrent_id:
            logger.debug("No torrent ID provided")
            return None

        try:
            resp: SmartResponse = self.api.session.get(f"torrents/mylist?id={torrent_id}")
            self._maybe_backoff(resp)
            if not resp.ok:
                logger.debug(f"Failed to get torrent info for {torrent_id}: {self._handle_error(resp)}")
                return None

            data = resp.data.data
            if getattr(data, "error", None):
                logger.debug(
                    f"Failed to get torrent info for {torrent_id}: '{data.error}' "
                    f"code={getattr(data, 'error_code', 'N/A')}"
                )
                return None

            files = {
                file.id: {
                    "path": file.name,  # we're gonna need this to weed out the junk files
                    "filename": file.short_name,
                    "bytes": file.size,
                    "selected": True,
                    "download_url": ""  # Will be populated by correlation, empty string instead of None
                } for file in data.files
            }
            return TorrentInfo(
                id=data.id,
                name=data.name,
                status=data.download_state,
                cached=data.cached,
                infohash=data.hash,
                bytes=data.size,
                created_at=data.created_at,
                alternative_filename=None,
                progress=getattr(data, "progress", None),
                files=files,
            )
        except CircuitBreakerOpen as e:
            logger.warning(f"Circuit breaker OPEN for TorBox API, cannot get torrent info for {torrent_id}: {e}")
            raise  # Re-raise to be handled by the calling service
        except Exception as e:
            logger.error(f"Failed to get torrent info for {torrent_id}: {e}")
            return None

    def get_download_url(self, torrent_id: str, file_id: str) -> Optional[str]:
        """Get download URL for a specific file"""
        try:
            resp: SmartResponse = self.api.session.get(
                f"torrents/requestdl?token={self.api.api_key}&torrent_id={torrent_id}&file_id={file_id}&zip_link=false"
            )
            if not resp.ok:
                logger.debug(f"Failed to get download URL for torrent {torrent_id}, file {file_id}: {self._handle_error(resp)}")
                return None
            return getattr(resp.data, "data", None)
        except CircuitBreakerOpen as e:
            logger.warning(f"Circuit breaker OPEN for TorBox API, cannot get download URL for {torrent_id}/{file_id}: {e}")
            return None
        except Exception as e:
            logger.error(f"Failed to get download URL for torrent {torrent_id}, file {file_id}: {e}")
            return None

    def delete_torrent(self, torrent_id: str) -> None:
        """
        Delete a torrent on TorBox.

        Raises:
            CircuitBreakerOpen: If the per-domain breaker is OPEN.
            TorBoxError: If the API returns a failing status.
        """
        resp: SmartResponse = self.api.session.post("torrents/controltorrent", data={
            "id": torrent_id,
            "operation": "delete",
        })
        self._maybe_backoff(resp)
        if not resp.ok:
            raise TorBoxError(self._handle_error(resp))

    def _maybe_backoff(self, resp: SmartResponse) -> None:
        """
        Promote TorBox 429/5xx responses to a service-level backoff signal.
        """
        code = resp.status_code
        if code == 429 or (500 <= code < 600):
            # Name matches the breaker key in SmartSession rate_limits/breakers
            raise CircuitBreakerOpen("api.torbox.app")

    def _handle_error(self, response: SmartResponse) -> str:
        """
        Map HTTP status codes to normalized error messages for logs/exceptions.
        """
        code = response.status_code
        if code == 451:
            return "[451] Infringing Torrent"
        if code == 503:
            return "[503] Service Unavailable"
        if code == 429:
            return "[429] Rate Limit Exceeded"
        if code == 404:
            return "[404] Torrent Not Found or Service Unavailable"
        if code == 400:
            return "[400] Torrent file is not valid"
        if code == 502:
            return "[502] Bad Gateway"
        return response.reason or f"HTTP {code}"

    def resolve_link(self, link: str) -> Optional[Dict]:
        return {
            'download_url': link,
            'name': 'file',
            'size': 0,
        }

    def get_user_info(self) -> Optional[UserInfo]:
        """
        Get normalized user information from TorBox.

        Returns:
            UserInfo: Normalized user information including premium status and expiration
        """
        try:
            resp: SmartResponse = self.api.session.get("user/me")
            if not resp.ok:
                logger.error(f"Failed to get user info: {self._handle_error(resp)}")
                return None

            data = resp.data.data

            # Parse expiration datetime
            expiration = None
            premium_days = None
            if hasattr(data, 'premium_expires_at') and data.premium_expires_at:
                try:
                    expiration = datetime.strptime(data.premium_expires_at, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=None)
                    time_left = expiration - datetime.utcnow()
                    premium_days = time_left.days
                except Exception as e:
                    logger.debug(f"Failed to parse expiration date: {e}")

            # Parse cooldown datetime
            cooldown = None
            if hasattr(data, 'cooldown_until') and data.cooldown_until:
                try:
                    cooldown = datetime.strptime(data.cooldown_until, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=None)
                except Exception as e:
                    logger.debug(f"Failed to parse cooldown date: {e}")

            return UserInfo(
                service="torbox",
                username=None,  # TorBox doesn't provide username
                email=getattr(data, 'email', None),
                user_id=data.id,
                premium_status="premium" if getattr(data, 'plan', 0) > 0 else "free",
                premium_expires_at=expiration.replace(tzinfo=None),
                premium_days_left=premium_days,
                total_downloaded_bytes=getattr(data, 'total_bytes_downloaded', None),
                cooldown_until=cooldown,
            )
        except CircuitBreakerOpen as e:
            logger.warning(f"Circuit breaker OPEN while getting user info: {e}")
            return None
        except Exception as e:
            logger.error(f"Failed to get user info: {e}")
            return None
