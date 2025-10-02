from __future__ import annotations
import os
from datetime import datetime, timezone
from typing import Optional, List, Dict, TYPE_CHECKING

from program.db.db import db
from program.media.filesystem_entry import FilesystemEntry


from loguru import logger as log

from sqlalchemy.orm.exc import StaleDataError

if TYPE_CHECKING:
    from program.services.downloaders import Downloader

class VFSDatabase:
    def __init__(self, downloader: Optional["Downloader"] = None) -> None:
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
        if not path.startswith('/'):
            path = '/' + path
        # Normalize path to handle double slashes and . components
        path = os.path.normpath(path)
        # Ensure it starts with / (normpath can remove leading slash)
        if not path.startswith('/'):
            path = '/' + path
        # Remove trailing slashes except for root
        if path != '/' and path.endswith('/'):
            path = path.rstrip('/')
        return path

    def _ensure_default_directories(self) -> None:
        """Ensure default directories exist in the VFS for library structure"""
        default_dirs = ['/movies', '/shows', '/anime_movies', '/anime_shows']

        with self.SessionLocal.begin() as s:
            for dir_path in default_dirs:
                # Check if directory already exists
                existing = s.query(FilesystemEntry.id).filter_by(
                    path=dir_path
                ).first()

                if not existing:
                    # Create directory entry
                    dir_entry = FilesystemEntry(
                        path=dir_path,
                        download_url=None,
                        provider=None,
                        provider_download_id=None,
                        file_size=0,
                        is_directory=True
                    )
                    s.add(dir_entry)

    # --- Queries ---
    def get_entry(self, path: str) -> Optional[Dict]:
        path = self._norm(path)
        with self.SessionLocal() as s:
            # Query FilesystemEntry for virtual files only
            fe = s.query(FilesystemEntry).filter_by(
                path=path
            ).one_or_none()
            if fe:
                return {
                    'virtual_path': fe.path,
                    'name': os.path.basename(fe.path) or '/',
                    'size': int(fe.file_size or 0),
                    'is_directory': bool(fe.is_directory),
                    'created': fe.created_at.isoformat() if fe.created_at else None,
                    'modified': fe.updated_at.isoformat() if fe.updated_at else None,
                }

            # Not in database - check if it's a virtual directory (parent of any files)
            if path == '/':
                return {'virtual_path': '/', 'name': '/', 'size': 0, 'is_directory': True, 'created': None, 'modified': None}

            # Check if any files exist under this path (making it a virtual directory)
            prefix = path + '/'
            has_children = s.query(FilesystemEntry.id).filter(
                FilesystemEntry.path.like(prefix + '%')
            ).first() is not None

            if has_children:
                return {
                    'virtual_path': path,
                    'name': os.path.basename(path),
                    'size': 0,
                    'is_directory': True,
                    'created': None,
                    'modified': None
                }

            return None

    def list_directory(self, path: str) -> List[Dict]:
        path = self._norm(path)
        prefix = '/' if path == '/' else path + '/'
        out: List[Dict] = []
        seen_names = set()

        with self.SessionLocal() as s:
            # Query all FilesystemEntry records under this path
            q = s.query(FilesystemEntry.path, FilesystemEntry.file_size, FilesystemEntry.is_directory, FilesystemEntry.created_at, FilesystemEntry.updated_at)

            if path == '/':
                rows = q.all()
            else:
                rows = q.filter(FilesystemEntry.path.like(prefix + '%')).all()

            for vp, size, is_dir, created, modified in rows:
                if vp == '/':
                    continue

                # Get the parent directory of this entry
                parent = os.path.dirname(vp.rstrip('/')) or '/'

                # If this entry is a direct child of the requested path
                if parent == path:
                    name = os.path.basename(vp.rstrip('/'))
                    if name not in seen_names:
                        seen_names.add(name)
                        out.append({
                            'virtual_path': vp,
                            'name': name,
                            'size': size,
                            'is_directory': bool(is_dir),
                            'created': created.isoformat() if created else None,
                            'modified': modified.isoformat() if modified else None
                        })
                # If this entry is deeper, create virtual directory entries for intermediate dirs
                elif vp.startswith(prefix):
                    # Extract the immediate child directory name
                    relative = vp[len(prefix):]
                    first_component = relative.split('/')[0]
                    if first_component and first_component not in seen_names:
                        seen_names.add(first_component)
                        virtual_dir_path = f"{path}/{first_component}" if path != '/' else f"/{first_component}"
                        out.append({
                            'virtual_path': virtual_dir_path,
                            'name': first_component,
                            'size': 0,
                            'is_directory': True,
                            'created': None,
                            'modified': None
                        })

        out.sort(key=lambda d: d['name'])
        return out

    def get_download_url(self, path: str, for_http: bool = False, force_resolve: bool = False) -> Optional[str]:
        """
        Get download URL for a file using database-driven provider lookup.

        Args:
            path: Virtual file path
            for_http: If True, return URL for HTTP requests (uses unrestricted URL)
            force_resolve: If True, force refresh of unrestricted URL from provider

        Returns:
            URL string or None if not found
        """
        path = self._norm(path)
        try:
            with self.SessionLocal.begin() as s:
                fe = s.query(FilesystemEntry).filter_by(
                    path=path
                ).one_or_none()
                if not fe:
                    return None

                # If no downloader available, return what we have
                if not self.downloader:
                    if not for_http:
                        log.debug(f"{path} -> using stored download_url (no downloader)")
                        return fe.download_url
                    chosen = fe.unrestricted_url or fe.download_url
                    log.debug(
                        f"{path} -> using {'unrestricted' if fe.unrestricted_url else 'download'} URL (no downloader)"
                    )
                    return chosen

                # For non-HTTP reads (persistence), return the stored download_url
                if not for_http:
                    log.debug(f"{path} -> returning stored download_url for persistence")
                    return fe.download_url

                # For HTTP reads: prefer persisted unrestricted URL if present and no forced refresh
                if fe.unrestricted_url and not force_resolve:
                    log.debug(f"{path} -> using persisted unrestricted URL")
                    return fe.unrestricted_url

                # Need to resolve/refresh the URL
                if not fe.download_url:
                    log.debug(f"{path} -> no download_url available; cannot resolve")
                    return None

                # Get the provider service from the downloader
                if not fe.provider:
                    log.warning(f"{path} -> no provider specified in database")
                    return fe.download_url

                # Find the matching service
                service = next(
                    (s for s in self.downloader.initialized_services if s.key == fe.provider),
                    None
                )
                if not service:
                    log.warning(f"{path} -> provider '{fe.provider}' not initialized")
                    return fe.unrestricted_url or fe.download_url

                # Resolve URL using the provider's resolve_link method
                try:
                    log.debug(f"{path} -> resolving URL via provider '{fe.provider}'")
                    result = service.resolve_link(fe.download_url)
                    if result and result.get('download_url'):
                        # Update persisted unrestricted URL for future reads
                        fe.unrestricted_url = result['download_url']
                        log.debug(f"{path} -> updated unrestricted_url")
                        # Update file size if available and not already set
                        if not fe.file_size and result.get('size'):
                            fe.file_size = int(result['size'])
                        return fe.unrestricted_url
                except Exception as e:
                    log.warning(f"{path} -> resolve failed via provider '{fe.provider}': {e}")

                # Fallback to what we have
                log.debug(
                    f"{path} -> fallback to {'unrestricted' if fe.unrestricted_url else 'download'} URL"
                )
                return fe.unrestricted_url or fe.download_url
        except StaleDataError:
            # Entry was deleted concurrently during read; treat as missing
            log.debug(f"{path} -> entry disappeared during read; returning None")
            return None

    def update_size(self, path: str, size: int) -> None:
        path = self._norm(path)
        with self.SessionLocal.begin() as s:
            fe = s.query(FilesystemEntry).filter_by(
                path=path
            ).one_or_none()
            if fe:
                fe.file_size = int(size)
                fe.updated_at = datetime.now(timezone.utc)

    def exists(self, path: str) -> bool:
        path = self._norm(path)
        if path == '/':
            return True
        with self.SessionLocal() as s:
            return s.query(FilesystemEntry.id).filter_by(
                path=path
            ).first() is not None

    # --- Mutations ---
    def add_directory(self, path: str) -> str:
        path = self._norm(path)
        with self.SessionLocal.begin() as s:
            if not self.exists(path):
                s.add(FilesystemEntry.create_virtual_entry(
                    path=path,
                    download_url=None,
                    provider=None,
                    provider_download_id=None,
                    file_size=0,
                    is_directory=True
                ))
        return path

    def add_file(self, path: str, url: Optional[str], size: int = 0, provider: Optional[str] = None, provider_download_id: Optional[str] = None) -> str:
        """Add a file to the VFS database. Directories are created virtually on-the-fly."""
        path = self._norm(path)
        with self.SessionLocal.begin() as s:
            fe = s.query(FilesystemEntry).filter_by(
                path=path
            ).one_or_none()
            if not fe:
                fe = FilesystemEntry.create_virtual_entry(
                    path=path,
                    download_url=url,
                    provider=provider,
                    provider_download_id=provider_download_id,
                    file_size=int(size or 0)
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
        path = self._norm(path)
        with self.SessionLocal.begin() as s:
            if path != '/':
                s.query(FilesystemEntry).filter(
                    (FilesystemEntry.path == path) |
                    (FilesystemEntry.path.like(path + '/%'))
                ).delete(synchronize_session=False)
                # Prune empty parent directories up the chain (but keep default roots)
                parent_dir = os.path.dirname(path.rstrip('/')) or '/'
                self._prune_empty_dirs(s, parent_dir)
                return True
        return False

    def _prune_empty_dirs(self, s, start_dir: str) -> None:
        """Remove empty directory entries up the chain, stopping at defaults or root."""
        default_dirs = {'/movies', '/shows', '/anime_movies', '/anime_shows'}
        cur = self._norm(start_dir)
        while cur not in ('/', '') and cur not in default_dirs:
            # Does this directory have any descendants left?
            has_children = s.query(FilesystemEntry.id).filter(
                FilesystemEntry.path.like(cur + '/%')
            ).first() is not None
            if has_children:
                break
            # Remove the directory entry itself if present
            s.query(FilesystemEntry).filter_by(path=cur, is_directory=True).delete(synchronize_session=False)
            # Move to parent
            cur = os.path.dirname(cur.rstrip('/')) or '/'

    def rename(self, old_path: str, new_path: str, provider: Optional[str] = None, provider_download_id: Optional[str] = None, download_url: Optional[str] = None, size: Optional[int] = None) -> bool:
        old_path = self._norm(old_path)
        new_path = self._norm(new_path)
        if old_path == new_path and provider is None and provider_download_id is None and download_url is None and size is None:
            return True
        with self.SessionLocal.begin() as s:
            fe = s.query(FilesystemEntry).filter_by(
                path=old_path
            ).one_or_none()
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
            children = s.query(FilesystemEntry).filter(FilesystemEntry.path.like(old_path + '/%')).all()
            for c in children:
                suffix = c.path[len(old_path):]
                new_child_path = new_path + suffix
                # Update child path (directories are virtual, no need to create them)
                c.path = new_child_path
            return True



