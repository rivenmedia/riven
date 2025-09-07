from datetime import datetime
from typing import List, Optional, Union
from loguru import logger
from requests import exceptions

from program.services.downloaders.models import (
    VALID_VIDEO_EXTENSIONS,
    DebridFile,
    InvalidDebridFileException,
    TorrentContainer,
    TorrentInfo,
)
from program.settings.manager import settings_manager
from program.utils.request import SmartSession, CircuitBreakerOpen

from .shared import DownloaderBase, premium_days_left


class RealDebridError(Exception):
    """Base exception for Real-Debrid related errors"""


class RealDebridAPI:
    """Handles Real-Debrid API communication"""
    BASE_URL = "https://api.real-debrid.com/rest/1.0"

    def __init__(self, api_key: str, proxy_url: Optional[str] = None):
        self.api_key = api_key
        rate_limits = {"api.real-debrid.com": {"rate": 250/60, "capacity": 250}} # 250 requests per minute
        self.session = SmartSession(
            base_url=self.BASE_URL,
            rate_limits=rate_limits,
            retries=2,
            backoff_factor=0.5
        )
        self.session.headers.update({"Authorization": f"Bearer {api_key}"})
        if proxy_url:
            self.session.proxies.update({"http": proxy_url, "https": proxy_url})

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
            user_info = self.api.session.get("user")
            if not user_info.data.premium:
                logger.error("Premium membership required")
                return False

            expiration = datetime.fromisoformat(
                user_info.data.expiration.replace("Z", "+00:00")
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
        except CircuitBreakerOpen as e:
            logger.debug(f"Circuit breaker OPEN for Real-Debrid API, skipping {infohash}: {e}")
            raise
        except InvalidDebridFileException as e:
            logger.debug(f"Invalid Debrid File: {infohash}: {e}")
        except exceptions.ReadTimeout as e:
            logger.debug(f"Failed to get instant availability for {infohash}: [ReadTimeout] {e}")
        except Exception as e:
            if hasattr(e, "args") and len(e.args) > 0:
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

        if torrent_info and torrent_info.status == "waiting_files_selection":
            video_file_ids = [
                file_id for file_id, file_info in torrent_info.files.items()
                if file_info["filename"].endswith(tuple(ext.lower() for ext in VALID_VIDEO_EXTENSIONS))
            ]

            if not video_file_ids:
                logger.debug(f"No video files found in torrent {torrent_id} with infohash {infohash}")
                return None

            self.select_files(torrent_id, video_file_ids)
            torrent_info = self.get_torrent_info(torrent_id)

        if torrent_info and torrent_info.status == "downloaded":
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

        if torrent_info.status in ("magnet_error", "error", "virus", "dead", "compressing", "uploading"):
            logger.debug(f"Torrent {torrent_id} with infohash {infohash} is invalid. Torrent status on Real-Debrid: {torrent_info.status}")
            return None

        logger.debug(f"Torrent {torrent_id} with infohash {infohash} is invalid. Torrent status on Real-Debrid: {torrent_info.status}")
        return None

    def add_torrent(self, infohash: str) -> str:
        """Add a torrent by infohash"""
        try:
            magnet = f"magnet:?xt=urn:btih:{infohash}"
            response = self.api.session.post(
                "torrents/addMagnet",
                data={"magnet": magnet.lower()}
            )
            if hasattr(response.data, "id") and response.data.id:
                return response.data.id
            raise RealDebridError("No torrent ID in response")
        except CircuitBreakerOpen as e:
            raise
        except Exception as e:
            if hasattr(e, "response"):
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
            self.api.session.post(f"torrents/selectFiles/{torrent_id}", data={"files": selection})
        except CircuitBreakerOpen as e:
            logger.debug(f"Circuit breaker OPEN for Real-Debrid API, cannot select files for torrent {torrent_id}: {e}")
            raise  # Re-raise to be handled by the calling service
        except Exception as e:
            logger.error(f"Failed to select files for torrent {torrent_id}: {e}")
            raise

    def get_torrent_info(self, torrent_id: str) -> Optional[TorrentInfo]:
        """Get information about a torrent"""
        try:
            response = self.api.session.get(f"torrents/info/{torrent_id}")

            if hasattr(response.data, "files") and response.data.files:
                files = {
                    file.id: {
                        "path": file.path, # we're gonna need this to weed out the junk files
                        "filename": file.path.split("/")[-1],
                        "bytes": file.bytes,
                        "selected": file.selected
                    } for file in response.data.files
                }
            else:
                files = {}

            return TorrentInfo(
                id=torrent_id,
                name=response.data.filename,
                status=response.data.status,
                infohash=response.data.hash,
                bytes=response.data.bytes,
                created_at=response.data.added if hasattr(response.data, "added") else None,
                alternative_filename=response.data.original_filename if hasattr(response.data, "original_filename") else None,
                progress=response.data.progress if hasattr(response.data, "progress") else None,
                files=files,
            )
        except CircuitBreakerOpen as e:
            raise
        except Exception as e:
            logger.error(f"Failed to get torrent info for {torrent_id}: {e}")
            raise

    def delete_torrent(self, torrent_id: str) -> None:
        """Delete a torrent"""
        try:
            self.api.session.delete(f"torrents/delete/{torrent_id}")
        except CircuitBreakerOpen as e:
            raise
        except Exception as e:
            logger.error(f"Failed to delete torrent {torrent_id}: {e}")
            raise
