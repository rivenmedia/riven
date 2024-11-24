import time
from datetime import datetime
from typing import List, Optional, Union
from loguru import logger
from requests import Session

from program.settings.manager import settings_manager
from program.utils.request import (
    BaseRequestHandler,
    HttpMethod,
    ResponseType,
    create_service_session,
    get_rate_limit_params,
)
from program.services.downloaders.models import TorrentContainer, DebridFile, TorrentInfo

from .shared import DownloaderBase, premium_days_left


# class TBTorrentStatus(str, Enum):
#     """Torbox torrent status enumeration"""
#     MAGNET_ERROR = "magnet_error"
#     MAGNET_CONVERSION = "magnet_conversion"
#     WAITING_FILES = "waiting_files_selection"
#     DOWNLOADING = "downloading"
#     DOWNLOADED = "downloaded"
#     ERROR = "error"
#     SEEDING = "seeding"
#     DEAD = "dead"
#     UPLOADING = "uploading"
#     COMPRESSING = "compressing"


class TorBoxError(Exception):
    """Base exception for TorBox related errors"""

class TorBoxRequestHandler(BaseRequestHandler):
    def __init__(self, session: Session, base_url: str, request_logging: bool = False):
        super().__init__(session, response_type=ResponseType.DICT, base_url=base_url, custom_exception=TorBoxError, request_logging=request_logging)

    def execute(self, method: HttpMethod, endpoint: str, **kwargs) -> Union[dict, list]:
        response = super()._request(method, endpoint, **kwargs)
        if response.status_code == 204:
            return {}
        if not response.data and not response.is_ok:
            raise TorBoxError("Invalid JSON response from TorBox")
        return response.data

class TorBoxAPI:
    """Handles TorBox API communication"""
    BASE_URL = "https://api.torbox.app/v1/api"

    def __init__(self, api_key: str, proxy_url: Optional[str] = None):
        self.api_key = api_key
        rate_limit_params = get_rate_limit_params(per_second=5)
        self.session = create_service_session(rate_limit_params=rate_limit_params)
        self.session.headers.update({"Authorization": f"Bearer {api_key}"})
        if proxy_url:
            self.session.proxies = {"http": proxy_url, "https": proxy_url}
        self.request_handler = TorBoxRequestHandler(self.session, self.BASE_URL)

class TorBoxDownloader(DownloaderBase):
    """Main Torbox downloader class implementing DownloaderBase"""
    MAX_RETRIES = 3
    RETRY_DELAY = 1.0

    def __init__(self):
        self.key = "torbox"
        self.settings = settings_manager.settings.downloaders.torbox
        self.api = None
        self.initialized = self.validate()

    def validate(self) -> bool:
        """
        Validate Real-Torbox and premium status
        Required by DownloaderBase
        """
        if not self._validate_settings():
            return False

        self.api = TorBoxAPI(
            api_key=self.settings.api_key,
            proxy_url=self.settings.proxy_url if self.settings.proxy_enabled else None
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
            response = self.api.request_handler.execute(HttpMethod.GET, "user/me")
            user_info = response["data"]
            if not user_info.get("plan") or user_info["plan"] == 0:
                logger.error("Premium membership required")
                return False

            expiration = datetime.fromisoformat(
                user_info["premium_expires_at"]
            ).replace(tzinfo=None)
            logger.info(premium_days_left(expiration))
            return True
        except Exception as e:
            logger.error(f"Failed to validate premium status: {e}")
            return False

    def get_instant_availability(self, infohashes: List[str], item_type: str) -> List[TorrentContainer]:
        """Get instant availability for multiple infohashes with retry logic"""
        results = []
        for attempt in range(self.MAX_RETRIES):
            try:
                response = self.api.request_handler.execute(
                    HttpMethod.GET,
                    f"torrents/checkcached?hash={','.join(infohashes)}&format=list&list_files=true"
                )

                data: list = response["data"]
                if not data:
                    return results

                for torrent in data:
                    files = []
                    for file in torrent["files"]:
                        debrid_file = DebridFile.create(file["name"], file["size"], item_type)
                        if debrid_file:
                            files.append(debrid_file)
                    if files:
                        results.append(TorrentContainer(
                            infohash=torrent["hash"],
                            files=files
                        ))
                return results
            except Exception as e:
                logger.debug(f"Failed to get instant availability (attempt {attempt + 1}/{self.MAX_RETRIES}): {e}")
                if attempt < self.MAX_RETRIES - 1:
                    time.sleep(self.RETRY_DELAY)
                continue

        logger.debug("All retry attempts failed for instant availability")
        return []

    def add_torrent(self, infohash: str) -> str:
        """Add a torrent by infohash"""
        try:
            magnet = f"magnet:?xt=urn:btih:{infohash}"
            response = self.api.request_handler.execute(
                HttpMethod.POST,
                "torrents/createtorrent",
                data={"magnet": magnet.lower()}
            )
            return response["data"]["torrent_id"]
        except Exception as e:
            logger.error(f"Failed to add torrent {infohash}: {e}")
            raise

    def select_files(self, *args) -> None:
        """Select files from a torrent"""
        pass

    def get_torrent_info(self, torrent_id: str) -> TorrentInfo:
        """Get information about a torrent using a torrent ID"""
        try:
            data = self.api.request_handler.execute(HttpMethod.GET, f"torrents/mylist?id={torrent_id}")['data']
            return TorrentInfo(
                id=data["id"],
                name=data["name"],  # points to dir
                infohash=data["hash"],
                status=data["download_state"],
                bytes=data["size"]
            )
        except Exception as e:
            logger.error(f"Failed to get torrent info for {torrent_id}: {e}")
            raise

    def delete_torrent(self, torrent_id: str) -> None:
        """Delete a torrent"""
        try:
            self.api.request_handler.execute(HttpMethod.POST, f"torrents/controltorrent", data={"torrent_id": torrent_id, "operation": "delete"})
        except Exception as e:
            logger.error(f"Failed to delete torrent {torrent_id}: {e}")
            raise
