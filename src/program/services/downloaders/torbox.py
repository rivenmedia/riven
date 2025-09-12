from datetime import datetime
from typing import List, Optional

from loguru import logger

from program.services.downloaders.models import (
    DebridFile,
    InvalidDebridFileException,
    TorrentContainer,
    TorrentInfo,
)
from program.settings.manager import settings_manager
from program.utils import get_version
from program.utils.request import CircuitBreakerOpen, SmartSession

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
        try:
            user_info = self.api.session.get("user/me")
            if not user_info.data.get("plan", 0) > 0:
                logger.error("Premium membership required")
                return False

            expiration = datetime.strptime(user_info.data["premium_expires_at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=None)
            logger.info(premium_days_left(expiration))
            return True
        except Exception as e:
            logger.error(f"Failed to validate premium status: {e}")
            return False
        
    def select_files(self, torrent_id: str, _: List[str] = None) -> None:
        pass

    def get_instant_availability(self, infohash: str, item_type: str) -> Optional[TorrentContainer]:
        """
        Get instant availability for a single infohash.
        """
        try:
            response = self.api.session.get(
                f"torrents/checkcached?hash={infohash}&format=object&list_files=true",
            )
            if not response.data:
                logger.debug(f"Torrent {infohash} is not cached")
                return None
            
            response_data = response.data.get(infohash, {})
            if not response_data:
                logger.debug(f"Torrent {infohash} is not cached")
                return None
            

            torrent_files = []
            
            files = response_data.get("files", [])
            for file_id, file in enumerate(files):
                try:
                    debrid_file = DebridFile.create(
                        path=file["name"],
                        filename=file["name"].split("/")[-1],
                        filesize_bytes=file["size"],
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
        """Add a torrent by infohash"""
        try:
            magnet = f"magnet:?xt=urn:btih:{infohash}"
            response = self.api.session.post(
                "torrents/createtorrent",
                data={"magnet": magnet.lower()}
            )
            return str(response.data["torrent_id"]) # must be a string
        except CircuitBreakerOpen as e:
            logger.warning(f"Circuit breaker OPEN for TorBox API, cannot add torrent {infohash}: {e}")
            raise  # Re-raise to be handled by the calling service
        except Exception as e:
            if len(e.args) > 0:
                if " 503 " in e.args[0]:
                    logger.debug(f"Failed to add torrent {infohash}: [503] Infringing Torrent or Service Unavailable")
                    raise TorBoxError("Infringing Torrent or Service Unavailable")
                if " 429 " in e.args[0]:
                    logger.debug(f"Failed to add torrent {infohash}: [429] Rate Limit Exceeded")
                    raise TorBoxError("Rate Limit Exceeded")
                if " 404 " in e.args[0]:
                    logger.debug(f"Failed to add torrent {infohash}: [404] Torrent Not Found or Service Unavailable")
                    raise TorBoxError("Torrent Not Found or Service Unavailable")
                if " 400 " in e.args[0]:
                    logger.debug(f"Failed to add torrent {infohash}: [400] Torrent file is not valid. Magnet: {magnet}")
                    raise TorBoxError("Torrent file is not valid")
            else:
                logger.debug(f"Failed to add torrent {infohash}: {e}")
            
            raise TorBoxError(f"Failed to add torrent {infohash}: {e}")

    def get_torrent_info(self, torrent_id: str) -> TorrentInfo:
        """Get information about a torrent"""
        try:
            data = self.api.session.get(f"torrents/mylist?id={torrent_id}")
            files = {
                file["id"]: {
                    "path": file["name"], # we're gonna need this to weed out the junk files
                    "filename": file["short_name"],
                    "bytes": file["size"],
                    "selected": True
                } for file in data.data["files"]
            }
            return TorrentInfo(
                id=data.data["id"],
                name=data.data["name"],
                status=data.data["download_state"],
                cached=data.data["cached"],
                infohash=data.data["hash"],
                bytes=data.data["size"],
                created_at=data.data["created_at"],
                alternative_filename=None,
                progress=data.data.get("progress", None),
                files=files,
            )
        except CircuitBreakerOpen as e:
            logger.warning(f"Circuit breaker OPEN for TorBox API, cannot get torrent info for {torrent_id}: {e}")
            raise  # Re-raise to be handled by the calling service
        except Exception as e:
            logger.error(f"Failed to get torrent info for {torrent_id}: {e}")
            raise

    def delete_torrent(self, torrent_id: str) -> None:
        """Delete a torrent"""
        try:
            self.api.session.post("torrents/controltorrent", data={
                "id": torrent_id,
                "operation": "delete",
            })
        except CircuitBreakerOpen as e:
            logger.warning(f"Circuit breaker OPEN for TorBox API, cannot delete torrent {torrent_id}: {e}")
            raise  # Re-raise to be handled by the calling service
        except Exception as e:
            logger.error(f"Failed to delete torrent {torrent_id}: {e}")
            raise
