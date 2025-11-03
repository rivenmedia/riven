from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import List, Optional, Tuple

import requests
from loguru import logger

from program.services.downloaders.models import (
    DebridFile,
    InvalidDebridFileException,
    TorrentContainer,
    TorrentInfo,
    UserInfo,
)
from program.settings.manager import settings_manager
from program.utils.request import CircuitBreakerOpen, SmartResponse, SmartSession

from .shared import DownloaderBase, premium_days_left


class DebridLinkError(Exception):
    """Base exception for Debrid-Link related errors."""


class DebridLinkAPI:
    """
    Minimal Debrid-Link API client using SmartSession for retries, rate limits, and circuit breaker.
    """

    BASE_URL = "https://debrid-link.com/api/v2"

    def __init__(self, api_key: str, proxy_url: Optional[str] = None) -> None:
        """
        Args:
            api_key: Debrid-Link API key.
            proxy_url: Optional proxy URL used for both HTTP and HTTPS.
        """
        self.api_key = api_key
        self.proxy_url = proxy_url

        # Conservative rate limiting - Debrid-Link doesn't specify exact limits
        # Using 60 req/min as a safe default
        rate_limits = {"debrid-link.com": {"rate": 1, "capacity": 60}}
        proxies = None
        if proxy_url:
            proxies = {"http": proxy_url, "https": proxy_url}
        self.session = SmartSession(
            base_url=self.BASE_URL,
            rate_limits=rate_limits,
            proxies=proxies,
            retries=2,
            backoff_factor=0.5,
        )
        self.session.headers.update({"Authorization": f"Bearer {api_key}"})


