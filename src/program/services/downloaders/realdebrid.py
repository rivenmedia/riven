from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel
from loguru import logger
from requests import exceptions

from program.services.downloaders.models import (
    VALID_VIDEO_EXTENSIONS,
    DebridFile,
    InvalidDebridFileException,
    TorrentContainer,
    TorrentFile,
    TorrentInfo,
    UserInfo,
)
from program.settings import settings_manager
from program.utils.request import CircuitBreakerOpen, SmartResponse, SmartSession
from program.services.streaming.exceptions.debrid_service_exception import (
    DebridServiceLinkUnavailable,
)

from .shared import DownloaderBase, premium_days_left


class RealDebridUserInfoResponse(BaseModel):
    id: int
    username: str
    email: str
    premium: int
    expiration: str
    points: int


class RealDebridDownload(BaseModel):
    id: str
    filename: str
    mimeType: str
    filesize: int
    link: str
    host: str
    chunks: int
    download: str
    generated: str


class RealDebridFile(BaseModel):
    id: int
    path: str
    bytes: int
    selected: Literal[0, 1]


class RealDebridTorrentInfo(BaseModel):
    id: str
    filename: str
    original_filename: str
    hash: str
    bytes: int
    progress: float
    status: str
    added: str
    files: list[RealDebridFile]
    links: list[str]


class RealDebridError(Exception):
    """Base exception for Real-Debrid related errors."""


class RealDebridAPI:
    """
    Minimal Real-Debrid API client using SmartSession for retries, rate limits, and circuit breaker.
    """

    BASE_URL = "https://api.real-debrid.com/rest/1.0"

    def __init__(self, api_key: str, proxy_url: str | None = None) -> None:
        """
        Args:
            api_key: Real-Debrid API key.
            proxy_url: Optional proxy URL used for both HTTP and HTTPS.
        """
        self.api_key = api_key
        self.proxy_url = proxy_url

        rate_limits = {
            # 250 req/min ~= 4.17 rps with capacity 250
            "api.real-debrid.com": {
                "rate": 250 / 60,
                "capacity": 250,
            },
        }

        proxies = {"http": proxy_url, "https": proxy_url} if proxy_url else None

        self.session = SmartSession(
            base_url=self.BASE_URL,
            rate_limits=rate_limits,
            proxies=proxies,
            retries=2,
            backoff_factor=0.5,
        )
        self.session.headers.update({"Authorization": f"Bearer {api_key}"})


