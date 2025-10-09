"""Model for filesystem entries"""
from datetime import datetime, timezone
from typing import Optional, TYPE_CHECKING


import sqlalchemy
from sqlalchemy.orm import Mapped, mapped_column, relationship

from program.db.db import db

if TYPE_CHECKING:
    from program.media.item import MediaItem


class FilesystemEntry(db.Model):
    """Base model for all virtual filesystem entries in RivenVFS"""
    __tablename__ = "FilesystemEntry"

    id: Mapped[int] = mapped_column(sqlalchemy.Integer, primary_key=True, autoincrement=True)

    # Discriminator for polymorphic identity (media, subtitle, etc.)
    entry_type: Mapped[str] = mapped_column(sqlalchemy.String, nullable=False)

    # Common fields for all VFS entries
    path: Mapped[str] = mapped_column(sqlalchemy.String, nullable=False, index=True)  # virtual path in VFS

    # File size in bytes (for media files, this is the video size; for subtitles, this is the subtitle file size)
    file_size: Mapped[int] = mapped_column(sqlalchemy.BigInteger, nullable=False, default=0)

    # Whether this entry represents a directory (only applicable to MediaEntry)
    is_directory: Mapped[bool] = mapped_column(sqlalchemy.Boolean, nullable=False, default=False)

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

    __mapper_args__ = {
        "polymorphic_identity": "base",
        "polymorphic_on": "entry_type",
    }

    __table_args__ = (
        sqlalchemy.UniqueConstraint('path', name='uq_filesystem_entry_path'),
        sqlalchemy.Index('ix_filesystem_entry_path', 'path'),
        sqlalchemy.Index('ix_filesystem_entry_type', 'entry_type'),
        sqlalchemy.Index('ix_filesystem_entry_media_item_id', 'media_item_id'),
        sqlalchemy.Index('ix_filesystem_entry_created_at', 'created_at'),
    )

    def __repr__(self):
        return f"<FilesystemEntry(id={self.id}, type='{self.entry_type}', path='{self.path}')>"

    def to_dict(self) -> dict:
        """
        Provide a dictionary representation of the FilesystemEntry.

        Returns:
            dict: Base fields common to all entry types.
        """
        return {
            "id": self.id,
            "entry_type": self.entry_type,
            "path": self.path,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "available_in_vfs": self.available_in_vfs,
            "media_item_id": self.media_item_id,
        }

# ============================================================================
# SQLAlchemy Event Listener for Automatic VFS Cleanup
# ============================================================================

from sqlalchemy import event
from loguru import logger

def cleanup_vfs_on_filesystem_entry_delete(mapper, connection, target: FilesystemEntry):
    """
    Invalidate Riven VFS caches for a FilesystemEntry that is being deleted.

    When invoked as a SQLAlchemy before_delete listener, removes the node from the VFS tree
    and invalidates FUSE caches for the entry and parent directories.

    Parameters:
        target (FilesystemEntry): The FilesystemEntry instance being deleted; its path is used to locate and invalidate VFS caches.
    """
    try:
        from program.program import riven
        from program.services.filesystem import FilesystemService

        filesystem_service: FilesystemService = riven.services.get(FilesystemService)
        if filesystem_service and filesystem_service.riven_vfs and target.path:
            vfs = filesystem_service.riven_vfs
            path = vfs._normalize_path(target.path)

            # Get node from tree to get inode before removal
            node = vfs._get_node_by_path(path)
            ino = node.inode if node else None

            # Remove node from VFS tree
            if node:
                vfs._remove_node(path)

            # Invalidate FUSE cache for the removed entry
            vfs._invalidate_removed_entry_cache(path, ino)
            # Also attempt to invalidate parent directories that may have been pruned
            vfs._invalidate_potentially_removed_dirs(path)
    except Exception as e:
        logger.warning(f"Error invalidating VFS caches for {target.path}: {e}")


# Register event listener
event.listen(FilesystemEntry, "before_delete", cleanup_vfs_on_filesystem_entry_delete)
