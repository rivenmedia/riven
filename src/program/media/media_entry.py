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
    # original_filename is the source of truth - all VFS paths are generated from this
    original_filename: Mapped[str] = mapped_column(
        sqlalchemy.String, nullable=False, index=True
    )

    # AIOStreams fields
    download_url: Mapped[Optional[str]] = mapped_column(
        sqlalchemy.String, nullable=True
    )  # Direct URL from AIOStreams
    unrestricted_url: Mapped[Optional[str]] = mapped_column(
        sqlalchemy.String, nullable=True
    )  # Kept for backward compatibility (same as download_url for AIOStreams)
    provider: Mapped[Optional[str]] = mapped_column(
        sqlalchemy.String, nullable=True
    )  # Which debrid service AIOStreams used (realdebrid, torbox, etc.)
    provider_download_id: Mapped[Optional[str]] = mapped_column(
        sqlalchemy.String, nullable=True
    )  # Infohash for re-scraping reference

    # Library Profile References (list of profile keys from settings.json)
    library_profiles: Mapped[Optional[list[str]]] = mapped_column(
        sqlalchemy.JSON,
        nullable=True,
        default=list,
        comment="List of library profile keys this entry matches (from settings.json)",
    )

    # Parsed filename data (cached to avoid re-parsing)
    # Stores PTT parse results: {item_type, season, episodes}
    parsed_data: Mapped[Optional[dict]] = mapped_column(
        sqlalchemy.JSON,
        nullable=True,
        comment="Cached parsed filename data from PTT (item_type, season, episodes)",
    )

    # Probed media data (cached to avoid re-probing)
    # Stores ffprobe results: {video, audio, subtitles, duration, etc.}
    probed_data: Mapped[Optional[dict]] = mapped_column(
        sqlalchemy.JSON,
        nullable=True,
        comment="Cached ffprobe media analysis data (video, audio, subtitles, etc.)",
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
        from program.settings.manager import settings_manager

        # Get the associated MediaItem
        item = self.media_item
        if not item:
            return []

        # Generate clean path structure from original_filename
        # This gives us the canonical structure: /movies/Title (Year)/Title.mkv or /shows/...
        # Pass cached parsed_data to avoid re-parsing
        canonical_path = generate_clean_path(
            item=item,
            original_filename=self.original_filename,
            file_size=self.file_size or 0,
            parsed_data=self.parsed_data,
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

                # Simplify path if profile only has one content type
                # e.g., /kids/Movie.mkv instead of /kids/movies/Movie.mkv
                filter_rules = profile.filter_rules
                content_types = filter_rules.content_types if filter_rules else None

                if content_types and len(content_types) == 1:
                    # Single content type - simplify path by removing /movies or /shows
                    if canonical_path.startswith("/movies/"):
                        simplified = canonical_path[8:]  # Remove "/movies/"
                    elif canonical_path.startswith("/shows/"):
                        simplified = canonical_path[7:]  # Remove "/shows/"
                    else:
                        simplified = canonical_path.lstrip("/")

                    profile_path = f"{profile.library_path}/{simplified}"
                else:
                    # Multiple content types - keep full path structure
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
        parsed_data: Optional[dict] = None,
    ) -> "MediaEntry":
        """
        Create a MediaEntry representing a virtual (RivenVFS) media file from AIOStreams.

        Parameters:
            original_filename (str): Original filename (source of truth).
            download_url (str): Direct URL from AIOStreams.
            provider (str): Which debrid service AIOStreams used (realdebrid, torbox, etc.).
            provider_download_id (str): Infohash for re-scraping reference.
            file_size (int): Size of the file in bytes; defaults to 0.
            parsed_data (dict, optional): Cached parsed filename data from PTT to avoid re-parsing.

        Returns:
            MediaEntry: A new MediaEntry instance populated with the provided values.
        """
        return cls(
            original_filename=original_filename,
            download_url=download_url,
            provider=provider,
            provider_download_id=provider_download_id,
            file_size=file_size,
            parsed_data=parsed_data,
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
                "original_filename": original filename (source of truth),
                "file_size": size in bytes,
                "is_directory": true if directory, false otherwise,
                "created_at": ISO 8601 timestamp or None,
                "updated_at": ISO 8601 timestamp or None,
                "download_url": direct URL from AIOStreams or None,
                "unrestricted_url": same as download_url (kept for backward compatibility) or None,
                "provider": which debrid service AIOStreams used (realdebrid, torbox, etc.) or None,
                "provider_download_id": infohash for re-scraping reference or None,
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
