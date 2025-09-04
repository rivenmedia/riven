from datetime import datetime
from typing import List, Optional, Union
from loguru import logger
from requests import Session, exceptions

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
    get_retry_policy,
)

from .shared import DownloaderBase, premium_days_left


class RealDebridError(Exception):
    """Base exception for Real-Debrid related errors"""

class RealDebridRequestHandler(BaseRequestHandler):
    def __init__(self, session: Session, base_url: str, request_logging: bool = False):
        super().__init__(session, response_type=ResponseType.DICT, base_url=base_url, custom_exception=RealDebridError, request_logging=request_logging)
        self.timeout = 30  # Real-Debrid timeout: 30 seconds total

    def execute(self, method: HttpMethod, endpoint: str, **kwargs) -> Union[dict, list]:
        # Add debugging for rate limiting
        if hasattr(self.session, 'limiter') and hasattr(self.session.limiter, 'bucket_group') and 'api.real-debrid.com' in self.session.limiter.bucket_group:
            bucket = self.session.limiter.bucket_group['api.real-debrid.com']
            bucket_size = f"{bucket._q.unfinished_tasks} / {bucket._q.maxsize}"
            logger.debug(f"Rate limiter bucket size before request: {bucket_size}")

        response = super()._request(method, endpoint, **kwargs)

        # Add debugging for rate limiting
        if hasattr(self.session, 'limiter') and hasattr(self.session.limiter, 'bucket_group') and 'api.real-debrid.com' in self.session.limiter.bucket_group:
            bucket = self.session.limiter.bucket_group['api.real-debrid.com']
            bucket_size = f"{bucket._q.unfinished_tasks} / {bucket._q.maxsize}"
            logger.debug(f"Rate limiter bucket size after request: {bucket_size}")

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
        rate_limit_params = get_rate_limit_params(per_minute=200, max_delay=15, enable_bucket_cleanup=True)
        retry_policy = get_retry_policy(retries=2, backoff_factor=0.5, status_forcelist=[429, 500, 502, 503, 504])
        self.session = create_service_session(rate_limit_params=rate_limit_params, retry_policy=retry_policy)
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
        Get instant availability for a single infohash.
        Creates a makeshift availability check since Real-Debrid no longer supports instant availability.
        """
        container: Optional[TorrentContainer] = None
        torrent_id = None

        try:
            torrent_id = self.add_torrent(infohash)
            container = self._process_torrent(torrent_id, infohash, item_type)
        except InvalidDebridFileException as e:
            logger.debug(f"Invalid Debrid File: {infohash}: {e}")
        except exceptions.ReadTimeout as e:
            logger.debug(f"Failed to get instant availability for {infohash}: [ReadTimeout] {e}")
        except Exception as e:
            if len(e.args) > 0:
                if " 503 " in e.args[0] or "Infringing" in e.args[0]:
                    logger.debug(f"Failed to get instant availability for {infohash}: [503] Infringing Torrent or Service Unavailable")
                elif " 429 " in e.args[0] or "Rate Limit Exceeded" in e.args[0]:
                    logger.debug(f"Failed to get instant availability for {infohash}: [429] Rate Limit Exceeded")
                elif " 404 " in e.args[0] or "Torrent Not Found" in e.args[0]:
                    logger.debug(f"Failed to get instant availability for {infohash}: [404] Torrent Not Found or Service Unavailable")
                elif " 400 " in e.args[0] or "Torrent file is not valid" in e.args[0]:
                    logger.debug(f"Failed to get instant availability for {infohash}: [400] Torrent file is not valid")
            else:
                logger.error(f"Failed to get instant availability for {infohash}: {e}")
        finally:
            if torrent_id is not None:
                try:
                    self.delete_torrent(torrent_id)
                except Exception as e:
                    logger.error(f"Failed to delete torrent {torrent_id}: {e}")

        return container

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

        if torrent_info.status == "downloaded":
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
            logger.debug(f"Skipping torrent {torrent_id} with infohash {infohash} because it is downloading. Torrent status on Real-Debrid: {torrent_info.status}")
            return None

        # if torrent_info.status in ("magnet_error", "error", "virus", "dead", "compressing", "uploading"):
        #     logger.debug(f"Torrent {torrent_id} with infohash {infohash} is invalid. Torrent status on Real-Debrid: {torrent_info.status}")
        #     return None

        logger.debug(f"Torrent {torrent_id} with infohash {infohash} is invalid. Torrent status on Real-Debrid: {torrent_info.status}")
        return None

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
            if e.response.status_code == 503:
                logger.debug(f"Failed to add torrent {infohash}: [503] Infringing Torrent or Service Unavailable")
                raise RealDebridError("Infringing Torrent or Service Unavailable")
            elif e.response.status_code == 429:
                logger.debug(f"Failed to add torrent {infohash}: [429] Rate Limit Exceeded")
                raise RealDebridError("Rate Limit Exceeded")
            elif e.response.status_code == 404:
                logger.debug(f"Failed to add torrent {infohash}: [404] Torrent Not Found or Service Unavailable")
                raise RealDebridError("Torrent Not Found or Service Unavailable")
            elif e.response.status_code == 400:
                logger.debug(f"Failed to add torrent {infohash}: [400] Torrent file is not valid")
                raise RealDebridError("Torrent file is not valid")
            elif e.response.status_code == 502:
                logger.debug(f"Failed to add torrent {infohash}: [502] Bad Gateway")
                raise RealDebridError("Bad Gateway")
            else:
                logger.debug(f"Failed to add torrent {infohash}: {e}")
                raise RealDebridError(f"Failed to add torrent {infohash}: {e}")

    def select_files(self, torrent_id: str, ids: List[int] = None) -> None:
        """Select files from a torrent"""
        try:
            selection = ",".join(str(file_id) for file_id in ids) if ids else "all"
            self.api.request_handler.execute(
                HttpMethod.POST,
                f"torrents/selectFiles/{torrent_id}",
                data={"files": selection}
            )
        except Exception as e:
            logger.error(f"Failed to select files for torrent {torrent_id}: {e}")
            raise

    def get_torrent_info(self, torrent_id: str) -> TorrentInfo:
        """Get information about a torrent"""
        try:
            data = self.api.request_handler.execute(HttpMethod.GET, f"torrents/info/{torrent_id}")
            files = {
                file["id"]: {
                    "path": file["path"], # we're gonna need this to weed out the junk files
                    "filename": file["path"].split("/")[-1],
                    "bytes": file["bytes"],
                    "selected": file["selected"]
                } for file in data["files"]
            }
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
