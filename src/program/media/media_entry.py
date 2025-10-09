import sqlalchemy
from sqlalchemy.orm import Mapped, mapped_column
from typing import Optional

from program.media.filesystem_entry import FilesystemEntry


class MediaEntry(FilesystemEntry):
    """Model for media file entries (videos) in RivenVFS"""

    __tablename__ = "MediaEntry"

    id: Mapped[int] = mapped_column(
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey("FilesystemEntry.id", ondelete="CASCADE"),
        primary_key=True,
    )

    # Media-specific fields
    # Note: file_size and is_directory are inherited from FilesystemEntry base class
    original_filename: Mapped[Optional[str]] = mapped_column(
        sqlalchemy.String, nullable=True
    )

    # Debrid service fields
    download_url: Mapped[Optional[str]] = mapped_column(
        sqlalchemy.String, nullable=True
    )
    unrestricted_url: Mapped[Optional[str]] = mapped_column(
        sqlalchemy.String, nullable=True
    )
    provider: Mapped[Optional[str]] = mapped_column(sqlalchemy.String, nullable=True)
    provider_download_id: Mapped[Optional[str]] = mapped_column(
        sqlalchemy.String, nullable=True
    )

    __mapper_args__ = {
        "polymorphic_identity": "media",
    }

    __table_args__ = (sqlalchemy.Index("ix_media_entry_provider", "provider"),)

    def __repr__(self):
        return f"<MediaEntry(id={self.id}, path='{self.path}', size={self.file_size})>"

    def get_original_filename(self) -> str:
        """
        Return the original filename for the entry.

        Returns:
            str: The stored `original_filename` if present, otherwise the basename of `path`.
        """
        if self.original_filename:
            return self.original_filename
        # Fallback to extracting from path
        import os

        return os.path.basename(self.path)

    @classmethod
    def create_virtual_entry(
        cls,
        path: str,
        download_url: str | None,
        provider: str | None,
        provider_download_id: str | None,
        file_size: int = 0,
        original_filename: str | None = None,
    ) -> "MediaEntry":
        """
        Create a MediaEntry representing a virtual (RivenVFS) media file.

        Parameters:
            path (str): Virtual VFS path for the entry.
            download_url (str): Provider-restricted URL used to fetch the file.
            provider (str): Identifier of the provider that supplies the file.
            provider_download_id (str): Provider-specific download identifier.
            file_size (int): Size of the file in bytes; defaults to 0.
            original_filename (str | None): Original source filename, used as a fallback display name.

        Returns:
            MediaEntry: A new MediaEntry instance populated with the provided values.
        """
        return cls(
            path=path,
            download_url=download_url,
            provider=provider,
            provider_download_id=provider_download_id,
            file_size=file_size,
            original_filename=original_filename,
        )

    def to_dict(self) -> dict:
        """
        Provide a dictionary representation of the MediaEntry.

        The dictionary includes primary fields and metadata. `created_at` and `updated_at`
        are ISO 8601 formatted strings when present, otherwise `None`. Other keys map
        directly to the model's attributes.

        Returns:
            dict: {
                "id": entry id,
                "entry_type": "media",
                "path": virtual VFS path,
                "file_size": size in bytes,
                "is_directory": true if directory, false otherwise,
                "created_at": ISO 8601 timestamp or None,
                "updated_at": ISO 8601 timestamp or None,
                "original_filename": original filename or None,
                "download_url": restricted download URL or None,
                "unrestricted_url": persisted direct URL or None,
                "provider": provider identifier or None,
                "provider_download_id": provider download id or None,
                "available_in_vfs": true if available in VFS, false otherwise,
                "media_item_id": associated MediaItem ID or None
            }
        """
        base_dict = super().to_dict()
        base_dict.update(
            {
                "file_size": self.file_size,
                "is_directory": self.is_directory,
                "original_filename": self.original_filename,
                "download_url": self.download_url,
                "unrestricted_url": self.unrestricted_url,
                "provider": self.provider,
                "provider_download_id": self.provider_download_id,
            }
        )
        return base_dict
