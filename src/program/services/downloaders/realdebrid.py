from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

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
from program.utils.request import CircuitBreakerOpen, SmartResponse, SmartSession

from .shared import DownloaderBase, premium_days_left


class RealDebridError(Exception):
    """Base exception for Real-Debrid related errors."""


class RealDebridAPI:
    """
    Minimal Real-Debrid API client using SmartSession for retries, rate limits, and circuit breaker.
    """

    BASE_URL = "https://api.real-debrid.com/rest/1.0"

    def __init__(self, api_key: str, proxy_url: Optional[str] = None) -> None:
        """
        Args:
            api_key: Real-Debrid API key.
            proxy_url: Optional proxy URL used for both HTTP and HTTPS.
        """
        # 250 req/min ~= 4.17 rps with capacity 250
        rate_limits = {"api.real-debrid.com": {"rate": 250 / 60, "capacity": 250}}
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
    """
    Real-Debrid downloader with lean exception handling.

    Notes on failure & breaker behavior:
    - Network/transport failures are retried by SmartSession, then counted against the per-domain
      CircuitBreaker; once OPEN, SmartSession raises CircuitBreakerOpen before the request.
    - HTTP status codes are not exceptions; we check response.ok and map to messages via _handle_error(...).
    """

    def __init__(self) -> None:
        self.key = "realdebrid"
        self.settings = settings_manager.settings.downloaders.real_debrid
        self.api: Optional[RealDebridAPI] = None
        self.initialized = self.validate()

    def validate(self) -> bool:
        """
        Validate settings and current premium status.

        Returns:
            True if ready, else False.
        """
        if not self._validate_settings():
            return False

        proxy_url = getattr(self, "PROXY_URL", None) or None
        self.api = RealDebridAPI(api_key=self.settings.api_key, proxy_url=proxy_url)
        return self._validate_premium()

    def _validate_settings(self) -> bool:
        """
        Returns:
            True when enabled and API key present; otherwise False.
        """
        if not self.settings.enabled:
            return False
        if not self.settings.api_key:
            logger.warning("Real-Debrid API key is not set")
            return False
        return True

    def _validate_premium(self) -> bool:
        """
        Returns:
            True if premium membership is active; otherwise False.
        """
        try:
            resp: SmartResponse = self.api.session.get("user")
            if not resp.ok:
                logger.error(f"Failed to validate premium: {self._handle_error(resp)}")
                return False

            if not resp.data.premium:
                logger.error("Premium membership required")
                return False

            expiration = datetime.fromisoformat(
                resp.data.expiration.replace("Z", "+00:00")
            ).replace(tzinfo=None)
            logger.info(premium_days_left(expiration))
            return True
        except CircuitBreakerOpen as e:
            logger.error(f"Circuit breaker while validating premium: {e}")
            return False
        except Exception as e:
            logger.error(f"Failed to validate premium status: {e}")
            return False

    def get_instant_availability(self, infohash: str, item_type: str) -> Optional[TorrentContainer]:
        """
        Attempt a quick availability check by adding the torrent, selecting video files (if required),
        and returning a TorrentContainer when the status is 'downloaded'.

        Behavior change: if this returns None, a concise reason is logged once at INFO level.
        """
        container: Optional[TorrentContainer] = None
        torrent_id: Optional[str] = None

        try:
            torrent_id = self.add_torrent(infohash)
            container, reason = self._process_torrent(torrent_id, infohash, item_type)
            if container is None and reason:
                logger.debug(f"Availability check failed [{infohash}]: {reason}")
            return container

        except CircuitBreakerOpen:
            # Don't swallow the breaker; upstream orchestration decides backoff policy.
            logger.debug(f"Circuit breaker OPEN for Real-Debrid; skipping {infohash}")
            raise
        except RealDebridError as e:
            # add_torrent/select_files/delete_torrent surface HTTP error context via _handle_error
            logger.warning(f"Availability check failed [{infohash}]: {e}")
            return None
        except InvalidDebridFileException as e:
            logger.debug(f"Availability check failed [{infohash}]: Invalid debrid file(s) - {e}")
            return None
        except exceptions.ReadTimeout as e:
            logger.debug(f"Availability check failed [{infohash}]: Timeout - {e}")
            return None
        except Exception as e:
            logger.error(f"Availability check failed [{infohash}]: Unexpected error - {e}")
            return None
        finally:
            # Best-effort cleanup; do not mask the main outcome.
            if torrent_id:
                try:
                    self.delete_torrent(torrent_id)
                except CircuitBreakerOpen:
                    logger.debug(f"Circuit breaker while deleting torrent {torrent_id}; suppressed in cleanup.")
                except Exception as e:
                    logger.error(f"Failed to delete torrent {torrent_id}: {e}")

    def _process_torrent(
        self,
        torrent_id: str,
        infohash: str,
        item_type: str,
    ) -> Tuple[Optional[TorrentContainer], Optional[str]]:
        """
        Process a single torrent and return (container, reason).

        Returns:
            (TorrentContainer or None, human-readable reason string if None)
        """
        info = self.get_torrent_info(torrent_id)
        if not info:
            return None, "no torrent info returned by Real-Debrid"

        if not info.files:
            return None, "no files present in the torrent"

        if info.status == "waiting_files_selection":
            video_exts = tuple(ext.lower() for ext in VALID_VIDEO_EXTENSIONS)
            video_ids: List[int] = [
                file_id
                for file_id, meta in info.files.items()
                if meta["filename"].lower().endswith(video_exts)
            ]
            if not video_ids:
                return None, "no video files found to select"

            # Select only video files
            self.select_files(torrent_id, video_ids)

            # Refresh info
            info = self.get_torrent_info(torrent_id)
            if not info:
                return None, "failed to refresh torrent info after selection"

        if info.status == "downloaded":
            files: List[DebridFile] = []
            for file_id, meta in info.files.items():
                if meta.get("selected", 0) != 1:
                    continue

                try:
                    df = DebridFile.create(
                        path=meta["path"],
                        filename=meta["filename"],
                        filesize_bytes=meta["bytes"],
                        filetype=item_type,
                        file_id=file_id,
                    )

                    if isinstance(df, DebridFile):
                        # Download URL is already available from get_torrent_info()
                        download_url = meta.get("download_url", "")
                        if download_url:  # Empty string is falsy, so this works
                            df.download_url = download_url
                            logger.debug(f"Using correlated download URL for {meta['filename']}")
                        else:
                            logger.warning(f"No download URL available for {meta['filename']}")
                        files.append(df)
                except InvalidDebridFileException as e:
                    logger.debug(f"{infohash}: {e}")  # noisy per-file details kept at debug

            if not files:
                return None, "no valid files after validation"

            return TorrentContainer(infohash=infohash, files=files), None

        if info.status in ("downloading", "queued"):
            return None, f"Not instantly available (status={info.status})"

        if info.status in ("magnet_error", "error", "virus", "dead", "compressing", "uploading"):
            return None, f"Invalid on Real-Debrid (status={info.status})"

        return None, f"unsupported torrent status: {info.status}"

    def add_torrent(self, infohash: str) -> str:
        """
        Add a torrent by infohash.

        Returns:
            Real-Debrid torrent id.

        Raises:
            CircuitBreakerOpen: If the per-domain breaker is OPEN.
            RealDebridError: If the API returns a failing status.
        """
        magnet = f"magnet:?xt=urn:btih:{infohash}"
        resp: SmartResponse = self.api.session.post("torrents/addMagnet", data={"magnet": magnet.lower()})
        self._maybe_backoff(resp)
        if not resp.ok:
            raise RealDebridError(self._handle_error(resp))

        tid = getattr(resp.data, "id", None)
        if not tid:
            raise RealDebridError("No torrent ID returned by Real-Debrid.")
        return tid

    def select_files(self, torrent_id: str, ids: Optional[List[int]] = None) -> None:
        """
        Select files within a torrent. If ids is None/empty, selects all files.
        """
        selection = ",".join(str(x) for x in ids) if ids else "all"
        resp: SmartResponse = self.api.session.post(
            f"torrents/selectFiles/{torrent_id}",
            data={"files": selection},
        )
        if not resp.ok:
            raise RealDebridError(self._handle_error(resp))

    def get_torrent_info(self, torrent_id: str) -> Optional[TorrentInfo]:
        """
        Retrieve torrent information and normalize into TorrentInfo.
        Returns None on API-level failure (non-OK) to match current behavior.
        """
        if not torrent_id:
            logger.debug("No torrent ID provided")
            return None

        resp: SmartResponse = self.api.session.get(f"torrents/info/{torrent_id}")
        self._maybe_backoff(resp)
        if not resp.ok:
            logger.debug(f"Failed to get torrent info for {torrent_id}: {self._handle_error(resp)}")
            return None

        data = resp.data
        if getattr(data, "error", None):
            logger.debug(
                f"Failed to get torrent info for {torrent_id}: '{data.error}' "
                f"code={getattr(data, 'error_code', 'N/A')}"
            )
            return None

        # Build initial files dict
        files = {
            file.id: {
                "path": file.path, # we're gonna need this to weed out the junk files
                "filename": file.path.split("/")[-1],
                "bytes": file.bytes,
                "selected": file.selected,
                "download_url": ""  # Will be populated by correlation, empty string instead of None
            } for file in data.files
        }

        # Correlate files to torrent links if torrent is downloaded
        links = data.links
        if data.status == "downloaded" and links:
            try:
                # Get selected files in order (these correspond to links by index)
                selected_files = [
                    (file.id, file) for file in data.files
                    if file.selected == 1
                ]

                logger.debug(f"Correlating {len(selected_files)} selected files with {len(links)} links for torrent {torrent_id}")

                # Correlate selected files to links by index - use torrent links directly
                for i in range(min(len(selected_files), len(links))):
                    file_id, file_data = selected_files[i]
                    torrent_link = links[i]

                    # Use the torrent link directly as download_url - VFS will handle unrestricting
                    if file_id in files:
                        files[file_id]["download_url"] = torrent_link
                        logger.debug(f"Added torrent link for file {file_data.path}")
                    else:
                        logger.warning(f"File key {file_id} not found in files dict")

            except Exception as e:
                logger.warning(f"Failed to correlate torrent links for torrent {torrent_id}: {e}")
                # Continue without download URLs - files will have download_url=""

        return TorrentInfo(
            id=data.id,
            name=data.filename,
            status=data.status,
            infohash=data.hash,
            bytes=data.bytes,
            created_at=data.added,
            alternative_filename=data.original_filename,
            progress=data.progress,
            files=files,
            links=links
        )

    def delete_torrent(self, torrent_id: str) -> None:
        """
        Delete a torrent on Real-Debrid.

        Raises:
            CircuitBreakerOpen: If the per-domain breaker is OPEN.
            RealDebridError: If the API returns a failing status.
        """
        resp: SmartResponse = self.api.session.delete(f"torrents/delete/{torrent_id}")
        self._maybe_backoff(resp)
        if not resp.ok:
            raise RealDebridError(self._handle_error(resp))

    def _maybe_backoff(self, resp: SmartResponse) -> None:
        """
        Promote Real-Debrid 429/5xx responses to a service-level backoff signal.
        """
        code = resp.status_code
        if code == 429 or (500 <= code < 600):
            # Name matches the breaker key in SmartSession rate_limits/breakers
            raise CircuitBreakerOpen("api.real-debrid.com")

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

    def get_downloads(self) -> list[dict]:
        """Get all downloads from Real-Debrid"""
        resp: SmartResponse = self.api.session.get(f"downloads")
        self._maybe_backoff(resp)
        if not resp.ok:
            raise RealDebridError(self._handle_error(resp))
        return resp.data

    def unrestrict_link(self, link: str) -> Optional[dict]:
        """Unrestrict a link using Real-Debrid API"""
        resp: SmartResponse = self.api.session.post(f"unrestrict/link", data={"link": link})
        self._maybe_backoff(resp)
        if not resp.ok:
            raise RealDebridError(self._handle_error(resp))
        return resp.data

    def resolve_link(self, link: str) -> Optional[Dict]:
        try:
            for d in self.get_downloads():
                if d.link == link or d.download == link:
                    return {
                        'download_url': d.download,
                        'name': d.filename,
                        'size': int(d.filesize or 0),
                    }
        except Exception:
            pass
        try:
            resp = self.unrestrict_link(link)
            return {
                'download_url': resp.download,
                'name': resp.filename or resp.original_filename,
                'size': int(resp.filesize or 0),
            }
        except Exception:
            return None
