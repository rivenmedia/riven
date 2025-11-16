from __future__ import annotations

from datetime import datetime, timezone
import time
from typing import List, Optional, Tuple

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


class AllDebridError(Exception):
    """Base exception for AllDebrid related errors."""


class AllDebridAPI:
    """
    Minimal AllDebrid API client using SmartSession for retries, rate limits, and circuit breaker.
    """

    BASE_URL = "https://api.alldebrid.com/v4"

    def __init__(self, api_key: str, proxy_url: Optional[str] = None) -> None:
        """
        Args:
            api_key: AllDebrid API key.
            proxy_url: Optional proxy URL used for both HTTP and HTTPS.
        """
        self.api_key = api_key
        self.proxy_url = proxy_url

        # AllDebrid rate limits: 12 req/sec and 600 req/min
        # Using conservative 10 req/sec (600 capacity)
        rate_limits = {"api.alldebrid.com": {"rate": 10, "capacity": 600}}
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


class AllDebridDownloader(DownloaderBase):
    """
    AllDebrid downloader with lean exception handling.

    Notes on failure & breaker behavior:
    - Network/transport failures are retried by SmartSession, then counted against the per-domain
      CircuitBreaker; once OPEN, SmartSession raises CircuitBreakerOpen before the request.
    - HTTP status codes are not exceptions; we check response.ok and map to messages via _handle_error(...).
    """

    def __init__(self) -> None:
        self.key = "alldebrid"
        self.settings = settings_manager.settings.downloaders.all_debrid
        self.api: AllDebridAPI | None = None
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
        self.api = AllDebridAPI(api_key=self.settings.api_key, proxy_url=proxy_url)
        return self._validate_premium()

    def _validate_settings(self) -> bool:
        """
        Returns:
            True when enabled and API key present; otherwise False.
        """

        if not self.settings.enabled:
            return False

        if not self.settings.api_key:
            logger.warning("AllDebrid API key is not set")
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
                logger.error("Failed to get AllDebrid user info")
                return False
            if user_info.premium_status != "premium":
                logger.error("AllDebrid premium membership required")
                return False
            if user_info.premium_expires_at:
                logger.info(premium_days_left(user_info.premium_expires_at))
            return True
        except Exception as e:
            logger.error(f"Failed to validate AllDebrid premium status: {e}")
            return False

    def _handle_error(self, resp: SmartResponse) -> str:
        """
        Map HTTP status codes and AllDebrid error codes to error messages.
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
            return "AllDebrid server error"
        else:
            # AllDebrid returns errors in data.error.message format
            if hasattr(resp.data, "error"):
                error = resp.data.error
                if hasattr(error, "message"):
                    return error.message
                elif hasattr(error, "code"):
                    return error.code
            return f"HTTP {status}"

    def _maybe_backoff(self, resp: SmartResponse) -> None:
        """
        Check if we should back off based on response.
        """
        if resp.status_code == 429:
            logger.warning("AllDebrid rate limit hit, backing off")

    def get_instant_availability(
        self, infohash: str, item_type: str
    ) -> Optional[TorrentContainer]:
        """
        Attempt a quick availability check by adding the magnet to AllDebrid
        and checking if it's instantly available (already cached).

        AllDebrid doesn't have a separate cache check endpoint,
        so we add the magnet and check its status.
        """
        container: Optional[TorrentContainer] = None
        torrent_id: Optional[int] = None

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
            logger.debug(f"Circuit breaker OPEN for AllDebrid; skipping {infohash}")
            if torrent_id:
                try:
                    self.delete_torrent(torrent_id)
                except Exception:
                    pass
            raise
        except AllDebridError as e:
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
        torrent_id: int,
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
            return None, "no torrent info returned by AllDebrid", None

        # Check if torrent is ready (statusCode 4 = Ready)
        # Status codes: 0=In Queue, 1=Downloading, 2=Compressing, 3=Uploading, 4=Ready
        if info.status != "Ready":
            return None, f"Not instantly available (status={info.status})", None

        # Get files from the magnet/files endpoint
        files_data = self._get_magnet_files(torrent_id)
        if not files_data:
            return None, "no files present in the torrent", None

        files: List[DebridFile] = []
        # Process files recursively from the nested structure
        # files_data is a list of file objects with 'n', 's', 'l', and optionally 'e' fields
        self._extract_files_recursive(files_data, item_type, files, infohash)

        if not files:
            return None, "no valid files after validation", None

        # Return container WITH the TorrentInfo to avoid re-fetching in download phase
        return TorrentContainer(infohash=infohash, files=files), None, info

    def _add_link_to_files_recursive(
        self, files: List, download_link: str, result: List
    ) -> None:
        """
        Recursively process files/folders and add download link to actual files.

        For season packs, AllDebrid returns nested structure:
        - files[0].n = folder name (e.g., "Show.S01.1080p")
        - files[0].e = array of episode files
        - files[0].e[0].n = episode filename
        - files[0].e[0].s = episode size

        We need to find the actual files (those with 's' field) and add the 'l' field.
        """
        for file_obj in files:
            # Check if this is a folder (has 'e' field with entries)
            entries = getattr(file_obj, "e", None)
            if entries and isinstance(entries, list):
                # This is a folder, recurse into it
                self._add_link_to_files_recursive(entries, download_link, result)
            else:
                # This is a file, add the download link
                file_with_link = type(
                    "obj",
                    (object,),
                    {
                        "n": getattr(file_obj, "n", ""),
                        "s": getattr(file_obj, "s", 0),
                        "e": None,
                        "l": download_link,
                    },
                )()
                result.append(file_with_link)

    def _extract_files_recursive(
        self,
        file_list: List,
        item_type: str,
        files: List[DebridFile],
        infohash: str,
        path_prefix: str = "",
    ) -> None:
        """
        Recursively extract files from AllDebrid's nested file structure.

        AllDebrid returns files with:
        - 'n' (name): filename or folder name
        - 's' (size): file size in bytes (only for files, not folders)
        - 'l' (link): download link (only for files, not folders)
        - 'e' (entries): array of nested files/folders (only for folders)
        """
        for file_entry in file_list:
            name = getattr(file_entry, "n", "")
            entries = getattr(file_entry, "e", None)

            current_path = f"{path_prefix}/{name}" if path_prefix else name

            # Check if this is a folder (has entries) or a file (has link)
            if entries and isinstance(entries, list):
                # This is a folder, recurse into it
                self._extract_files_recursive(
                    entries, item_type, files, infohash, current_path
                )
            else:
                # This is a file - it should have 'l' (link) and 's' (size)
                link = getattr(file_entry, "l", "")
                size = getattr(file_entry, "s", 0)

                if not link:
                    continue

                try:
                    df = DebridFile.create(
                        path=current_path,
                        filename=name,
                        filesize_bytes=size,
                        filetype=item_type,
                        file_id=None,
                    )

                    if isinstance(df, DebridFile):
                        df.download_url = link
                        files.append(df)
                except InvalidDebridFileException:
                    pass

    def add_torrent(self, infohash: str) -> int:
        """
        Add a magnet by infohash.

        Returns:
            AllDebrid magnet id.

        Raises:
            CircuitBreakerOpen: If the per-domain breaker is OPEN.
            AllDebridError: If the API returns a failing status.
        """
        magnet_url = f"magnet:?xt=urn:btih:{infohash}"
        resp: SmartResponse = self.api.session.post(
            "magnet/upload", data={"magnets[]": magnet_url}
        )
        self._maybe_backoff(resp)
        if not resp.ok:
            raise AllDebridError(self._handle_error(resp))

        # AllDebrid API returns {status: "success", data: {magnets: [{id: ...}]}}
        data = resp.data
        if not hasattr(data, "data"):
            raise AllDebridError("Invalid response format from AllDebrid")

        magnets = getattr(data.data, "magnets", None)
        if not magnets:
            raise AllDebridError("No magnet ID returned by AllDebrid")

        # Handle both list and single SimpleNamespace object
        if isinstance(magnets, list):
            if len(magnets) == 0:
                raise AllDebridError("No magnet ID returned by AllDebrid")
            magnet_info = magnets[0]
        else:
            # Single SimpleNamespace object
            magnet_info = magnets

        magnet_id = getattr(magnet_info, "id", None)
        if not magnet_id:
            raise AllDebridError("No magnet ID in response")

        return int(magnet_id)

    def select_files(self, torrent_id: int, file_ids: List[int]) -> None:
        """
        Select which files to download from the magnet.

        Note: AllDebrid doesn't require explicit file selection.
        Files are automatically available once the magnet is ready.
        """
        pass

    def _get_magnet_files(self, magnet_id: int) -> Optional[List]:
        """
        Get the files and download links for a magnet.

        Returns:
            List of file objects with 'n' (name), 's' (size), 'l' (link), and optionally 'e' (entries) fields.
        """
        try:
            # Get the magnet status which includes links
            status_resp: SmartResponse = self.api.session.post(
                "magnet/status", data={"id": str(magnet_id)}
            )
            self._maybe_backoff(status_resp)

            if not status_resp.ok:
                return None

            status_data = status_resp.data

            # Check for error
            if hasattr(status_data, "error"):
                return None

            if not hasattr(status_data, "data"):
                return None

            # Get magnets from status response
            magnets = getattr(status_data.data, "magnets", None)
            if not magnets:
                return None

            # Handle both list and single SimpleNamespace object
            if isinstance(magnets, list):
                if len(magnets) == 0:
                    return None
                magnet_obj = magnets[0]
            else:
                magnet_obj = magnets

            # Extract files from links in the status response
            # Structure: links[].link = download URL, links[].files = file/folder objects
            # For season packs: links[].files[0].e = array of episode files
            links = getattr(magnet_obj, "links", None)
            if links and isinstance(links, list) and len(links) > 0:
                all_files = []
                for link_obj in links:
                    download_link = getattr(link_obj, "link", None)
                    link_files = getattr(link_obj, "files", None)

                    if link_files and isinstance(link_files, list) and download_link:
                        # Recursively process files/folders and add download link
                        self._add_link_to_files_recursive(
                            link_files, download_link, all_files
                        )

                if all_files:
                    return all_files

            return None

        except Exception as e:
            logger.debug(f"Error getting magnet files: {e}")
            return None

    def get_torrent_info(self, torrent_id: int) -> TorrentInfo:
        """
        Get information about a specific magnet using its ID.

        Args:
            torrent_id: ID of the magnet to get info for.

        Returns:
            TorrentInfo: Current information about the magnet.

        Raises:
            CircuitBreakerOpen: If the per-domain breaker is OPEN.
            AllDebridError: If the API returns a failing status.
        """
        # AllDebrid API expects ID as string
        resp: SmartResponse = self.api.session.post(
            "magnet/status", data={"id": str(torrent_id)}
        )
        self._maybe_backoff(resp)
        if not resp.ok:
            raise AllDebridError(self._handle_error(resp))

        data = resp.data
        if not hasattr(data, "data"):
            raise AllDebridError("Invalid response format from AllDebrid")

        magnets = getattr(data.data, "magnets", None)
        if not magnets:
            raise AllDebridError(f"Magnet {torrent_id} not found")

        # Handle both list and single SimpleNamespace object
        if isinstance(magnets, list):
            if len(magnets) == 0:
                raise AllDebridError(f"Magnet {torrent_id} not found")
            magnet_data = magnets[0]
        else:
            # Single SimpleNamespace object
            magnet_data = magnets

        # Map AllDebrid status codes to status strings
        # 0=In Queue, 1=Downloading, 2=Compressing/Moving, 3=Uploading, 4=Ready, 5+=Errors
        status_code = getattr(magnet_data, "statusCode", 0)
        status_map = {
            0: "In Queue",
            1: "Downloading",
            2: "Compressing",
            3: "Uploading",
            4: "Ready",
            5: "Upload fail",
            6: "Internal error on unpacking",
            7: "Not downloaded in 20 min",
            8: "File too big",
            9: "Internal error",
            10: "Download took more than 72h",
            11: "Deleted on the hoster website",
        }
        status = status_map.get(status_code, "Unknown")

        # Parse timestamps
        upload_date = getattr(magnet_data, "uploadDate", 0)
        completion_date = getattr(magnet_data, "completionDate", 0)

        created_at = datetime.fromtimestamp(upload_date) if upload_date else None
        completed_at = (
            datetime.fromtimestamp(completion_date) if completion_date else None
        )

        return TorrentInfo(
            id=torrent_id,
            name=getattr(magnet_data, "filename", ""),
            status=status,
            infohash=None,  # AllDebrid doesn't return infohash in status
            bytes=getattr(magnet_data, "size", 0),
            created_at=created_at,
            completed_at=completed_at,
            progress=100.0 if status_code == 4 else 0.0,
            files={},  # Files are retrieved separately via magnet/files
            links=[],
        )

    def delete_torrent(self, torrent_id: int) -> None:
        """
        Delete a magnet on AllDebrid.

        Raises:
            CircuitBreakerOpen: If the per-domain breaker is OPEN.
            AllDebridError: If the API returns a failing status.
        """
        # AllDebrid API expects ID as string
        resp: SmartResponse = self.api.session.post(
            "magnet/delete", data={"id": str(torrent_id)}
        )
        self._maybe_backoff(resp)
        if not resp.ok:
            raise AllDebridError(self._handle_error(resp))

    def unrestrict_link(self, link: str) -> Optional[object]:
        """
        Unrestrict a link using AllDebrid.

        Args:
            link: The link to unrestrict.

        Returns:
            Object with 'download', 'filename', 'filesize' attributes, or None on error.
        """
        try:
            resp: SmartResponse = self.api.session.get(
                "link/unlock", params={"link": link}
            )
            self._maybe_backoff(resp)
            if not resp.ok:
                return None

            data = resp.data
            if not hasattr(data, "data"):
                return None

            link_data = data.data
            unrestricted_url = getattr(link_data, "link", "")

            if not unrestricted_url:
                return None

            # Return an object with attributes (matching RealDebrid's format)
            class UnrestrictedLink:
                def __init__(self, download, filename, filesize):
                    self.download = download
                    self.filename = filename
                    self.filesize = filesize

            return UnrestrictedLink(
                download=unrestricted_url,
                filename=getattr(link_data, "filename", "file"),
                filesize=getattr(link_data, "filesize", 0),
            )

        except Exception:
            return None

    def get_user_info(self) -> Optional[UserInfo]:
        """
        Get normalized user information from AllDebrid.

        Returns:
            UserInfo with normalized fields, or None on error.
        """
        try:
            resp: SmartResponse = self.api.session.get("user")
            self._maybe_backoff(resp)
            if not resp.ok:
                logger.error(f"Failed to get user info: {self._handle_error(resp)}")
                return None

            data = resp.data
            if not hasattr(data, "data"):
                return None

            user_data = getattr(data.data, "user", None)
            if not user_data:
                return None

            # Parse premium expiration
            premium_expires_at = None
            premium_days_left_val = None
            is_premium = getattr(user_data, "isPremium", False)

            if is_premium:
                premium_until = getattr(user_data, "premiumUntil", 0)
                if premium_until > 0:
                    premium_expires_at = datetime.fromtimestamp(
                        premium_until, tz=timezone.utc
                    )
                    premium_days_left_val = max(
                        0, (premium_expires_at - datetime.now(tz=timezone.utc)).days
                    )

            return UserInfo(
                service="alldebrid",
                username=getattr(user_data, "username", None),
                email=getattr(user_data, "email", None),
                user_id=getattr(user_data, "username", "unknown"),
                premium_status="premium" if is_premium else "free",
                premium_expires_at=premium_expires_at,
                premium_days_left=premium_days_left_val,
                points=getattr(user_data, "fidelityPoints", 0),
            )

        except Exception as e:
            logger.error(f"Error getting AllDebrid user info: {e}")
            return None
