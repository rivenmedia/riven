"""
MediaEntry model for Riven.

This module defines MediaEntry, which represents a single downloaded/processed
version of a MediaItem. One MediaItem can have multiple MediaEntry instances
(one per scraping profile), enabling multi-profile downloads with different
quality settings.

MediaEntry extends FilesystemEntry and adds download-specific metadata:
- Scraping profile reference
- Debrid service information (download URLs, provider)
- Stream selection (active_stream)
- Parsed torrent metadata (RTN ParsedData)
- FFprobe analysis results (RTN MediaMetadata)
- Subtitles relationship
- Per-profile stream blacklisting
"""
import sqlalchemy
from sqlalchemy.orm import Mapped, mapped_column, relationship
from typing import Optional, TYPE_CHECKING, Dict, Any

from RTN import ParsedData
from RTN.file_parser import MediaMetadata

from program.media.filesystem_entry import FilesystemEntry
from program.media.entry_state import EntryState
from program.types import ParsedDataType, MediaMetadataType

if TYPE_CHECKING:
    from program.media.subtitle_entry import SubtitleEntry
    from program.media.stream import Stream


class MediaEntry(FilesystemEntry):
    """
    Model for media file entries (videos) in RivenVFS.

    Represents a single downloaded/processed version of a MediaItem.
    One MediaItem can have multiple MediaEntry instances (one per scraping profile).

    Attributes:
        id: Primary key (inherits from FilesystemEntry).
        scraping_profile_name: Name of the scraping profile (references settings.json).
        original_filename: Original filename from torrent/debrid service.
        download_url: Restricted download URL from debrid service.
        unrestricted_url: Unrestricted URL for direct access (cached after first use).
        provider: Debrid provider name (e.g., "realdebrid", "torbox").
        provider_download_id: Provider-specific download ID.
        active_stream: Currently selected stream for this entry (JSON dict).
        failed: Whether download/processing failed (requires manual intervention).
        updated: Whether entry has been checked for updates by Updater service.
        notified: Whether notification has been sent for this entry.
        parsed: Parsed torrent metadata (RTN ParsedData) - resolution, codec, quality, etc.
        probed: FFprobe analysis results (RTN MediaMetadata) - duration, tracks, etc.
        subtitles: List of SubtitleEntry instances for this media file.
        blacklisted_streams: Streams blacklisted for this specific profile.

    Inherited from FilesystemEntry:
        path: Virtual path in VFS.
        file_size: Size in bytes.
        is_directory: Whether this is a directory (for show packs).
        created_at: Creation timestamp.
        updated_at: Last update timestamp.
        available_in_vfs: Whether available in RivenVFS.
        media_item_id: Foreign key to parent MediaItem.
        media_item: Relationship to parent MediaItem.
    """

    __tablename__ = "MediaEntry"

    id: Mapped[int] = mapped_column(
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey("FilesystemEntry.id", ondelete="CASCADE"),
        primary_key=True,
    )

    # Scraping Profile Reference (stored as name, references settings.json)
    scraping_profile_name: Mapped[str] = mapped_column(
        sqlalchemy.String,
        nullable=False,
        default="Default Quality"
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

    # Download/Processing Metadata (moved from MediaItem)
    # These are specific to this downloaded version
    active_stream: Mapped[Optional[dict]] = mapped_column(
        sqlalchemy.JSON, nullable=True
    )  # Current selected stream for this entry

    # Failure tracking for state determination
    failed: Mapped[bool] = mapped_column(
        sqlalchemy.Boolean, default=False, nullable=False
    )  # True if download/processing failed

    # Update tracking for state determination
    updated: Mapped[bool] = mapped_column(
        sqlalchemy.Boolean, default=False, nullable=False
    )  # True if entry has been checked for updates

    # Notification tracking to prevent duplicate notifications
    notified: Mapped[bool] = mapped_column(
        sqlalchemy.Boolean, default=False, nullable=False
    )

    parsed: Mapped[Optional[ParsedData]] = mapped_column(
        ParsedDataType, nullable=True
    )

    probed: Mapped[Optional[MediaMetadata]] = mapped_column(
        MediaMetadataType, nullable=True
    )

    subtitles: Mapped[list["SubtitleEntry"]] = relationship(
        "SubtitleEntry",
        back_populates="media_entry",
        foreign_keys="[SubtitleEntry.media_entry_id]",
        lazy="selectin",
        cascade="all, delete-orphan"
    )

    # Blacklisted streams for this specific MediaEntry/profile
    blacklisted_streams: Mapped[list["Stream"]] = relationship(
        secondary="MediaEntryStreamBlacklistRelation",
        back_populates="blacklisted_media_entries",
        lazy="selectin",
        cascade="all"
    )

    __mapper_args__ = {
        "polymorphic_identity": "media",
    }

    __table_args__ = (
        sqlalchemy.Index("ix_media_entry_provider", "provider"),
        sqlalchemy.Index("ix_media_entry_scraping_profile", "scraping_profile_name"),
    )

    @property
    def state(self) -> EntryState:
        """
        Computed property that determines the current state based on attributes.

        State transitions:
        - Pending: No active_stream yet
        - Downloading: Has active_stream but no download_url
        - Downloaded: Has download_url and file_size but not in VFS
        - Available: In VFS (available_in_vfs = True)
        - Completed: Processed by updater (updated = True on parent MediaItem)

        Returns:
            EntryState: The current state
        """
        return self._determine_state()

    def _determine_state(self) -> EntryState:
        """
        Determine the current state of this MediaEntry based on its attributes.

        Similar to MediaItem._determine_state(), but for entry-specific lifecycle.

        State determination logic:
        1. If failed flag is set → Failed
        2. If updated flag is set → Completed
        3. If available_in_vfs → Available
        4. If has download_url and file_size → Downloaded
        5. If has active_stream → Downloading
        6. Otherwise → Pending
        """
        # Check for explicit failure first
        if self.failed:
            return EntryState.Failed

        # If updated, it's Completed
        if self.updated:
            return EntryState.Completed

        # If available in VFS, it's Available
        if self.available_in_vfs:
            return EntryState.Available

        # If we have download_url and file_size, it's Downloaded
        if self.download_url and self.file_size > 0:
            return EntryState.Downloaded

        # If we have active_stream but no download yet, it's Downloading
        if self.active_stream:
            return EntryState.Downloading

        # Otherwise it's Pending (waiting to be processed)
        return EntryState.Pending

    def get_stream_for_ranking(self) -> Optional[Dict[str, Any]]:
        """
        Get the stream data from this entry for ranking purposes.

        Returns the active_stream dict which contains infohash and can be
        used to find the corresponding Stream object for ranking.

        Returns:
            Optional[Dict]: The active_stream dict with infohash, or None
        """
        return self.active_stream if self.active_stream else None

    def blacklist_stream(self, stream: "Stream") -> bool:
        """
        Blacklist a stream for this specific MediaEntry/profile.

        Args:
            stream: The stream to blacklist

        Returns:
            bool: True if stream was blacklisted, False if already blacklisted
        """
        if stream not in self.blacklisted_streams:
            self.blacklisted_streams.append(stream)
            from loguru import logger
            logger.debug(f"Blacklisted stream {stream.infohash} for MediaEntry {self.id} (profile: '{self.scraping_profile_name}')")
            return True
        return False

    def unblacklist_stream(self, stream: "Stream") -> bool:
        """
        Remove a stream from the blacklist for this MediaEntry/profile.

        Args:
            stream: The stream to unblacklist

        Returns:
            bool: True if stream was unblacklisted, False if not in blacklist
        """
        if stream in self.blacklisted_streams:
            self.blacklisted_streams.remove(stream)
            from loguru import logger
            logger.debug(f"Unblacklisted stream {stream.infohash} for MediaEntry {self.id} (profile: '{self.scraping_profile_name}')")
            return True
        return False

    def is_stream_blacklisted(self, stream: "Stream") -> bool:
        """
        Check if a stream is blacklisted for this MediaEntry/profile.

        Args:
            stream: The stream to check

        Returns:
            bool: True if stream is blacklisted
        """
        return stream in self.blacklisted_streams

    def __repr__(self):
        """String representation of the MediaEntry."""
        return f"<MediaEntry(id={self.id}, path='{self.path}', size={self.file_size})>"

    def get_original_filename(self) -> str:
        """
        Get the original filename for this entry.

        Returns:
            str: The stored original_filename if present, otherwise basename of path.
        """
        if self.original_filename:
            return self.original_filename
        # Fallback to extracting from path
        import os

        return os.path.basename(self.path)

    @property
    def log_string(self) -> str:
        """
        Generate a human-readable log string for this MediaEntry.

        Format: "{MediaItem.log_string} [Profile: {profile_name}] (Entry ID: {id})"

        Returns:
            str: A formatted string for logging
        """
        item_log = self.media_item.log_string if self.media_item else "Unknown Item"
        profile = self.scraping_profile_name or "Unknown Profile"
        entry_id = self.id if self.id else "Unsaved"
        return f"{item_log} [Profile: {profile}] (Entry ID: {entry_id})"

    @classmethod
    def create_virtual_entry(
        cls,
        path: str,
        download_url: str,
        provider: str,
        provider_download_id: str,
        file_size: int = 0,
        original_filename: str = None,
        scraping_profile_name: str = "Default Quality",
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
            scraping_profile_name (str): Name of the scraping profile used for this entry.

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
            scraping_profile_name=scraping_profile_name,
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
                "scraping_profile_name": scraping profile name,
                "original_filename": original filename or None,
                "download_url": restricted download URL or None,
                "unrestricted_url": persisted direct URL or None,
                "provider": provider identifier or None,
                "provider_download_id": provider download id or None,
                "active_stream": active stream dict or None,
                "parsed": parsed data dict or None,
                "probed": probed data dict or None,
                "available_in_vfs": true if available in VFS, false otherwise,
                "media_item_id": associated MediaItem ID or None,
                "subtitles": list of subtitle dicts
            }
        """
        base_dict = super().to_dict()
        base_dict.update(
            {
                "file_size": self.file_size,
                "is_directory": self.is_directory,
                "scraping_profile_name": self.scraping_profile_name,
                "original_filename": self.original_filename,
                "download_url": self.download_url,
                "unrestricted_url": self.unrestricted_url,
                "provider": self.provider,
                "provider_download_id": self.provider_download_id,
                "active_stream": self.active_stream,
                "state": self.state.value if self.state else EntryState.Unknown.value,
                "parsed": self.parsed.model_dump() if self.parsed else None,
                "probed": self.probed.model_dump() if self.probed else None,
                "subtitles": [subtitle.to_dict() for subtitle in self.subtitles] if hasattr(self, "subtitles") and self.subtitles else [],
            }
        )
        return base_dict
