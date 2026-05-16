"""In-memory VFS inventory when pyfuse3 (FUSE) is not available.

Exposes the same duck surface as :class:`program.services.filesystem.vfs.rivenvfs.RivenVFS`
for pipeline and ``GET /mount`` without mounting a real FUSE filesystem.
"""

from __future__ import annotations

import os
import threading
from typing import Any

from sqlalchemy.orm import object_session

from program.db.db import db_session
from program.media.item import MediaItem, Season, Show
from program.media.media_entry import MediaEntry
from program.services.downloaders import Downloader
from program.utils.logging import logger

from .vfs_profile_rematch import rematch_profiles_collect_item_ids


class MockRivenVFS:
    """Tracks VFS path → synthetic absolute path for web mount explorer only."""

    def __init__(self, mountpoint: str, downloader: Downloader) -> None:
        self._mountpoint = os.path.abspath(mountpoint)
        self._downloader = downloader
        self._lock = threading.RLock()
        self._paths: dict[str, str] = {}
        self._paths_by_media_item_id: dict[int, set[str]] = {}
        self._last_profile_hash: int | None = None
        self.mounted = True

        log = logger.bind(component="MockRivenVFS")
        logger.log(
            "VFS",
            f"MockRivenVFS (no FUSE) inventory at logical mount {self._mountpoint}",
        )
        log.debug("Mock VFS initialized; running initial full sync from database")
        self.sync(None)

    @property
    def opener_stats(self) -> dict[str, dict[str, Any]]:
        return {}

    @property
    def io_metrics_snapshot(self) -> dict[str, Any]:
        return {
            "network_bytes_ingested": 0,
            "client_bytes_served_warm": 0,
            "client_bytes_served_cold": 0,
            "client_warm_byte_ratio": None,
        }

    def _normalize_path(self, path: str) -> str:
        path = (path or "/").strip()
        if not path.startswith("/"):
            path = "/" + path
        if len(path) > 1 and path.endswith("/"):
            path = path.rstrip("/")
        return path

    def _abs_for_vfs_path(self, vfs_path: str) -> str:
        n = self._normalize_path(vfs_path)
        return os.path.join(self._mountpoint, n.lstrip("/"))

    def _clear_paths_for_media_item(self, media_item_id: int) -> int:
        with self._lock:
            to_drop = list(self._paths_by_media_item_id.pop(media_item_id, ()))
            for p in to_drop:
                self._paths.pop(p, None)
            return len(to_drop)

    def _register_path(self, vfs_path: str, media_item_id: int | None) -> str:
        n = self._normalize_path(vfs_path)
        abs_path = self._abs_for_vfs_path(n)
        with self._lock:
            self._paths[n] = abs_path
            if media_item_id is not None:
                self._paths_by_media_item_id.setdefault(media_item_id, set()).add(n)
        return n

    def _unregister_paths(self, paths: list[str]) -> int:
        removed = 0
        with self._lock:
            for raw in paths:
                n = self._normalize_path(raw)
                if self._paths.pop(n, None) is not None:
                    removed += 1
                for s in self._paths_by_media_item_id.values():
                    s.discard(n)
            empty_mids = [
                mid for mid, s in self._paths_by_media_item_id.items() if not s
            ]
            for mid in empty_mids:
                del self._paths_by_media_item_id[mid]
        return removed

    def get_mount_files_inventory(self) -> dict[str, str]:
        with self._lock:
            return dict(self._paths)

    def add(self, item: MediaItem) -> bool:
        log = logger.bind(component="MockRivenVFS")

        if not (entry := item.media_entry):
            log.debug(
                f"Item {item.id} has no media entry, skipping mock VFS add",
            )
            return False

        mid = entry.media_item_id
        if mid is not None:
            cleared = self._clear_paths_for_media_item(mid)
            if cleared:
                logger.trace(
                    f"MockVFS: removed {cleared} stale path(s) for media_item_id={mid}",
                )

        video_paths: list[str] = []
        for path in entry.get_all_vfs_paths():
            n = self._register_path(path, mid)
            video_paths.append(n)

        if not video_paths:
            log.debug(f"Item {item.id}: no VFS paths from media entry, add skipped")
            return False

        entry.available_in_vfs = True

        subtitle_slots = 0
        for subtitle in item.subtitles:
            language = subtitle.language
            for video_path in video_paths:
                directory = os.path.dirname(video_path)
                filename = os.path.basename(video_path)
                name_without_ext = os.path.splitext(filename)[0]
                subtitle_path = os.path.join(
                    directory,
                    f"{name_without_ext}.{language}.srt",
                )
                self._register_path(subtitle_path, subtitle.media_item_id)
                subtitle_slots += 1
            subtitle.available_in_vfs = True

        log.debug(
            f"MockVFS add item={item.id} ({item.log_string}): "
            f"{len(video_paths)} video path(s), {subtitle_slots} subtitle path(s)",
        )
        return True

    def remove(self, item: MediaItem) -> bool:
        log = logger.bind(component="MockRivenVFS")
        if isinstance(item, Show):
            for season in item.seasons:
                self.remove(season)
        if isinstance(item, Season):
            for episode in item.episodes:
                self.remove(episode)
        return self._remove_media_leaf(item, log)

    def _remove_media_leaf(self, item: MediaItem, log: Any) -> bool:
        """Unregister paths for a leaf item with a :class:`MediaEntry`."""

        if not item.filesystem_entry:
            log.debug(
                f"Item {item.id} has no filesystem_entry, skipping mock VFS remove",
            )
            return False

        entry = item.filesystem_entry

        if not isinstance(entry, MediaEntry):
            log.debug(
                f"Item {item.id} filesystem_entry is not a MediaEntry, skip remove",
            )
            return False

        video_paths_norm = [self._normalize_path(p) for p in entry.get_all_vfs_paths()]
        to_remove: set[str] = set(video_paths_norm)

        for video_path in video_paths_norm:
            directory = os.path.dirname(video_path)
            filename = os.path.basename(video_path)
            name_without_ext = os.path.splitext(filename)[0]
            for subtitle in item.subtitles:
                sp = os.path.join(
                    directory,
                    f"{name_without_ext}.{subtitle.language}.srt",
                )
                to_remove.add(self._normalize_path(sp))

        removed = self._unregister_paths(sorted(to_remove))
        entry.available_in_vfs = False
        for subtitle in item.subtitles:
            subtitle.available_in_vfs = False

        if removed:
            log.debug(
                f"MockVFS remove item={item.id}: dropped {removed} path(s)",
            )
            return True
        return False

    def sync(self, item: MediaItem | None = None) -> None:
        if item is None:
            self._sync_full()
        else:
            self._sync_individual(item)

    def _sync_full(self) -> None:
        log = logger.bind(component="MockRivenVFS")
        logger.log("VFS", "Full sync: re-matching library profiles (mock inventory)")

        result = rematch_profiles_collect_item_ids(
            last_profile_hash=self._last_profile_hash,
        )
        if result.skipped_profiles_unchanged:
            log.debug("Mock full sync skipped (library profiles unchanged)")
            return

        self._last_profile_hash = result.profile_hash
        item_ids = result.item_ids

        log.debug("Clearing mock VFS inventory for rebuild")
        with self._lock:
            self._paths.clear()
            self._paths_by_media_item_id.clear()

        logger.debug(f"Re-registering {len(item_ids)} items (mock)")

        registered_count = 0
        with db_session() as session:
            items = session.query(MediaItem).filter(MediaItem.id.in_(item_ids)).all()
            item_map = {i.id: i for i in items}

            for item_id in item_ids:
                try:
                    db_item = item_map.get(item_id)
                    if not db_item:
                        continue
                    if self.add(db_item):
                        registered_count += 1
                except Exception:
                    logger.exception(f"MockVFS: failed to register item {item_id}")

            if registered_count > 0:
                session.commit()

        with self._lock:
            path_count = len(self._paths)
        logger.log(
            "VFS",
            f"Full sync complete: re-registered {registered_count} items "
            f"(mock; {path_count} total paths)",
        )

    def _sync_individual(self, item: MediaItem) -> None:
        log = logger.bind(component="MockRivenVFS")
        logger.log(
            "VFS",
            f"Individual sync (mock): item {item.id} ({item.log_string})",
        )

        existing_session = object_session(item)

        if existing_session:
            existing_session.refresh(
                item,
                attribute_names=["subtitles", "filesystem_entries"],
            )
            self.remove(item)
            self.add(item)
        else:
            with db_session() as session:
                fresh = (
                    session.query(MediaItem).filter(MediaItem.id == item.id).first()
                )
                if not fresh:
                    log.warning(
                        f"Item {item.id} not found in database, cannot mock sync",
                    )
                    return
                self.remove(fresh)
                self.add(fresh)
                session.commit()

        log.debug(f"Mock individual sync complete for item {item.id}")

    def close(self) -> None:
        logger.log(
            "VFS",
            f"Closing MockRivenVFS (logical mount was {self._mountpoint})",
        )
        with self._lock:
            self._paths.clear()
            self._paths_by_media_item_id.clear()
        self.mounted = False