class RealDebridDownloader(DownloaderBase):
    """
    Real-Debrid downloader with lean exception handling.

    Notes on failure & breaker behaviour:
    - Network/transport failures are retried by SmartSession, then counted against the per-domain
      CircuitBreaker; once OPEN, SmartSession raises CircuitBreakerOpen before the request.
    - HTTP status codes are not exceptions; we check response.ok and map to messages via _handle_error(...).
    """

    def __init__(self) -> None:
        self.key = "realdebrid"
        self.settings = settings_manager.settings.downloaders.real_debrid
        self.api: RealDebridAPI | None = None
        self.initialized = self.validate()

    def validate(self) -> bool:
        """
        Validate settings and current premium status.

        Returns:
            True if ready, else False.
        """
        if not self._validate_settings():
            return False

        proxy_url = self.PROXY_URL or None
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

        user_info = self.get_user_info()

        if not user_info:
            logger.error("Failed to retrieve Real-Debrid user info")
            return False

        if not user_info.premium_status:
            logger.error("Premium membership required")
            return False

        if user_info.premium_expires_at:
            logger.info(premium_days_left(user_info.premium_expires_at))

        return True

    def get_instant_availability(
        self,
        infohash: str,
        item_type: Literal["movie", "show", "season", "episode"],
    ) -> TorrentContainer | None:
        """
        Attempt a quick availability check by adding the torrent, selecting video files (if required),
        and returning a TorrentContainer when the status is 'downloaded'.
        """

        container: TorrentContainer | None = None
        torrent_id: str | None = None

        try:
            torrent_id = self.add_torrent(infohash)
            container, reason, info = self._process_torrent(
                torrent_id, infohash, item_type
            )

            if container is None and reason:
                # Failed validation - delete the torrent

                logger.debug(f"Availability check failed [{infohash}]: {reason}")

                if torrent_id:
                    try:
                        self.delete_torrent(torrent_id)
                    except Exception as e:
                        logger.debug(
                            f"Failed to delete failed torrent {torrent_id}: {e}"
                        )

                return None

            # Success - cache torrent_id AND info in container to avoid re-adding/re-fetching during download
            # This eliminates 2 API calls per stream (add_torrent + get_torrent_info in download phase)
            if container:
                container.torrent_id = torrent_id
                container.torrent_info = info

            return container

        except CircuitBreakerOpen:
            # Don't swallow the breaker; upstream orchestration decides backoff policy.
            logger.debug(f"Circuit breaker OPEN for Real-Debrid; skipping {infohash}")

            # Clean up on circuit breaker
            if torrent_id:
                try:
                    self.delete_torrent(torrent_id)
                except Exception:
                    pass

            raise
        except RealDebridError as e:
            # add_torrent/select_files/delete_torrent surface HTTP error context via _handle_error
            logger.warning(f"Availability check failed [{infohash}]: {e}")

            if torrent_id:
                try:
                    self.delete_torrent(torrent_id)
                except Exception:
                    pass

            return None
        except InvalidDebridFileException as e:
            logger.debug(
                f"Availability check failed [{infohash}]: Invalid debrid file(s) - {e}"
            )

            if torrent_id:
                try:
                    self.delete_torrent(torrent_id)
                except Exception:
                    pass

            return None
        except exceptions.ReadTimeout as e:
            logger.debug(f"Availability check failed [{infohash}]: Timeout - {e}")

            if torrent_id:
                try:
                    self.delete_torrent(torrent_id)
                except Exception:
                    pass

            return None
        except Exception as e:
            logger.error(
                f"Availability check failed [{infohash}]: Unexpected error - {e}"
            )

            if torrent_id:
                try:
                    self.delete_torrent(torrent_id)
                except Exception:
                    pass

            return None

    def _process_torrent(
        self,
        torrent_id: str,
        infohash: str,
        item_type: Literal["movie", "show", "season", "episode"],
    ) -> tuple[TorrentContainer | None, str | None, TorrentInfo | None]:
        """
        Process a single torrent and return (container, reason, info).

        Returns:
            (TorrentContainer or None, human-readable reason string if None, TorrentInfo or None)
        """

        info = self.get_torrent_info(torrent_id)

        if not info:
            return None, "no torrent info returned by Real-Debrid", None

        if not info.files:
            return None, "no files present in the torrent", None

        if info.status == "waiting_files_selection":
            video_exts = tuple(ext.lower() for ext in VALID_VIDEO_EXTENSIONS)
            video_ids: list[int] = [
                file_id
                for file_id, meta in info.files.items()
                if meta.filename.lower().endswith(video_exts)
            ]

            if not video_ids:
                return None, "no video files found to select", None

            # Select only video files
            self.select_files(torrent_id, video_ids)

            # Refresh info - REQUIRED to verify torrent is actually downloaded after selection
            # Real-Debrid may still be processing, so we need to check the actual status
            info = self.get_torrent_info(torrent_id)

            if not info:
                return None, "failed to refresh torrent info after selection", None

        if info.status == "downloaded":
            files: list[DebridFile] = []

            for file_id, meta in info.files.items():
                if meta.selected != 1:
                    continue

                try:
                    df = DebridFile.create(
                        path=meta.path,
                        filename=meta.filename,
                        filesize_bytes=meta.bytes,
                        filetype=item_type,
                        file_id=file_id,
                    )

                    if isinstance(df, DebridFile):
                        # Download URL is already available from get_torrent_info()
                        download_url = meta.download_url

                        if download_url:  # Empty string is falsy, so this works
                            df.download_url = download_url
                            logger.debug(
                                f"Using correlated download URL for {meta.filename}"
                            )
                        else:
                            logger.warning(
                                f"No download URL available for {meta.filename}"
                            )

                        files.append(df)
                except InvalidDebridFileException as e:
                    # noisy per-file details kept at debug
                    logger.debug(f"{infohash}: {e}")

            if not files:
                return None, "no valid files after validation", None

            # Return container WITH the TorrentInfo to avoid re-fetching in download phase
            return TorrentContainer(infohash=infohash, files=files), None, info

        if info.status in ("downloading", "queued"):
            return None, f"Not instantly available (status={info.status})", None

        if info.status in (
            "magnet_error",
            "error",
            "virus",
            "dead",
            "compressing",
            "uploading",
        ):
            return None, f"Invalid on Real-Debrid (status={info.status})", None

        return None, f"unsupported torrent status: {info.status}", None

    def add_torrent(self, infohash: str) -> str:
        """
        Add a torrent by infohash.

        Returns:
            Real-Debrid torrent id.

        Raises:
            CircuitBreakerOpen: If the per-domain breaker is OPEN.
            RealDebridError: If the API returns a failing status.
        """

        assert self.api

        magnet = f"magnet:?xt=urn:btih:{infohash}"
        response = self.api.session.post(
            "torrents/addMagnet", data={"magnet": magnet.lower()}
        )
        self._maybe_backoff(response)

        if not response.ok:
            raise RealDebridError(self._handle_error(response))

        class RealDebridAddMagnetResponse(BaseModel):
            id: str

        tid = RealDebridAddMagnetResponse.model_validate(response.json()).id

        if not tid:
            raise RealDebridError("No torrent ID returned by Real-Debrid.")

        return tid

    def select_files(
        self,
        torrent_id: int | str,
        file_ids: list[int] | None = None,
    ) -> None:
        """
        Select files within a torrent. If ids is None/empty, selects all files.
        """

        assert self.api

        selection = ",".join(str(x) for x in file_ids) if file_ids else "all"
        response = self.api.session.post(
            f"torrents/selectFiles/{torrent_id}",
            data={"files": selection},
        )

        if not response.ok:
            raise RealDebridError(self._handle_error(response))

    def get_torrent_info(self, torrent_id: int | str) -> TorrentInfo | None:
        """
        Retrieve torrent information and normalize into TorrentInfo.
        Returns None on API-level failure (non-OK) to match current behavior.
        """

        if not torrent_id:
            logger.debug("No torrent ID provided")
            return None

        assert self.api

        response = self.api.session.get(f"torrents/info/{torrent_id}")
        self._maybe_backoff(response)

        if not response.ok:
            logger.debug(
                f"Failed to get torrent info for {torrent_id}: {self._handle_error(response)}"
            )
            return None

        torrent_info = RealDebridTorrentInfo.model_validate(response.json())

        # Build initial files dict
        files = {
            file.id: TorrentFile(
                id=file.id,
                path=file.path,  # we're gonna need this to weed out the junk files
                bytes=file.bytes,
                selected=file.selected,
                download_url="",  # Will be populated by correlation, empty string instead of None
            )
            for file in torrent_info.files
        }

        # Correlate files to torrent links if torrent is downloaded
        links = torrent_info.links

        if torrent_info.status == "downloaded" and links:
            try:
                # Get selected files in order (these correspond to links by index)
                selected_files = [
                    (file.id, file) for file in torrent_info.files if file.selected == 1
                ]

                logger.debug(
                    f"Correlating {len(selected_files)} selected files with {len(links)} links for torrent {torrent_id}"
                )

                # Correlate selected files to links by index - use torrent links directly
                for i in range(min(len(selected_files), len(links))):
                    file_id, file_data = selected_files[i]
                    torrent_link = links[i]

                    # Use the torrent link directly as download_url - VFS will handle unrestricting
                    if file_id in files:
                        files[file_id].download_url = torrent_link
                        logger.debug(f"Added torrent link for file {file_data.path}")
                    else:
                        logger.warning(f"File key {file_id} not found in files dict")

            except Exception as e:
                logger.warning(
                    f"Failed to correlate torrent links for torrent {torrent_id}: {e}"
                )
                # Continue without download URLs - files will have download_url=""

        return TorrentInfo(
            id=torrent_info.id,
            name=torrent_info.filename,
            status=torrent_info.status,
            infohash=torrent_info.hash,
            bytes=torrent_info.bytes,
            created_at=datetime.fromisoformat(torrent_info.added),
            alternative_filename=torrent_info.original_filename,
            progress=torrent_info.progress,
            files=files,
            links=links,
        )

    def delete_torrent(self, torrent_id: int | str) -> None:
        """
        Delete a torrent on Real-Debrid.

        Raises:
            CircuitBreakerOpen: If the per-domain breaker is OPEN.
            RealDebridError: If the API returns a failing status.
        """

        assert self.api

        response = self.api.session.delete(f"torrents/delete/{torrent_id}")
        self._maybe_backoff(response)

        if not response.ok:
            raise RealDebridError(self._handle_error(response))

    def _maybe_backoff(self, response: SmartResponse) -> None:
        """
        Promote Real-Debrid 429/5xx responses to a service-level backoff signal.
        """

        code = response.status_code

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

    def get_downloads(self) -> list[RealDebridDownload]:
        """Get all downloads from Real-Debrid"""

        assert self.api

        response = self.api.session.get(f"downloads")
        self._maybe_backoff(response)

        if not response.ok:
            raise RealDebridError(self._handle_error(response))

        class DownloadList(BaseModel):
            data: list[RealDebridDownload]

        return DownloadList.model_validate({"data": response.json()}).data

    def unrestrict_link(self, link: str) -> RealDebridDownload | None:
        """
        Unrestrict a link using direct requests library, bypassing SmartSession rate limiting.

        This is used by VFS for frequent file access where rate limiting would cause issues
        (e.g., Plex scanning 100+ files). The VFS already caches unrestricted URLs in the
        database, so this is only called on cache misses or URL expiration.

        Returns:
            Response data dict with 'download', 'filename', 'filesize' fields, or None on error
        """

        try:
            assert self.api

            response = self.api.session.post(
                f"{self.api.BASE_URL}/unrestrict/link",
                data={"link": link},
                timeout=10,
            )

            self._maybe_backoff(response)

            if not response.ok:
                logger.debug(
                    f"Direct unrestrict failed with status {response.status_code}: {response.text}"
                )

                raise DebridServiceLinkUnavailable(provider=self.key, link=link)

            return RealDebridDownload.model_validate(response.json())
        except DebridServiceLinkUnavailable:
            raise
        except Exception as e:
            logger.debug(f"Direct unrestrict_link failed for {link}: {e}")
            return None

    def get_user_info(self) -> UserInfo | None:
        """
        Get normalized user information from Real-Debrid.

        Returns:
            UserInfo: Normalized user information including premium status and expiration
        """

        try:
            assert self.api

            response = self.api.session.get("user")
            self._maybe_backoff(response)

            if not response.ok:
                logger.error(f"Failed to get user info: {self._handle_error(response)}")
                return None

            data = RealDebridUserInfoResponse.model_validate(response.json())

            # Parse expiration datetime
            expiration = None
            premium_days = None

            if data.expiration:
                try:
                    expiration = datetime.fromisoformat(
                        data.expiration.replace("Z", "+00:00")
                    )
                    time_left = expiration - datetime.now(expiration.tzinfo)
                    premium_days = time_left.days
                except Exception as e:
                    logger.debug(f"Failed to parse expiration date: {e}")

            return UserInfo(
                service="realdebrid",
                username=data.username,
                email=data.email,
                user_id=data.id,
                premium_status="premium" if data.premium > 0 else "free",
                premium_expires_at=(
                    expiration.replace(tzinfo=None) if expiration else None
                ),
                premium_days_left=premium_days,
                points=data.points,
            )
        except CircuitBreakerOpen as e:
            logger.warning(f"Circuit breaker OPEN while getting user info: {e}")
            return None
        except Exception as e:
            logger.error(f"Failed to get user info: {e}")
            return None
