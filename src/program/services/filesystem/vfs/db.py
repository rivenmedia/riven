from __future__ import annotations
import os
from datetime import datetime, timezone
from typing import Optional, List, Dict

from program.db.db import db
from program.media.filesystem_entry import FilesystemEntry


from loguru import logger as log

from sqlalchemy.orm.exc import StaleDataError

class VFSDatabase:
    def __init__(self, provider_manager=None) -> None:
        self.provider_manager = provider_manager
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
            if not fe:
                if path == '/':
                    return {'virtual_path': '/', 'name': '/', 'size': 0, 'is_directory': True, 'modified': None}
                return None
            return {
                'virtual_path': fe.path,
                'name': os.path.basename(fe.path) or '/',
                'size': int(fe.file_size or 0),
                'is_directory': bool(fe.is_directory),
                'modified': fe.updated_at.isoformat() if fe.updated_at else None,
            }

    def list_directory(self, path: str) -> List[Dict]:
        path = self._norm(path)
        prefix = '/' if path == '/' else path + '/'
        out: List[Dict] = []
        with self.SessionLocal() as s:
            # Query FilesystemEntry for virtual files only
            q = s.query(FilesystemEntry.path, FilesystemEntry.file_size, FilesystemEntry.is_directory, FilesystemEntry.updated_at)
            if path == '/':
                rows = q.all()
                for vp, size, is_dir, lm in rows:
                    if vp == '/':
                        continue
                    parent = os.path.dirname(vp.rstrip('/')) or '/'
                    if parent == '/':
                        name = os.path.basename(vp.rstrip('/'))
                        out.append({'virtual_path': vp, 'name': name, 'size': size, 'is_directory': bool(is_dir), 'modified': lm.isoformat() if lm else None})
            else:
                rows = q.filter(FilesystemEntry.path.like(prefix + '%')).all()
                for vp, size, is_dir, lm in rows:
                    parent = os.path.dirname(vp.rstrip('/')) or '/'
                    if parent == path:
                        name = os.path.basename(vp.rstrip('/'))
                        out.append({'virtual_path': vp, 'name': name, 'size': size, 'is_directory': bool(is_dir), 'modified': lm.isoformat() if lm else None})
        out.sort(key=lambda d: d['name'])
        return out

    def get_download_url(self, path: str, for_http: bool = False, force_resolve: bool = False) -> Optional[str]:
        """
        Get download URL for a file.

        Args:
            path: Virtual file path
            for_http: If True, return URL for HTTP requests. Does not resolve unless force_resolve is True.
            force_resolve: If True, attempt to resolve provider URLs to unrestricted links and update storage.

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

                if not self.provider_manager:
                    # No provider manager
                    if not for_http:
                        log.debug(f"{path} -> using stored restricted URL (no provider_manager)")
                        return fe.download_url
                    chosen = fe.unrestricted_url or fe.download_url
                    log.debug(
                        f"{path} -> using {'unrestricted' if fe.unrestricted_url else 'restricted'} URL (no provider_manager)"
                    )
                    return chosen

                # Compute the restricted URL from stored data (if needed)
                stored_url = self.provider_manager.get_download_url(
                    fe.download_url,
                    fe.provider,
                    fe.provider_download_id
                )

                # Persist restricted URL if we didn't have one
                if stored_url and not fe.download_url:
                    fe.download_url = stored_url
                    log.debug(f"{path} -> persisted restricted URL")

                # If caller wants the stored URL for persistence, return it
                if not for_http:
                    log.debug(f"{path} -> returning restricted stored URL for persistence")
                    return stored_url

                # For HTTP reads: prefer persisted unrestricted URL if present and no forced refresh
                if fe.unrestricted_url and not force_resolve:
                    log.debug(f"{path} -> using persisted unrestricted URL")
                    return fe.unrestricted_url

                # If we don't even have a restricted URL, nothing to use
                if not stored_url:
                    log.debug(f"{path} -> no restricted URL available; cannot resolve")
                    return None

                # Resolve (first open or refresh-after-failure): try to obtain unrestricted URL
                provider_name = fe.provider or self.provider_manager.detect_provider_from_url(stored_url)
                if provider_name:
                    try:
                        log.debug(f"{path} -> resolving unrestricted URL via provider '{provider_name}'")
                        result = self.provider_manager.resolve_url(stored_url, provider_name)
                        if result and result.get('download_url'):
                            # Update persisted unrestricted URL for future reads
                            fe.unrestricted_url = result['download_url']
                            log.debug(f"{path} -> updated unrestricted_url and will use it for reads")
                            # Update file size if available and not already set
                            if not fe.file_size and result.get('size'):
                                fe.file_size = int(result['size'])
                            return fe.unrestricted_url
                    except Exception as e:
                        log.warning(f"{path} -> resolve failed via provider '{provider_name}': {e}")

                # Fallbacks
                log.debug(
                    f"{path} -> fallback to {'unrestricted' if fe.unrestricted_url else 'restricted'} URL"
                )
                return fe.unrestricted_url or stored_url
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

    def _ensure_dir_chain(self, s, path: str) -> None:
        if path in ('', '/'):
            return
        parts = [p for p in path.strip('/').split('/') if p]
        acc = ''
        for p in parts:
            acc = f"{acc}/{p}" if acc else f"/{p}"
            if not s.query(FilesystemEntry.id).filter_by(
                path=acc
            ).first():
                # Create directory entry manually since factory method doesn't support is_directory
                dir_entry = FilesystemEntry(
                    path=acc,
                    download_url=None,
                    provider=None,
                    provider_download_id=None,
                    file_size=0,
                    is_directory=True
                )
                s.add(dir_entry)

    def add_file(self, path: str, url: Optional[str], size: int = 0, provider: Optional[str] = None, provider_download_id: Optional[str] = None) -> str:
        path = self._norm(path)
        parent = os.path.dirname(path.rstrip('/')) or '/'
        with self.SessionLocal.begin() as s:
            self._ensure_dir_chain(s, parent)
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

            # Ensure parent directories exist for the new path
            new_parent = os.path.dirname(new_path.rstrip('/')) or '/'
            self._ensure_dir_chain(s, new_parent)

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
                # Ensure parent directories exist for each child's new path
                child_parent = os.path.dirname(new_child_path.rstrip('/')) or '/'
                self._ensure_dir_chain(s, child_parent)
                c.path = new_child_path
            return True



