"""Model for filesystem entries"""
from datetime import datetime, timezone
from typing import Optional, TYPE_CHECKING


import sqlalchemy
from sqlalchemy.orm import Mapped, mapped_column, relationship

from program.db.db import db

if TYPE_CHECKING:
    from program.media.item import MediaItem





class FilesystemEntry(db.Model):
    """Model for filesystem entries"""
    __tablename__ = "FilesystemEntry"

    id: Mapped[int] = mapped_column(sqlalchemy.Integer, primary_key=True, autoincrement=True)

    # Fields for virtual files in RivenVFS
    path: Mapped[str] = mapped_column(sqlalchemy.String, nullable=False, index=True)  # virtual path in VFS
    file_size: Mapped[int] = mapped_column(sqlalchemy.BigInteger, default=0, nullable=False)
    is_directory: Mapped[bool] = mapped_column(sqlalchemy.Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        sqlalchemy.DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        sqlalchemy.DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False
    )

    original_filename: Mapped[Optional[str]] = mapped_column(sqlalchemy.String, nullable=True)  # Original filename from source

    # Restricted URL provided by the debrid service (e.g., RD /d/<id>)
    download_url: Mapped[Optional[str]] = mapped_column(sqlalchemy.String, nullable=True)
    # Persisted unrestricted (direct) URL for fast reads; refreshed on failures
    unrestricted_url: Mapped[Optional[str]] = mapped_column(sqlalchemy.String, nullable=True)

    provider: Mapped[Optional[str]] = mapped_column(sqlalchemy.String, nullable=True)
    provider_download_id: Mapped[Optional[str]] = mapped_column(sqlalchemy.String, nullable=True)

    # Availability flag: set to True once added to the VFS
    available_in_vfs: Mapped[bool] = mapped_column(sqlalchemy.Boolean, default=False, nullable=False)

    # Foreign key to MediaItem (many FilesystemEntries can belong to one MediaItem)
    media_item_id: Mapped[Optional[int]] = mapped_column(
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey("MediaItem.id", ondelete="CASCADE"),
        nullable=True
    )

    # Many-to-one relationship: many FilesystemEntries belong to one MediaItem
    media_item: Mapped[Optional["MediaItem"]] = relationship(
        "MediaItem",
        back_populates="filesystem_entries",
        lazy="selectin"
    )

    __table_args__ = (
        sqlalchemy.UniqueConstraint('path', name='uq_filesystem_entry_path'),
        sqlalchemy.Index('ix_filesystem_entry_path', 'path'),
        sqlalchemy.Index('ix_filesystem_entry_provider', 'provider'),
        sqlalchemy.Index('ix_filesystem_entry_created_at', 'created_at'),
    )

    def __repr__(self):
        return f"<FilesystemEntry(id={self.id}, path='{self.path}', size={self.file_size})>"



    def get_original_filename(self) -> str:
        """Get the original filename, falling back to path basename if not set"""
        if self.original_filename:
            return self.original_filename
        # Fallback to extracting from path
        import os
        return os.path.basename(self.path)



    @classmethod
    def create_virtual_entry(cls, path: str, download_url: str, provider: str,
                           provider_download_id: str, file_size: int = 0,
                           original_filename: str = None) -> "FilesystemEntry":
        """Create a virtual file filesystem entry"""
        return cls(
            path=path,
            download_url=download_url,
            provider=provider,
            provider_download_id=provider_download_id,
            file_size=file_size,
            original_filename=original_filename
        )

    def to_dict(self) -> dict:
        """Convert to dictionary representation"""
        return {
            "id": self.id,
            "path": self.path,
            "file_size": self.file_size,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "original_filename": self.original_filename,
            "download_url": self.download_url,
            "unrestricted_url": self.unrestricted_url,
            "provider": self.provider,
            "provider_download_id": self.provider_download_id,
            "available_in_vfs": self.available_in_vfs,
        }


# ============================================================================
# SQLAlchemy Event Listener for Automatic VFS Cleanup
# ============================================================================

from sqlalchemy import event
from loguru import logger

def cleanup_vfs_on_filesystem_entry_delete(mapper, connection, target: FilesystemEntry):
    """Automatically invalidate VFS caches when FilesystemEntry is deleted"""
    try:
        from program.program import riven
        from program.services.filesystem import FilesystemService

        filesystem_service: FilesystemService = riven.services.get(FilesystemService)
        if filesystem_service and filesystem_service.riven_vfs and target.path:
            vfs = filesystem_service.riven_vfs
            path = vfs._normalize_path(target.path)

            # Get inode before removal for cache invalidation
            ino = vfs._path_to_inode.pop(path, None)
            if ino is not None:
                vfs._inode_to_path.pop(ino, None)

            # Invalidate FUSE cache for the removed entry
            vfs._entry_cache_invalidate_path(path)
            vfs._invalidate_removed_entry_cache(path, ino)
            # Also attempt to invalidate parent directories that may have been pruned
            vfs._invalidate_potentially_removed_dirs(path)
    except Exception as e:
        logger.warning(f"Error invalidating VFS caches for {target.path}: {e}")


# Register event listener
event.listen(FilesystemEntry, "before_delete", cleanup_vfs_on_filesystem_entry_delete)
