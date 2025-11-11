from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Literal, TypedDict

from kink import di
from loguru import logger

from sqlalchemy.orm import Session
from program.db.db import db
from program.media.filesystem_entry import FilesystemEntry
from program.media.media_entry import MediaEntry
from program.services.streaming.exceptions import (
    DebridServiceLinkUnavailable,
)
from program.media.item import MediaItem
from program.program import Program
from program.types import Event
from routers.secure.items import apply_item_mutation

if TYPE_CHECKING:
    from program.services.downloaders import Downloader


class VFSEntry(TypedDict):
    virtual_path: str
    name: str
    size: int
    is_directory: bool
    entry_type: str | None
    created: str | None
    modified: str | None


class VFSDatabase:
    def __init__(self, downloader: "Downloader | None" = None) -> None:
        """
        Initialize VFS Database.

        Args:
            downloader: Downloader instance with initialized services for URL resolution
        """
        self.downloader = downloader
        self.SessionLocal = db.Session
        self._ensure_default_directories()

    def _norm(self, path: str) -> str:
        import os

        path = (path or "/").strip()
        if not path.startswith("/"):
            path = "/" + path
        # Normalize path to handle double slashes and . components
        path = os.path.normpath(path)
        # Ensure it starts with / (normpath can remove leading slash)
        if not path.startswith("/"):
            path = "/" + path
        # Remove trailing slashes except for root
        if path != "/" and path.endswith("/"):
            path = path.rstrip("/")
        return path

    def _ensure_default_directories(self) -> None:
        """
        Ensure default directories exist in the VFS for library structure.

        Note: Directories are created automatically by the VFS based on file paths.
        This method is kept for backward compatibility with existing code that may
        expect these directories to exist in the database.

        In practice, the VFS will create virtual directories on-the-fly when listing
        parent directories of files, so explicit directory creation is not required.
        """
        # Legacy directories for backward compatibility with existing data
        # These will be automatically created as virtual directories when files are added
        pass

    # --- Queries ---
    def get_entry(self, path: str) -> VFSEntry | None:
        """
        Retrieve metadata for a virtual filesystem entry or for a virtual directory inferred from stored entries.

        Parameters:
            path (str): Path to look up; the path will be normalized before lookup.

        Returns:
            dict: If an entry exists or the path represents a virtual directory, a dictionary with keys:
                - `virtual_path`: the normalized virtual path.
                - `name`: the basename of the path or `'/'` for root.
                - `size`: file size in bytes (0 for directories or unknown sizes).
                - `is_directory`: `True` for directories, `False` for files.
                - `entry_type`: type of entry ('media', 'subtitle', or None for virtual directories).
                - `created`: ISO 8601 creation timestamp or `None` if not available.
                - `modified`: ISO 8601 modification timestamp or `None` if not available.
            None: If no entry exists and the path does not correspond to any virtual directory.
        """
        path = self._norm(path)
        with self.SessionLocal() as s:
            # Query FilesystemEntry for virtual files only
            fe = s.query(FilesystemEntry).filter_by(path=path).one_or_none()
            if fe:
                return {
                    "virtual_path": fe.path,
                    "name": os.path.basename(fe.path) or "/",
                    "size": int(fe.file_size or 0),
                    "is_directory": bool(fe.is_directory),
                    "entry_type": fe.entry_type,
                    "created": fe.created_at.isoformat() if fe.created_at else None,
                    "modified": fe.updated_at.isoformat() if fe.updated_at else None,
                }

            # Not in database - check if it's a virtual directory (parent of any files)
            if path == "/":
                return {
                    "virtual_path": "/",
                    "name": "/",
                    "size": 0,
                    "is_directory": True,
                    "entry_type": None,
                    "created": None,
                    "modified": None,
                }

            # Check if any files exist under this path (making it a virtual directory)
            prefix = path + "/"
            has_children = (
                s.query(FilesystemEntry.id)
                .filter(FilesystemEntry.path.like(prefix + "%"))
                .first()
                is not None
            )

            if has_children:
                return {
                    "virtual_path": path,
                    "name": os.path.basename(path),
                    "size": 0,
                    "is_directory": True,
                    "entry_type": None,
                    "created": None,
                    "modified": None,
                }

            return None

    def list_directory(self, path: str) -> list[VFSEntry]:
        """
        List entries directly under a virtual filesystem path, including synthesized virtual intermediate directories for deeper descendants.

        Parameters:
            path (str): Virtual path to list (e.g., "/", "/movies"). Trailing slashes are normalized.

        Returns:
            List[dict]: A list of entry dictionaries sorted by name. Each dictionary contains:
                - virtual_path (str): Full virtual path of the entry or synthesized directory.
                - name (str): The final path component (entry name).
                - size (int): File size in bytes (0 for directories or synthesized entries).
                - is_directory (bool): True for directories (including synthesized virtual directories).
                - created (str|None): ISO 8601 timestamp of creation, or None if not available.
                - modified (str|None): ISO 8601 timestamp of last modification, or None if not available.
        """
        path = self._norm(path)
        prefix = "/" if path == "/" else path + "/"
        out: list[VFSEntry] = []
        seen_names = set()

        with self.SessionLocal() as s:
            # Query all FilesystemEntry records under this path
            q = s.query(
                FilesystemEntry.path,
                FilesystemEntry.file_size,
                FilesystemEntry.is_directory,
                FilesystemEntry.created_at,
                FilesystemEntry.updated_at,
            )

            if path == "/":
                rows = q.all()
            else:
                rows = q.filter(FilesystemEntry.path.like(prefix + "%")).all()

            for vp, size, is_dir, created, modified in rows:
                if vp == "/":
                    continue

                # Get the parent directory of this entry
                parent = os.path.dirname(vp.rstrip("/")) or "/"

                # If this entry is a direct child of the requested path
                if parent == path:
                    name = os.path.basename(vp.rstrip("/"))
                    if name not in seen_names:
                        seen_names.add(name)
                        out.append(
                            {
                                "virtual_path": vp,
                                "name": name,
                                "size": size,
                                "is_directory": bool(is_dir),
                                "created": created.isoformat() if created else None,
                                "modified": modified.isoformat() if modified else None,
                                "entry_type": None,
                            }
                        )
                # If this entry is deeper, create virtual directory entries for intermediate dirs
                elif vp.startswith(prefix):
                    # Extract the immediate child directory name
                    relative = vp[len(prefix) :]
                    first_component = relative.split("/")[0]
                    if first_component and first_component not in seen_names:
                        seen_names.add(first_component)
                        virtual_dir_path = (
                            f"{path}/{first_component}"
                            if path != "/"
                            else f"/{first_component}"
                        )
                        out.append(
                            {
                                "virtual_path": virtual_dir_path,
                                "name": first_component,
                                "size": 0,
                                "is_directory": True,
                                "created": None,
                                "modified": None,
                                "entry_type": None,
                            }
                        )

        out.sort(key=lambda d: d["name"])
        return out

    def get_subtitles_for_video(self, parent_original_filename: str) -> list[dict]:
        """
        Get all subtitles for a given video file.

        Parameters:
            parent_original_filename (str): Original filename of the parent MediaEntry (video file).

        Returns:
            list[Dict]: List of subtitle metadata dictionaries, each containing:
                - language: ISO 639-3 language code
                - file_size: Size of subtitle file in bytes
                - created_at: ISO 8601 timestamp
                - updated_at: ISO 8601 timestamp
        """
        with self.SessionLocal() as s:
            from program.media.subtitle_entry import SubtitleEntry

            subtitles = (
                s.query(SubtitleEntry)
                .filter_by(parent_original_filename=parent_original_filename)
                .all()
            )

            return [
                {
                    "language": sub.language,
                    "file_size": sub.file_size or 0,
                    "created_at": (
                        sub.created_at.isoformat() if sub.created_at else None
                    ),
                    "updated_at": (
                        sub.updated_at.isoformat() if sub.updated_at else None
                    ),
                }
                for sub in subtitles
            ]

    def get_subtitle_content(
        self, parent_original_filename: str, language: str
    ) -> bytes | None:
        """
        Get the subtitle content for a SubtitleEntry.

        In the new architecture, subtitles are looked up by their parent video's
        original_filename and language code, not by path.

        Parameters:
            parent_original_filename (str): Original filename of the parent MediaEntry (video file).
            language (str): ISO 639-3 language code (e.g., 'eng').

        Returns:
            bytes: Subtitle content encoded as UTF-8, or None if not found or not a subtitle.
        """
        with self.SessionLocal() as s:
            from program.media.subtitle_entry import SubtitleEntry

            # Query specifically for SubtitleEntry by parent and language
            subtitle = (
                s.query(SubtitleEntry)
                .filter_by(
                    parent_original_filename=parent_original_filename, language=language
                )
                .first()
            )

            if subtitle and subtitle.content:
                return subtitle.content.encode("utf-8")

            return None

    def get_entry_by_original_filename(
        self,
        original_filename: str,
        force_resolve: bool = False,
    ):
        """
        Get entry metadata and download URL by original filename.

        This is the NEW API that replaces path-based lookups.

        Args:
            original_filename: Original filename from debrid provider
            force_resolve: If True, force refresh of unrestricted URL from provider

        Returns:
            Dictionary with entry metadata and URLs, or None if not found
        """

        class GetEntryByOriginalFilenameResult(TypedDict):
            original_filename: str
            download_url: str | None
            unrestricted_url: str | None
            provider: str | None
            provider_download_id: str | None
            size: int | None
            created: str | None
            modified: str | None
            entry_type: Literal["media", "subtitle"]
            url: str | None

        try:
            with self.SessionLocal() as s:
                entry: MediaEntry | None = (
                    s.query(MediaEntry)
                    .filter(MediaEntry.original_filename == original_filename)
                    .first()
                )

                if not entry:
                    return None

                # Get download URL (with optional unrestricting)
                download_url = entry.download_url
                unrestricted_url = entry.unrestricted_url

                # If force_resolve or no unrestricted URL, try to unrestrict
                if (force_resolve or not unrestricted_url) and (
                    self.downloader and entry.provider
                ):
                    # Find service by matching the key attribute (services dict uses class as key)
                    service = next(
                        (
                            svc
                            for svc in self.downloader.services.values()
                            if svc.key == entry.provider
                        ),
                        None,
                    )

                    if service and hasattr(service, "unrestrict_link"):
                        try:
                            new_unrestricted = service.unrestrict_link(download_url)

                            if (
                                new_unrestricted
                                and new_unrestricted.download != unrestricted_url
                            ):
                                entry.unrestricted_url = new_unrestricted.download
                                unrestricted_url = new_unrestricted.download
                                s.commit()
                                logger.debug(
                                    f"Refreshed unrestricted URL for {original_filename}"
                                )
                        except DebridServiceLinkUnavailable as e:
                            logger.warning(
                                f"Failed to unrestrict URL for {original_filename}: {e}"
                            )

                            # If unrestricting fails, reset the MediaItem to trigger a new download
                            if entry.media_item:

                                def mutation(i: MediaItem, s: Session):
                                    i.blacklist_active_stream()
                                    i._reset()
                                    i.store_state()

                                apply_item_mutation(
                                    program=di[Program],
                                    item=entry.media_item,
                                    mutation_fn=mutation,
                                    session=s,
                                )

                                s.commit()

                            raise
                        except Exception as e:
                            logger.warning(
                                f"Failed to unrestrict URL for {original_filename}: {e}"
                            )

                chosen_url = unrestricted_url or download_url

                return GetEntryByOriginalFilenameResult(
                    original_filename=entry.original_filename,
                    download_url=download_url,
                    unrestricted_url=unrestricted_url,
                    provider=entry.provider,
                    provider_download_id=entry.provider_download_id,
                    size=entry.file_size,
                    created=(entry.created_at.isoformat()),
                    modified=(entry.updated_at.isoformat()),
                    entry_type="media",
                    url=chosen_url,  # The URL to use for this request
                )
        except DebridServiceLinkUnavailable:
            raise
        except Exception as e:
            logger.error(
                f"Error getting entry by original_filename {original_filename}: {e}"
            )
            return None

    def update_size(self, path: str, size: int) -> None:
        path = self._norm(path)
        with self.SessionLocal.begin() as s:
            fe = s.query(FilesystemEntry).filter_by(path=path).one_or_none()
            if fe:
                fe.file_size = int(size)
                fe.updated_at = datetime.now(timezone.utc)

    def exists(self, path: str) -> bool:
        path = self._norm(path)
        if path == "/":
            return True
        with self.SessionLocal() as s:
            return s.query(FilesystemEntry.id).filter_by(path=path).first() is not None

    # --- Mutations ---
    def add_directory(self, path: str) -> str:
        """
        Ensure a virtual directory exists at the given path and return the normalized path.

        Parameters:
            path (str): Path to the directory to add. The path is normalized (canonicalized and ensured to have a leading slash) before use.

        Returns:
            str: The normalized directory path.
        """
        path = self._norm(path)
        with self.SessionLocal.begin() as s:
            if not self.exists(path):
                dir_entry = MediaEntry.create_virtual_entry(
                    path=path,
                    download_url=None,
                    provider=None,
                    provider_download_id=None,
                    file_size=0,
                    original_filename=None,
                )
                dir_entry.is_directory = True
                s.add(dir_entry)
        return path

    def add_file(
        self,
        path: str,
        url: str | None,
        size: int = 0,
        provider: str | None = None,
        provider_download_id: str | None = None,
    ) -> str:
        """
        Create or update a file entry in the virtual filesystem; parent directories are implicit (virtual).

        If an entry for the normalized path does not exist, a new file entry is created with the provided download URL, provider metadata, and size. If an entry already exists, its download URL, file size, provider, provider_download_id, and modification timestamp are updated.

        Returns:
                the normalized path that was added or updated.
        """
        path = self._norm(path)
        with self.SessionLocal.begin() as s:
            fe = s.query(MediaEntry).filter_by(path=path).one_or_none()
            if not fe:
                fe = MediaEntry.create_virtual_entry(
                    path=path,
                    download_url=url,
                    provider=provider,
                    provider_download_id=provider_download_id,
                    file_size=int(size or 0),
                    original_filename=None,
                )
                # is_directory defaults to False, so no need to set it
                s.add(fe)
            else:
                fe.download_url = url
                fe.file_size = int(size or 0)
                fe.provider = provider
                fe.provider_download_id = provider_download_id
                fe.updated_at = datetime.now(timezone.utc)
        return path

    def remove(self, path: str) -> bool:
        """
        Remove a path and its descendants from the virtual filesystem.

        Performs ORM deletes for the entry at the normalized path and all of its descendants so ORM before_delete listeners can run (e.g., to invalidate VFS caches). After deletion, prunes empty parent directories up to the configured default roots. The root path ('/') is not removed.

        Parameters:
                path (str): The virtual path to remove; it will be normalized before use.

        Returns:
                bool: `True` if the operation was performed for a non-root path, `False` otherwise.
        """
        path = self._norm(path)
        with self.SessionLocal.begin() as s:
            if path != "/":
                # Fetch all entries to be deleted (path and descendants)
                # Use ORM delete instead of bulk delete so event listeners fire
                entries = (
                    s.query(FilesystemEntry)
                    .filter(
                        (FilesystemEntry.path == path)
                        | (FilesystemEntry.path.like(path + "/%"))
                    )
                    .all()
                )

                # Delete each entry using ORM so before_delete listener fires
                for entry in entries:
                    s.delete(entry)

                # Prune empty parent directories up the chain (but keep default roots)
                parent_dir = os.path.dirname(path.rstrip("/")) or "/"
                self._prune_empty_dirs(s, parent_dir)
                return True
        return False

    def _prune_empty_dirs(self, s, start_dir: str) -> None:
        """
        Prune empty directory entries upward from a starting directory until reaching a default directory or root.

        Deletes any directory row that has no descendants using ORM deletes so SQLAlchemy `before_delete` listeners run (used for VFS cache invalidation). Traversal stops when the current directory is `'/'`, empty, or one of the preserved default directories (`/movies`, `/shows`, `/anime_movies`, `/anime_shows`).

        Parameters:
            s: Database session used for ORM queries and deletes.
            start_dir (str): Virtual path at which to begin pruning; the path will be normalized.
        """
        default_dirs = {"/movies", "/shows", "/anime_movies", "/anime_shows"}
        cur = self._norm(start_dir)
        while cur not in ("/", "") and cur not in default_dirs:
            # Does this directory have any descendants left?
            has_children = (
                s.query(FilesystemEntry.id)
                .filter(FilesystemEntry.path.like(cur + "/%"))
                .first()
                is not None
            )
            if has_children:
                break
            # Remove the directory entry itself if present
            # Use ORM delete instead of bulk delete so event listeners fire
            dir_entry = (
                s.query(FilesystemEntry).filter_by(path=cur, is_directory=True).first()
            )
            if dir_entry:
                s.delete(dir_entry)
            # Move to parent
            cur = os.path.dirname(cur.rstrip("/")) or "/"

    def rename(
        self,
        old_path: str,
        new_path: str,
        provider: str | None = None,
        provider_download_id: str | None = None,
        download_url: str | None = None,
        size: int | None = None,
    ) -> bool:
        """
        Rename a filesystem entry and its descendants to a new virtual path, optionally updating provider and download metadata.

        Parameters:
            old_path (str): Existing virtual path of the entry to rename.
            new_path (str): Target virtual path to assign to the entry and its descendants.
            provider (Optional[str]): New provider identifier to set on the entry if provided.
            provider_download_id (Optional[str]): New provider-specific download ID to set if provided.
            download_url (Optional[str]): New stored download URL to set on the entry if provided.
            size (Optional[int]): New file size (in bytes) to set on the entry if provided.

        Returns:
            bool: `true` if the entry existed and was updated (including children), `false` if the source entry was not found.
        """
        old_path = self._norm(old_path)
        new_path = self._norm(new_path)
        if (
            old_path == new_path
            and provider is None
            and provider_download_id is None
            and download_url is None
            and size is None
        ):
            return True
        with self.SessionLocal.begin() as s:
            fe = s.query(FilesystemEntry).filter_by(path=old_path).one_or_none()
            if not fe:
                return False

            # Update the path (directories are virtual, no need to create them)
            fe.path = new_path
            if provider is not None:
                fe.provider = provider
            if provider_download_id is not None:
                fe.provider_download_id = provider_download_id
            if download_url is not None:
                fe.download_url = download_url
            if size is not None:
                fe.file_size = int(size)
            fe.updated_at = datetime.now(timezone.utc)
            # update children
            children = (
                s.query(FilesystemEntry)
                .filter(FilesystemEntry.path.like(old_path + "/%"))
                .all()
            )
            for c in children:
                suffix = c.path[len(old_path) :]
                new_child_path = new_path + suffix
                # Update child path (directories are virtual, no need to create them)
                c.path = new_child_path
            return True
