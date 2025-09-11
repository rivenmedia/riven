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
    original_folder: Mapped[Optional[str]] = mapped_column(sqlalchemy.String, nullable=True)  # Original folder name from source

    # Restricted URL provided by the debrid service (e.g., RD /d/<id>)
    download_url: Mapped[Optional[str]] = mapped_column(sqlalchemy.String, nullable=True)
    # Persisted unrestricted (direct) URL for fast reads; refreshed on failures
    unrestricted_url: Mapped[Optional[str]] = mapped_column(sqlalchemy.String, nullable=True)

    provider: Mapped[Optional[str]] = mapped_column(sqlalchemy.String, nullable=True)
    provider_download_id: Mapped[Optional[str]] = mapped_column(sqlalchemy.String, nullable=True)

    # Availability flag: set to True once added to the VFS
    available_in_vfs: Mapped[bool] = mapped_column(sqlalchemy.Boolean, default=False, nullable=False)

    # Relationship to MediaItem
    media_items: Mapped[list["MediaItem"]] = relationship(
        "MediaItem",
        back_populates="filesystem_entry",
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

    def get_original_folder(self) -> str:
        """Get the original folder name, falling back to path parent if not set"""
        if self.original_folder:
            return self.original_folder
        # Fallback to extracting from path
        import os
        return os.path.basename(os.path.dirname(self.path))



    @classmethod
    def create_virtual_entry(cls, path: str, download_url: str, provider: str,
                           provider_download_id: str, file_size: int = 0,
                           original_filename: str = None, original_folder: str = None) -> "FilesystemEntry":
        """Create a virtual file filesystem entry"""
        return cls(
            path=path,
            download_url=download_url,
            provider=provider,
            provider_download_id=provider_download_id,
            file_size=file_size,
            original_filename=original_filename,
            original_folder=original_folder
        )

    def to_dict(self) -> dict:
        """Convert to dictionary representation"""
        return {
            "id": self.id,
            "path": self.path,
            "file_size": self.file_size,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "download_url": self.download_url,
            "unrestricted_url": self.unrestricted_url,
            "provider": self.provider,
            "provider_download_id": self.provider_download_id,
            "available_in_vfs": self.available_in_vfs,
        }
