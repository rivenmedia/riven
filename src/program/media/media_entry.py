import sqlalchemy

from typing import Any
from sqlalchemy.types import TypeDecorator
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.engine import Dialect

from program.media.filesystem_entry import FilesystemEntry
from program.media.models import MediaMetadata


class MediaMetadataDecorator(TypeDecorator[MediaMetadata]):
    """Custom SQLAlchemy type decorator for MediaMetadata JSON serialization"""

    impl = sqlalchemy.JSON
    cache_ok = True

    def process_bind_param(self, value: MediaMetadata | None, dialect: Dialect):
        if value is None:
            return None

        return value.model_dump()

    def process_result_value(self, value: dict[str, Any] | None, dialect: Dialect):
        if value is None:
            return None

        return MediaMetadata.model_validate(value)


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
    # original_filename is the source of truth - all VFS paths are generated from this
    original_filename: Mapped[str] = mapped_column(
        sqlalchemy.String, nullable=False, index=True
    )

    # Debrid service fields
    download_url: Mapped[str | None]
    unrestricted_url: Mapped[str | None]
    provider: Mapped[str | None]
    provider_download_id: Mapped[str | None]

    # Library Profile References (list of profile keys from settings.json)
    library_profiles: Mapped[list[str] | None] = mapped_column(
        sqlalchemy.JSON,
        nullable=True,
        default=list,
        comment="List of library profile keys this entry matches (from settings.json)",
    )

    # Unified media metadata (combines parsed and probed data)
    # Stores MediaMetadata model: {video, audio_tracks, subtitle_tracks, quality_source, etc.}
    media_metadata: Mapped[MediaMetadata | None] = mapped_column(
        MediaMetadataDecorator,
        nullable=True,
        comment="Unified media metadata combining parsed (RTN) and probed (ffprobe) data",
    )

    __mapper_args__ = {
        "polymorphic_identity": "media",
    }

    __table_args__ = (
        sqlalchemy.Index("ix_media_entry_provider", "provider"),
        sqlalchemy.Index("ix_media_entry_original_filename", "original_filename"),
    )

    def __repr__(self):
        return f"<MediaEntry(id={self.id}, original_filename='{self.original_filename}', size={self.file_size})>"

    def get_original_filename(self) -> str:
        """
        Return the original filename for the entry.

        Returns:
            str: The stored `original_filename` (always present in new architecture).
        """
        return self.original_filename

    def get_all_vfs_paths(self) -> list[str]:
        """
        Generate all VFS paths for this entry.

        This is the single source of truth for path generation, used by both
        RivenVFS registration and Updater refresh logic.

        Every item ALWAYS appears in the base /movies or /shows path.
        Library profiles provide ADDITIONAL filtered views (e.g., /kids, /anime).

        Returns:
            List of VFS paths (e.g., ["/movies/Movie.mkv", "/kids/Movie.mkv"])
            Always includes at least the base path.
        """
        from program.services.filesystem.vfs.naming import generate_clean_path
        from program.settings import settings_manager

        # Get the associated MediaItem
        item = self.media_item

        if not item:
            return []

        # Generate clean path structure from original_filename
        # This gives us the canonical structure: /movies/Title (Year)/Title.mkv or /shows/...
        # Pass cached media_metadata to avoid re-parsing
        canonical_path = generate_clean_path(
            item=item,
            original_filename=self.original_filename,
        )

        # ALWAYS include the base path (/movies or /shows)
        # This is non-configurable and ensures every item is accessible
        all_paths = [canonical_path]

        # Add additional paths from library profiles (optional filtered views)
        if self.library_profiles:
            profiles = settings_manager.settings.filesystem.library_profiles

            for profile_key in self.library_profiles:
                if profile_key not in profiles:
                    continue

                profile = profiles[profile_key]

                # Always use full path structure with /movies or /shows
                # This ensures consistent directory structure across all library profiles
                # e.g., /kids/movies/Movie.mkv and /kids/shows/Show.mkv
                profile_path = f"{profile.library_path}{canonical_path}"

                all_paths.append(profile_path)

        return all_paths

    @classmethod
    def create_virtual_entry(
        cls,
        original_filename: str,
        download_url: str,
        provider: str,
        provider_download_id: str,
        file_size: int = 0,
        media_metadata: MediaMetadata | None = None,
    ) -> "MediaEntry":
        """
        Create a MediaEntry representing a virtual (RivenVFS) media file.

        Parameters:
            original_filename (str): Original filename from debrid provider (source of truth).
            download_url (str): Provider-restricted URL used to fetch the file.
            provider (str): Identifier of the provider that supplies the file.
            provider_download_id (str): Provider-specific download identifier.
            file_size (int): Size of the file in bytes; defaults to 0.
            media_metadata (dict, optional): Cached media metadata to avoid re-parsing/probing.

        Returns:
            MediaEntry: A new MediaEntry instance populated with the provided values.
        """
        return cls(
            original_filename=original_filename,
            download_url=download_url,
            provider=provider,
            provider_download_id=provider_download_id,
            file_size=file_size,
            media_metadata=media_metadata,
        )

    def to_dict(self) -> dict[str, int | str | bool | None]:
        """
        Provide a dictionary representation of the MediaEntry.

        The dictionary includes primary fields and metadata. `created_at` and `updated_at`
        are ISO 8601 formatted strings when present, otherwise `None`. Other keys map
        directly to the model's attributes.

        Returns:
            dict: {
                "id": entry id,
                "entry_type": "media",
                "original_filename": original filename (source of truth),
                "file_size": size in bytes,
                "is_directory": true if directory, false otherwise,
                "created_at": ISO 8601 timestamp or None,
                "updated_at": ISO 8601 timestamp or None,
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


# ============================================================================
# SQLAlchemy Event Listener for Automatic VFS Cleanup
# ============================================================================

# Note: VFS sync after FilesystemEntry deletion is handled manually in the code
# that performs the deletion (e.g., /remove endpoint, item.reset()) to ensure
# the sync happens AFTER the transaction is committed, not during the delete event.
