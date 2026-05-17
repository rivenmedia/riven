from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote

import requests
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
from program.utils.request import CircuitBreakerOpen, SmartResponse, SmartSession

from .shared import DownloaderBase, premium_days_left


class TorBoxError(Exception):
    """Raised when TorBox returns an error payload or unexpected data."""


def _lower_key_dict(d: dict[str, Any]) -> dict[str, Any]:
    """TorBox JSON uses PascalCase in many responses (``Data``, ``TorrentId``, ``Plan``)."""

    return {str(k).lower(): v for k, v in d.items()}


def _unwrap_data(body: dict[str, Any]) -> Any:
    """Unwrap TorBox envelope (``data`` / ``Data``) and map API failures to ``TorBoxError``."""

    success = body.get("success")
    if success is None:
        success = body.get("Success")

    if success is False:
        detail = (
            body.get("detail")
            or body.get("Detail")
            or body.get("error")
            or body.get("Error")
            or body.get("message")
            or str(body)
        )
        raise TorBoxError(str(detail))

    if "data" in body:
        return body["data"]

    if "Data" in body:
        return body["Data"]

    return body


def _requestdl_permalink(api_key: str, torrent_id: int | str, file_id: int) -> str:
    token = quote(api_key, safe="")
    return (
        f"https://api.torbox.app/v1/api/torrents/requestdl"
        f"?token={token}&torrent_id={torrent_id}&file_id={file_id}&redirect=true"
    )


def _parse_content_disposition_filename(header: str | None) -> str:
    if not header:
        return ""

    # filename="foo.mkv" or filename*=UTF-8''foo.mkv
    if "filename*=" in header:
        part = header.split("filename*=", 1)[1].split(";", 1)[0].strip()
        if "''" in part:
            return part.split("''", 1)[-1].strip().strip('"')
    if "filename=" in header:
        part = header.split("filename=", 1)[1].split(";", 1)[0].strip().strip('"')
        return part

    return ""


def _collect_file_dicts(node: Any) -> list[dict[str, Any]]:
    """Flatten nested ``files`` trees from TorBox ``mylist`` into leaf file dicts."""

    found: list[dict[str, Any]] = []

    def walk(obj: Any) -> None:
        if isinstance(obj, list):
            for item in obj:
                walk(item)
        elif isinstance(obj, dict):
            o = _lower_key_dict(obj)
            has_id = "id" in o
            name = o.get("name") or o.get("short_name") or o.get("filename")
            size = o.get("size")
            if size is None:
                size = o.get("bytes")
            if size is None:
                size = o.get("file_size")

            if has_id and name is not None:
                try:
                    int(o["id"])
                except (TypeError, ValueError):
                    pass
                else:
                    found.append(o)

            for key in ("files", "children", "contents", "file_list", "items"):
                if key in o:
                    walk(o[key])

    walk(node)

    return found


class TorBoxAPI:
    BASE_URL = "https://api.torbox.app/v1/api"

    def __init__(self, api_key: str, proxy_url: str | None = None) -> None:
        self.api_key = api_key
        proxies = {"http": proxy_url, "https": proxy_url} if proxy_url else None

        self.session = SmartSession(
            base_url=self.BASE_URL,
            rate_limits={
                "api.torbox.app": {
                    "rate": 5.0,
                    "capacity": 30,
                },
            },
            proxies=proxies,
            retries=2,
            backoff_factor=0.5,
        )
        self.session.headers.update({"Authorization": f"Bearer {api_key}"})


