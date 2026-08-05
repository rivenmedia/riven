from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlencode

from loguru import logger

from program.media.item import ProcessedItemType
from program.services.downloaders.models import (
    DebridFile,
    InvalidDebridFileException,
    TorrentContainer,
    TorrentFile,
    TorrentInfo,
    UnrestrictedLink,
    UserInfo,
)
from program.settings import settings_manager
from program.utils import get_version
from program.utils.request import SmartResponse, SmartSession

from .shared import DownloaderBase, premium_days_left


class TorBoxError(Exception):
    """Raised when TorBox returns an unsuccessful response."""


class TorBoxAPI:
    BASE_URL = "https://api.torbox.app/v1/api"

    def __init__(self, api_key: str, proxy_url: str | None = None) -> None:
        proxies = {"http": proxy_url, "https": proxy_url} if proxy_url else None
        self.api_key = api_key
        self.session = SmartSession(
            base_url=self.BASE_URL,
            rate_limits={"api.torbox.app": {"rate": 5, "capacity": 300}},
            proxies=proxies,
            retries=2,
            backoff_factor=0.5,
        )
        self.session.headers.update(
            {
                "Authorization": f"Bearer {api_key}",
                "User-Agent": f"Riven/{get_version()} TorBox/1.0",
            }
        )


class TorBoxDownloader(DownloaderBase):
    """TorBox torrent provider, forward-ported from TorBox-App/riven."""

    def __init__(self) -> None:
        self.key = "torbox"
        self.settings = settings_manager.settings.downloaders.torbox
        self.api: TorBoxAPI | None = None
        self.initialized = self.validate()

    def validate(self) -> bool:
        if not self.settings.enabled:
            return False
        if not self.settings.api_key:
            logger.warning("TorBox API key is not set")
            return False

        self.api = TorBoxAPI(self.settings.api_key, self.PROXY_URL or None)
        try:
            user = self.get_user_info()
            if not user or user.premium_status != "premium":
                logger.error("TorBox premium membership required")
                return False
            if user.premium_expires_at:
                logger.info(premium_days_left(user.premium_expires_at))
            return True
        except Exception as exc:  # noqa: BLE001 - provider validation boundary
            logger.error(f"Failed to validate TorBox account: {exc}")
            return False

    @staticmethod
    def _data(response: SmartResponse) -> Any:
        payload = response.json()
        if not isinstance(payload, dict):
            raise TorBoxError("TorBox returned an invalid response")
        if not response.ok or payload.get("success") is False:
            detail = payload.get("detail") or payload.get("error")
            raise TorBoxError(detail or f"TorBox returned HTTP {response.status_code}")
        return payload.get("data")

    @staticmethod
    def _parse_date(value: str | None) -> datetime | None:
        if not value:
            return None
        return datetime.fromisoformat(value)

    def get_instant_availability(
        self, infohash: str, item_type: ProcessedItemType, **_: Any
    ) -> TorrentContainer | None:
        assert self.api
        try:
            response = self.api.session.get(
                "torrents/checkcached",
                params={"hash": infohash, "format": "object", "list_files": "true"},
            )
            data = self._data(response) or {}
            cached = data.get(infohash) or data.get(infohash.lower()) or {}
            if not cached:
                return None

            if not cached.get("files"):
                return None

            torrent_id = self.add_torrent(infohash)
            info = self.get_torrent_info(torrent_id)
            files: list[DebridFile] = []
            for file_id, file_data in info.files.items():
                try:
                    file = DebridFile.create(
                        path=file_data.path,
                        filename=file_data.filename,
                        filesize_bytes=file_data.bytes,
                        filetype=item_type,
                        file_id=file_id,
                    )
                    file.download_url = file_data.download_url
                    files.append(file)
                except (
                    InvalidDebridFileException,
                    KeyError,
                    TypeError,
                    ValueError,
                ) as exc:
                    logger.debug(f"{infohash}: {exc}")

            if not files:
                return None

            return TorrentContainer(
                infohash=infohash,
                files=files,
                torrent_id=torrent_id,
                torrent_info=info,
            )
        except Exception as exc:  # noqa: BLE001 - a failed provider must not halt fallback
            logger.debug(f"TorBox availability check failed [{infohash}]: {exc}")
            return None

    def add_torrent(self, infohash: str) -> str:
        assert self.api
        response = self.api.session.post(
            "torrents/createtorrent",
            data={
                "magnet": f"magnet:?xt=urn:btih:{infohash.lower()}",
                "add_only_if_cached": "true",
            },
        )
        data = self._data(response) or {}
        torrent_id = data.get("torrent_id")
        if torrent_id is None:
            raise TorBoxError("TorBox did not return a torrent ID")
        return str(torrent_id)

    def select_files(self, _torrent_id: int | str, _file_ids: list[int]) -> None:
        # TorBox downloads all torrent files and has no selection endpoint.
        return None

    def _permalink(self, torrent_id: int | str, file_id: int) -> str:
        assert self.api
        query = urlencode(
            {
                "token": self.api.api_key,
                "torrent_id": torrent_id,
                "file_id": file_id,
                "redirect": "true",
            }
        )
        return f"{self.api.BASE_URL}/torrents/requestdl?{query}"

    def get_torrent_info(self, torrent_id: int | str) -> TorrentInfo:
        assert self.api
        data = self._data(
            self.api.session.get(
                "torrents/mylist", params={"id": torrent_id, "bypass_cache": "true"}
            )
        )
        if not isinstance(data, dict):
            raise TorBoxError(f"Torrent {torrent_id} was not found")

        files: dict[int, TorrentFile] = {}
        links: list[str] = []
        for index, file_data in enumerate(data.get("files") or []):
            file_id = int(file_data.get("id", index))
            link = self._permalink(torrent_id, file_id)
            files[file_id] = TorrentFile(
                id=file_id,
                path=file_data["name"],
                bytes=file_data["size"],
                selected=1,
                download_url=link,
            )
            links.append(link)

        return TorrentInfo(
            id=str(data["id"]),
            name=data.get("name", ""),
            status=data.get("download_state"),
            infohash=data.get("hash"),
            progress=data.get("progress"),
            bytes=data.get("size"),
            created_at=self._parse_date(data.get("created_at")),
            files=files,
            links=links,
        )

    def delete_torrent(self, torrent_id: int | str) -> None:
        assert self.api
        self._data(
            self.api.session.post(
                "torrents/controltorrent",
                json={"torrent_id": int(torrent_id), "operation": "delete"},
            )
        )

    def unrestrict_link(self, link: str) -> UnrestrictedLink:
        return UnrestrictedLink(download=link, filename="file", filesize=0)

    def get_user_info(self) -> UserInfo | None:
        assert self.api
        try:
            data = self._data(self.api.session.get("user/me")) or {}
            expires = self._parse_date(data.get("premium_expires_at"))
            now = datetime.now(UTC)
            days = max((expires - now).days, 0) if expires else None
            plan = int(data.get("plan", 0) or 0)
            return UserInfo(
                service="torbox",
                username=data.get("username"),
                email=data.get("email"),
                user_id=data.get("id") or data.get("user_id") or "unknown",
                premium_status="premium" if plan > 0 else "free",
                premium_expires_at=expires,
                premium_days_left=days,
            )
        except Exception as exc:  # noqa: BLE001 - normalize provider errors to None
            logger.error(f"Failed to get TorBox user info: {exc}")
            return None