class DebridLinkDownloader(DownloaderBase):
    """
    Debrid-Link downloader with lean exception handling.

    Notes on failure & breaker behavior:
    - Network/transport failures are retried by SmartSession, then counted against the per-domain
      CircuitBreaker; once OPEN, SmartSession raises CircuitBreakerOpen before the request.
    - HTTP status codes are not exceptions; we check response.ok and map to messages via _handle_error(...).
    """

    def __init__(self) -> None:
        self.key = "debridlink"
        self.settings = settings_manager.settings.downloaders.debrid_link
        self.api: Optional[DebridLinkAPI] = None
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
        self.api = DebridLinkAPI(api_key=self.settings.api_key, proxy_url=proxy_url)
        return self._validate_premium()

    def _validate_settings(self) -> bool:
        """
        Returns:
            True when enabled and API key present; otherwise False.
        """
        if not self.settings.enabled:
            return False
        if not self.settings.api_key:
            logger.warning("Debrid-Link API key is not set")
            return False
        return True

    def _validate_premium(self) -> bool:
        """
        Returns:
            True if premium is active; otherwise False.
        """
        try:
            user_info = self.get_user_info()
            if not user_info:
                logger.error("Failed to get Debrid-Link user info")
                return False
            if user_info.premium_status != "premium":
                logger.error("Debrid-Link premium membership required")
                return False
            if user_info.premium_expires_at:
                logger.info(premium_days_left(user_info.premium_expires_at))
            return True
        except Exception as e:
            logger.error(f"Failed to validate Debrid-Link premium status: {e}")
            return False

    def _handle_error(self, resp: SmartResponse) -> str:
        """
        Map HTTP status codes to error messages.
        """
        status = resp.status_code
        if status == 400:
            return "Bad request"
        elif status == 401:
            return "Unauthorized - check API key"
        elif status == 403:
            return "Forbidden"
        elif status == 404:
            return "Not found"
        elif status == 429:
            return "Rate limit exceeded"
        elif status >= 500:
            return "Debrid-Link server error"
        else:
            error_msg = getattr(resp.data, "error", None)
            return error_msg or f"HTTP {status}"

    def _maybe_backoff(self, resp: SmartResponse) -> None:
        """
        Check if we should back off based on response.
        """
        if resp.status_code == 429:
            logger.warning("Debrid-Link rate limit hit, backing off")

    def get_instant_availability(
        self, infohash: str, item_type: str
    ) -> Optional[TorrentContainer]:
        """
        Attempt a quick availability check by adding the torrent to the seedbox
        and checking if it's instantly available (already cached).

        Like Real-Debrid, Debrid-Link doesn't have a separate cache check endpoint,
        so we add the torrent and check its status.
        """
        container: Optional[TorrentContainer] = None
        torrent_id: Optional[str] = None

        try:
            torrent_id = self.add_torrent(infohash)
            container, reason, info = self._process_torrent(
                torrent_id, infohash, item_type
            )
            if container is None and reason:
                logger.debug(f"Availability check failed [{infohash}]: {reason}")
                # Failed validation - delete the torrent
                if torrent_id:
                    try:
                        self.delete_torrent(torrent_id)
                    except Exception as e:
                        logger.debug(
                            f"Failed to delete failed torrent {torrent_id}: {e}"
                        )
                return None

            # Success - cache torrent_id AND info in container to avoid re-adding/re-fetching during download
            if container:
                container.torrent_id = torrent_id
                container.torrent_info = info

            return container

        except CircuitBreakerOpen:
            logger.debug(f"Circuit breaker OPEN for Debrid-Link; skipping {infohash}")
            if torrent_id:
                try:
                    self.delete_torrent(torrent_id)
                except Exception:
                    pass
            raise
        except DebridLinkError as e:
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
        except Exception as e:
            logger.debug(f"Availability check failed [{infohash}]: {e}")
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
        item_type: str,
    ) -> Tuple[Optional[TorrentContainer], Optional[str], Optional[TorrentInfo]]:
        """
        Process a single torrent and return (container, reason, info).

        Returns:
            (TorrentContainer or None, human-readable reason string if None, TorrentInfo or None)
        """

        info = self.get_torrent_info(torrent_id)
        if not info:
            return None, "no torrent info returned by Debrid-Link", None

        if not info.files:
            return None, "no files present in the torrent", None

        # Status "downloaded" means completed/cached
        # Also check if downloadPercent == 100
        if info.status == "downloaded" or info.progress >= 100:
            files: List[DebridFile] = []
            for file_id, meta in info.files.items():
                # Debrid-Link doesn't have a "selected" field, all files are available
                try:
                    df = DebridFile.create(
                        path=meta["path"],
                        filename=meta["filename"],
                        filesize_bytes=meta["bytes"],
                        filetype=item_type,
                        file_id=file_id,
                    )

                    if isinstance(df, DebridFile):
                        # Store download URL if available
                        download_url = meta.get("download_url", "")
                        if download_url:
                            df.download_url = download_url
                            logger.debug(
                                f"Using correlated download URL for {meta['filename']}"
                            )
                        files.append(df)
                except InvalidDebridFileException as e:
                    logger.debug(f"{infohash}: {e}")

            if not files:
                return None, "no valid files after validation", None

            # Return container WITH the TorrentInfo to avoid re-fetching in download phase
            return TorrentContainer(infohash=infohash, files=files), None, info

        return None, f"Not instantly available (status={info.status})", None

    def add_torrent(self, infohash: str) -> str:
        """
        Add a torrent by infohash.

        Returns:
            Debrid-Link torrent id.

        Raises:
            CircuitBreakerOpen: If the per-domain breaker is OPEN.
            DebridLinkError: If the API returns a failing status.
        """
        url = f"magnet:?xt=urn:btih:{infohash}"
        # Don't set wait=True - we want the torrent to start immediately
        # The hash is only added if it's already cached on Debrid-Link servers
        resp: SmartResponse = self.api.session.post("seedbox/add", data={"url": url})
        self._maybe_backoff(resp)
        if not resp.ok:
            raise DebridLinkError(self._handle_error(resp))

        # Debrid-Link API v2 returns {success: true, value: {...}}
        data = resp.data
        if hasattr(data, "value"):
            data = data.value

        tid = getattr(data, "id", None)
        if not tid:
            raise DebridLinkError("No torrent ID returned by Debrid-Link.")
        return str(tid)

    def select_files(self, torrent_id: str, file_ids: List[int]) -> None:
        """
        Select which files to download from the torrent.

        Note: Debrid-Link doesn't require explicit file selection like Real-Debrid.
        Files are automatically available once the torrent is added.
        """
        pass

    def get_torrent_info(self, torrent_id: str) -> TorrentInfo:
        """
        Get information about a specific torrent using its ID.

        Args:
            torrent_id: ID of the torrent to get info for.

        Returns:
            TorrentInfo: Current information about the torrent.

        Raises:
            CircuitBreakerOpen: If the per-domain breaker is OPEN.
            DebridLinkError: If the API returns a failing status.
        """
        resp: SmartResponse = self.api.session.get(f"seedbox/list")
        self._maybe_backoff(resp)
        if not resp.ok:
            raise DebridLinkError(self._handle_error(resp))

        # Debrid-Link API v2 returns {success: true, value: [...]}
        data = resp.data
        if hasattr(data, "value"):
            torrents = data.value
        else:
            torrents = data

        torrent_data = None
        for t in torrents:
            if str(getattr(t, "id", None)) == str(torrent_id):
                torrent_data = t
                break

        if not torrent_data:
            raise DebridLinkError(f"Torrent {torrent_id} not found")

        # Parse file information
        # API returns files as a list, but we need to convert to dict with integer keys
        files = {}
        links = []
        torrent_files = getattr(torrent_data, "files", [])
        for idx, file_info in enumerate(torrent_files):
            file_name = getattr(file_info, "name", "")
            file_size = getattr(file_info, "size", 0)
            download_url = getattr(file_info, "downloadUrl", "")

            # Extract just the filename from the path
            filename = file_name.split("/")[-1] if "/" in file_name else file_name

            files[idx] = {
                "id": idx,
                "path": file_name,
                "filename": filename,
                "bytes": file_size,
                "selected": 1,  # All files are selected by default in Debrid-Link
                "download_url": download_url,
            }
            if download_url:
                links.append(download_url)

        # Convert status code to string for TorrentInfo model
        status_code = getattr(torrent_data, "status", 0)
        status = "downloaded" if status_code == 100 else "not_downloaded"

        return TorrentInfo(
            id=torrent_id,
            name=getattr(torrent_data, "name", ""),
            status=status,
            infohash=getattr(torrent_data, "hashString", ""),
            bytes=getattr(torrent_data, "totalSize", 0),
            created_at=datetime.fromtimestamp(getattr(torrent_data, "created", 0)),
            progress=getattr(torrent_data, "downloadPercent", 0),
            files=files,
            links=links,
        )

    def delete_torrent(self, torrent_id: str) -> None:
        """
        Delete a torrent on Debrid-Link.

        Raises:
            CircuitBreakerOpen: If the per-domain breaker is OPEN.
            DebridLinkError: If the API returns a failing status.
        """
        resp: SmartResponse = self.api.session.delete(f"seedbox/{torrent_id}/remove")
        self._maybe_backoff(resp)
        if not resp.ok:
            raise DebridLinkError(self._handle_error(resp))

    def unrestrict_link(self, link: str) -> Optional[object]:
        """
        Unrestrict a link using Debrid-Link.

        For Debrid-Link, links are already direct download URLs, so we just return them.

        Args:
            link: The link to unrestrict.

        Returns:
            Object with 'download', 'filename', 'filesize' attributes, or None on error.
        """

        # Debrid-Link provides direct download URLs, no unrestricting needed
        class UnrestrictedLink:
            def __init__(self, download, filename, filesize):
                self.download = download
                self.filename = filename
                self.filesize = filesize

        return UnrestrictedLink(
            download=link,
            filename="file",
            filesize=0,
        )

    def get_user_info(self) -> Optional[UserInfo]:
        """
        Get normalized user information from Debrid-Link.

        Returns:
            UserInfo with normalized fields, or None on error.
        """
        try:
            resp: SmartResponse = self.api.session.get("account/infos")
            self._maybe_backoff(resp)
            if not resp.ok:
                logger.error(f"Failed to get user info: {self._handle_error(resp)}")
                return None

            # Debrid-Link API v2 returns data in 'value' field
            data = resp.data
            if hasattr(data, "value"):
                data = data.value

            # Parse premium expiration
            premium_expires_at = None
            premium_days_left_val = None
            account_type = getattr(data, "accountType", 0)

            if account_type > 0:  # Premium account
                premium_until = getattr(data, "premiumLeft", 0)
                if premium_until > 0:
                    # premiumLeft is duration in seconds, not a timestamp
                    premium_expires_at = datetime.now(tz=timezone.utc) + timedelta(
                        seconds=premium_until
                    )
                    premium_days_left_val = max(
                        0, (premium_expires_at - datetime.now(tz=timezone.utc)).days
                    )

            return UserInfo(
                service="debridlink",
                username=getattr(data, "username", None),
                email=getattr(data, "email", None),
                user_id=getattr(data, "id", 0),
                premium_status="premium" if account_type > 0 else "free",
                premium_expires_at=premium_expires_at,
                premium_days_left=premium_days_left_val,
                points=getattr(data, "pts", 0),
            )

        except Exception as e:
            logger.error(f"Error getting Debrid-Link user info: {e}")
            return None