class TorBoxDownloader(DownloaderBase):
    """
    TorBox debrid downloader.

    Flow mirrors Real-Debrid: ``get_instant_availability`` leaves ``torrent_id`` and
    ``torrent_info`` on the container so the orchestrator does not re-add the torrent.

    Uses TorBox ``checkcached`` first, then ``createtorrent`` + ``mylist`` polling.
    File URLs are stored as ``requestdl`` permalinks (token in query) per TorBox guidance.
    """

    API_BREAKER_DOMAIN = "api.torbox.app"
    API_RATE_PER_SECOND = 5.0

    _STILL_FETCHING_STATES = frozenset(
        {
            "downloading",
            "queued",
            "metadl",
            "magnet_conversion",
            "checkingresumedata",
        }
    )
    _BAD_STATES = frozenset(
        {
            "error",
            "dead",
            "magnet_error",
        }
    )

    def __init__(self) -> None:
        self.key = "torbox"
        self.settings = settings_manager.settings.downloaders.torbox
        self.api: TorBoxAPI | None = None
        self.initialized = self.validate()

    def validate(self) -> bool:
        if not self._validate_settings():
            return False

        proxy_url = self.PROXY_URL or None
        self.api = TorBoxAPI(api_key=self.settings.api_key, proxy_url=proxy_url)

        return self._validate_premium()

    def _validate_settings(self) -> bool:
        if not self.settings.enabled:
            return False

        if not self.settings.api_key:
            logger.warning("TorBox API key is not set")
            return False

        return True

    def _validate_premium(self) -> bool:
        try:
            user_info = self.get_user_info()

            if not user_info:
                logger.error("Failed to retrieve TorBox user info")
                return False

            if user_info.premium_status != "premium":
                logger.error("TorBox premium membership required")
                return False

            if user_info.premium_expires_at:
                logger.info(premium_days_left(user_info.premium_expires_at))

            return True
        except Exception as e:
            logger.error(f"Failed to validate TorBox premium status: {e}")
            return False

    def _maybe_backoff(self, response: SmartResponse) -> None:
        code = response.status_code

        if code == 429 or (500 <= code < 600):
            raise CircuitBreakerOpen("api.torbox.app")

    def _get_json(self, response: SmartResponse) -> dict[str, Any]:
        self._maybe_backoff(response)

        if not response.ok:
            raise TorBoxError(response.reason or f"HTTP {response.status_code}")

        body = response.json()

        if not isinstance(body, dict):
            raise TorBoxError("TorBox returned non-object JSON")

        return body

    def _check_cached_raw(self, infohash: str) -> list[dict[str, Any]]:
        assert self.api

        resp = self.api.session.get(
            "torrents/checkcached",
            params={
                "hash": infohash.lower(),
                "format": "list",
                "list_files": "true",
            },
            timeout=30,
        )
        data = _unwrap_data(self._get_json(resp))

        if not data:
            return []

        if isinstance(data, list):
            return [x for x in data if isinstance(x, dict)]

        if isinstance(data, dict):
            return [data]

        return []

    def get_instant_availability(
        self,
        infohash: str,
        item_type: ProcessedItemType,
    ) -> TorrentContainer | None:
        assert self.api

        torrent_id: str | None = None

        try:
            cached_rows = self._check_cached_raw(infohash)

            if not cached_rows:
                logger.debug(f"TorBox checkcached: no cache entry for {infohash}")
                return None

            torrent_id = self.add_torrent(infohash)
            info = self._poll_until_ready(torrent_id)

            if not info:
                logger.debug(f"TorBox: torrent {torrent_id} did not become ready for {infohash}")
                try:
                    self.delete_torrent(torrent_id)
                except Exception:
                    pass
                return None

            container, reason = self._build_container_from_info(infohash, item_type, info)

            if not container:
                logger.debug(f"TorBox availability failed [{infohash}]: {reason}")

                try:
                    self.delete_torrent(torrent_id)
                except Exception:
                    pass

                return None

            container.torrent_id = torrent_id
            container.torrent_info = info

            return container

        except CircuitBreakerOpen:
            logger.debug(f"Circuit breaker OPEN for TorBox; skipping {infohash}")

            if torrent_id:
                try:
                    self.delete_torrent(torrent_id)
                except Exception:
                    pass

            raise
        except TorBoxError as e:
            logger.warning(f"TorBox availability check failed [{infohash}]: {e}")

            if torrent_id:
                try:
                    self.delete_torrent(torrent_id)
                except Exception:
                    pass

            return None
        except InvalidDebridFileException as e:
            logger.debug(f"TorBox availability check failed [{infohash}]: {e}")

            if torrent_id:
                try:
                    self.delete_torrent(torrent_id)
                except Exception:
                    pass

            return None
        except Exception as e:
            logger.debug(f"TorBox availability check failed [{infohash}]: {e}")

            if torrent_id:
                try:
                    self.delete_torrent(torrent_id)
                except Exception:
                    pass

            return None

    def _poll_until_ready(self, torrent_id: str, max_attempts: int = 45) -> TorrentInfo | None:
        assert self.api

        for _ in range(max_attempts):
            info = self.get_torrent_info(torrent_id)
            state = (info.status or "").lower().replace(" ", "")

            if state in self._BAD_STATES or "magnet_error" in state:
                logger.debug(f"TorBox torrent {torrent_id} in bad state: {info.status}")
                return None

            if info.files and state not in self._STILL_FETCHING_STATES:
                return info

            time.sleep(1.5)

        logger.debug(f"TorBox torrent {torrent_id} polling timed out")
        return None

    def _build_container_from_info(
        self,
        infohash: str,
        item_type: ProcessedItemType,
        info: TorrentInfo,
    ) -> tuple[TorrentContainer | None, str | None]:
        if not info.files:
            return None, "no files on torrent after TorBox reported ready"

        files = list[DebridFile]()

        for file_id, tf in info.files.items():
            try:
                df = DebridFile.create(
                    path=tf.path,
                    filename=tf.filename,
                    filesize_bytes=tf.bytes,
                    filetype=item_type,
                    file_id=file_id,
                )
            except InvalidDebridFileException as e:
                logger.debug(f"{infohash}: {e}")
                continue

            df.download_url = _requestdl_permalink(self.settings.api_key, info.id, file_id)
            files.append(df)

        if not files:
            return None, "no valid video files after validation"

        return TorrentContainer(infohash=infohash, files=files), None

    def add_torrent(self, infohash: str) -> str:
        assert self.api

        magnet = f"magnet:?xt=urn:btih:{infohash.lower()}"
        resp = self.api.session.post(
            "torrents/createtorrent",
            data={"magnet": magnet},
            timeout=60,
        )
        body = self._get_json(resp)
        data = _unwrap_data(body)

        if not isinstance(data, dict):
            raise TorBoxError("createtorrent returned unexpected data")

        d = _lower_key_dict(data)
        tid = d.get("torrent_id") or d.get("torrentid") or d.get("id") or d.get("queuedid")

        if tid is None:
            raise TorBoxError("createtorrent returned no torrent_id")

        if isinstance(tid, float):
            tid = int(tid)

        return str(tid)

    def select_files(self, torrent_id: int | str, file_ids: list[int]) -> None:
        # TorBox selection is handled when the torrent is linked to cached data; no-op.
        _ = (torrent_id, file_ids)

    def get_torrent_info(self, torrent_id: int | str) -> TorrentInfo:
        assert self.api

        resp = self.api.session.get(
            "torrents/mylist",
            params={"id": str(torrent_id), "bypass_cache": "true"},
            timeout=30,
        )
        body = self._get_json(resp)
        data = _unwrap_data(body)

        if isinstance(data, list):
            if not data:
                raise TorBoxError("empty mylist response")

            def row_id(x: dict[str, Any]) -> str:
                return str(_lower_key_dict(x).get("id", ""))

            row = next((x for x in data if isinstance(x, dict) and row_id(x) == str(torrent_id)), data[0])
        elif isinstance(data, dict):
            row = data
        else:
            raise TorBoxError("unexpected mylist payload")

        if not isinstance(row, dict):
            raise TorBoxError("mylist row is not an object")

        return self._row_to_torrent_info(row)

    def _row_to_torrent_info(self, row: dict[str, Any]) -> TorrentInfo:
        row = _lower_key_dict(row)
        tid = row.get("id")
        name = row.get("name") or row.get("title") or ""
        if isinstance(name, str) and "/" in name:
            display_name = name.split("/")[-1]
        else:
            display_name = str(name)

        status = row.get("download_state") or row.get("status") or row.get("state")
        infohash = row.get("hash") or row.get("info_hash") or ""
        size = row.get("size") or row.get("bytes") or row.get("total_size") or 0

        try:
            size_int = int(size)
        except (TypeError, ValueError):
            size_int = 0

        raw_files = row.get("files") or row.get("file_list") or []
        tor = row.get("torrent")

        if isinstance(tor, dict) and not raw_files:
            raw_files = _lower_key_dict(tor).get("files") or []

        leafs = _collect_file_dicts(raw_files)

        if not leafs and isinstance(raw_files, list):
            leafs = [
                _lower_key_dict(x)
                for x in raw_files
                if isinstance(x, dict) and any(str(k).lower() == "id" for k in x)
            ]

        files: dict[int, TorrentFile] = {}

        for f in leafs:
            f = _lower_key_dict(f) if f else f
            try:
                fid = int(f["id"])
            except (KeyError, TypeError, ValueError):
                continue

            path = str(f.get("name") or f.get("path") or display_name)
            try:
                nbytes = int(f.get("size") or f.get("bytes") or 0)
            except (TypeError, ValueError):
                nbytes = 0

            files[fid] = TorrentFile(
                id=fid,
                path=path,
                bytes=nbytes,
                selected=1,
                download_url="",
            )

        added = row.get("created_at") or row.get("created") or row.get("added") or row.get("createdat")

        created: datetime | None = None

        if isinstance(added, str):
            try:
                created = datetime.fromisoformat(added.replace("Z", "+00:00"))
            except ValueError:
                created = None
        elif isinstance(added, (int, float)):
            try:
                created = datetime.fromtimestamp(float(added), tz=timezone.utc)
            except (OSError, ValueError):
                created = None

        return TorrentInfo(
            id=str(tid) if tid is not None else "",
            name=display_name or str(tid),
            status=str(status) if status is not None else None,
            infohash=str(infohash) if infohash else None,
            progress=None,
            bytes=size_int,
            created_at=created,
            alternative_filename=str(name) if name else None,
            files=files,
            links=[],
        )

    def delete_torrent(self, torrent_id: int | str) -> None:
        assert self.api

        resp = self.api.session.post(
            "torrents/controltorrent",
            json={"torrent_id": str(torrent_id), "operation": "delete"},
            timeout=30,
        )

        if resp.status_code == 204:
            return

        self._get_json(resp)

    def get_user_info(self) -> UserInfo | None:
        assert self.api

        try:
            resp = self.api.session.get("user/me", timeout=20)
            body = self._get_json(resp)
            data = _unwrap_data(body)

            if data is None:
                logger.error("TorBox user/me returned empty data")
                return None

            if not isinstance(data, dict):
                logger.error("TorBox user/me returned unexpected data")
                return None

            d = _lower_key_dict(data)

            plan = d.get("plan")
            is_subscribed = d.get("issubscribed")

            if is_subscribed is True:
                premium_ok = True
            elif isinstance(plan, (int, float)):
                premium_ok = plan > 0
            elif plan is not None:
                premium_ok = str(plan).strip().lower() not in ("0", "free", "", "none")
            else:
                premium_ok = False

            expiration: datetime | None = None
            premium_days: int | None = None

            raw_exp = (
                d.get("premium_expires_at")
                or d.get("premiumexpiresat")
                or d.get("expires_at")
            )

            if isinstance(raw_exp, str) and raw_exp:
                try:
                    expiration = datetime.fromisoformat(raw_exp.replace("Z", "+00:00"))

                    if expiration.tzinfo:
                        delta = expiration - datetime.now(tz=expiration.tzinfo)
                    else:
                        delta = expiration - datetime.now()

                    premium_days = delta.days
                except ValueError:
                    expiration = None

            uid = d.get("id") or d.get("user_id") or d.get("email") or "unknown"

            if isinstance(uid, float):
                uid = int(uid)

            return UserInfo(
                service="torbox",
                username=d.get("username") or d.get("name") or d.get("customer"),
                email=d.get("email"),
                user_id=uid,
                premium_status="premium" if premium_ok else "free",
                premium_expires_at=expiration.replace(tzinfo=None) if expiration else None,
                premium_days_left=premium_days,
                total_downloaded_bytes=(
                    int(td)
                    if isinstance((td := d.get("totaldownloaded")), (int, float))
                    else None
                ),
            )
        except CircuitBreakerOpen as e:
            logger.warning(f"Circuit breaker OPEN while getting TorBox user info: {e}")
            return None
        except Exception as e:
            logger.error(f"Failed to get TorBox user info: {e}")
            return None

    def unrestrict_link(self, link: str) -> UnrestrictedLink | None:
        """
        Resolve a TorBox ``requestdl`` permalink (or follow redirects) to a direct CDN URL.
        """

        from program.utils.debrid_cdn_url import _url_log_hint

        proxies: dict[str, str] | None = None

        if self.api and getattr(self.api.session, "proxies", None):
            p = self.api.session.proxies

            if p:
                proxies = p

        try:
            # stream=True: do not read the full response body; ``requestdl`` can redirect
            # to the CDN with a multi-GB body; without streaming, urllib3 reads until EOF.
            with requests.get(
                link,
                allow_redirects=True,
                timeout=(15.0, 45.0),
                headers={"User-Agent": "Riven/1.0"},
                proxies=proxies,
                stream=True,
            ) as r:
                r.raise_for_status()

                logger.debug(
                    f"TorBox unrestrict_link ok status={r.status_code} "
                    f"final={_url_log_hint(r.url)}"
                )

                final_url = r.url
                fname = _parse_content_disposition_filename(r.headers.get("Content-Disposition"))
                clen = r.headers.get("Content-Length")

                try:
                    fsize = int(clen) if clen else 0
                except ValueError:
                    fsize = 0

                if not fname and final_url:
                    fname = final_url.rsplit("/", 1)[-1].split("?", 1)[0]

                return UnrestrictedLink(download=final_url, filename=fname or "download", filesize=fsize)
        except Exception as e:
            logger.debug(
                f"TorBox unrestrict_link failed for url={_url_log_hint(link)}: {e}"
            )
            return None
