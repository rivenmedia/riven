"""Model for filesystem entries"""

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional

import sqlalchemy
from sqlalchemy.orm import Mapped, mapped_column, relationship

from program.db.db import db

if TYPE_CHECKING:
    from program.media.item import MediaItem


class FilesystemEntry(db.Model):
    """Base model for all virtual filesystem entries in RivenVFS"""

    __tablename__ = "FilesystemEntry"

    id: Mapped[int] = mapped_column(
        sqlalchemy.Integer, primary_key=True, autoincrement=True
    )

    # Discriminator for polymorphic identity (media, subtitle, etc.)
    entry_type: Mapped[str] = mapped_column(sqlalchemy.String, nullable=False)

    # File size in bytes (for media files, this is the video size; for subtitles, this is the subtitle file size)
    file_size: Mapped[int] = mapped_column(
        sqlalchemy.BigInteger, nullable=False, default=0
    )

    # Whether this entry represents a directory (only applicable to MediaEntry)
    is_directory: Mapped[bool] = mapped_column(
        sqlalchemy.Boolean, nullable=False, default=False
    )

    created_at: Mapped[datetime] = mapped_column(
        sqlalchemy.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        sqlalchemy.DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Availability flag: set to True once added to the VFS
    available_in_vfs: Mapped[bool] = mapped_column(
        sqlalchemy.Boolean, default=False, nullable=False
    )

    # Foreign key to MediaItem (many FilesystemEntries can belong to one MediaItem)
    media_item_id: Mapped[Optional[int]] = mapped_column(
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey("MediaItem.id", ondelete="CASCADE"),
        nullable=True,
    )

    # Many-to-one relationship: many FilesystemEntries belong to one MediaItem
    media_item: Mapped[Optional["MediaItem"]] = relationship(
        "MediaItem", back_populates="filesystem_entries", lazy="selectin"
    )

    __mapper_args__ = {
        "polymorphic_identity": "base",
        "polymorphic_on": "entry_type",
    }

    __table_args__ = (
        sqlalchemy.Index("ix_filesystem_entry_type", "entry_type"),
        sqlalchemy.Index("ix_filesystem_entry_media_item_id", "media_item_id"),
        sqlalchemy.Index("ix_filesystem_entry_created_at", "created_at"),
    )

    def __repr__(self):
        return f"<FilesystemEntry(id={self.id}, type='{self.entry_type}')>"

    def to_dict(self) -> dict:
        """
        Provide a dictionary representation of the FilesystemEntry.

        Returns:
            dict: Base fields common to all entry types.
        """
        return {
            "id": self.id,
            "entry_type": self.entry_type,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "available_in_vfs": self.available_in_vfs,
            "media_item_id": self.media_item_id,
        }
