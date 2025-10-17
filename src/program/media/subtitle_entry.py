"""Model for subtitle entries"""

from typing import Optional, TYPE_CHECKING

import sqlalchemy
from sqlalchemy.orm import Mapped, mapped_column

from program.media.filesystem_entry import FilesystemEntry

if TYPE_CHECKING:
    from program.media.item import MediaItem


class SubtitleEntry(FilesystemEntry):
    """Model for subtitle entries in RivenVFS"""

    __tablename__ = "SubtitleEntry"

    id: Mapped[int] = mapped_column(
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey("FilesystemEntry.id", ondelete="CASCADE"),
        primary_key=True,
    )

    # Subtitle-specific fields
    # Note: file_size (inherited from FilesystemEntry) represents the subtitle file size
    # Note: is_directory (inherited from FilesystemEntry) is always False for subtitles

    # ISO 639-3 language code (e.g., 'eng', 'spa', 'fra')
    language: Mapped[str] = mapped_column(sqlalchemy.String, nullable=False, index=True)

    # Original filename of the parent MediaEntry (video file)
    # Used to generate subtitle paths dynamically alongside the video
    parent_original_filename: Mapped[Optional[str]] = mapped_column(
        sqlalchemy.String,
        nullable=True,
        index=True,
        comment="Original filename of the parent MediaEntry (video file)",
    )

    # Subtitle content stored directly in database (SRT format)
    content: Mapped[Optional[str]] = mapped_column(sqlalchemy.Text, nullable=True)

    # OpenSubtitles hash of the video file this subtitle is for
    file_hash: Mapped[Optional[str]] = mapped_column(
        sqlalchemy.String, nullable=True, index=True
    )

    # Size of the VIDEO file (needed for OpenSubtitles API, not the subtitle file size)
    video_file_size: Mapped[Optional[int]] = mapped_column(
        sqlalchemy.BigInteger, nullable=True
    )

    # OpenSubtitles subtitle ID for tracking
    opensubtitles_id: Mapped[Optional[str]] = mapped_column(
        sqlalchemy.String, nullable=True, index=True
    )

    __mapper_args__ = {
        "polymorphic_identity": "subtitle",
    }

    __table_args__ = (
        sqlalchemy.Index("ix_subtitle_entry_language", "language"),
        sqlalchemy.Index(
            "ix_subtitle_entry_parent_original_filename", "parent_original_filename"
        ),
        sqlalchemy.Index("ix_subtitle_entry_file_hash", "file_hash"),
        sqlalchemy.Index("ix_subtitle_entry_opensubtitles_id", "opensubtitles_id"),
    )

    def __repr__(self):
        return f"<SubtitleEntry(id={self.id}, language='{self.language}', parent='{self.parent_original_filename}')>"

    def to_dict(self) -> dict:
        """
        Serialize the SubtitleEntry ORM instance into a plain dictionary.

        Returns:
            dict: A mapping with keys:
                - "id": integer primary key of the subtitle.
                - "entry_type": "subtitle"
                - "file_size": size of the subtitle file in bytes (inherited from base).
                - "language": ISO 639-3 language code.
                - "parent_original_filename": original filename of parent video file.
                - "content": subtitle content (SRT format) or None.
                - "file_hash": OpenSubtitles hash of the video file or None.
                - "video_file_size": size of the video file in bytes or None.
                - "opensubtitles_id": OpenSubtitles subtitle ID or None.
                - "created_at": ISO 8601 timestamp or None.
                - "updated_at": ISO 8601 timestamp or None.
                - "available_in_vfs": true if available in VFS, false otherwise.
                - "media_item_id": the associated MediaItem primary key or None.
        """
        base_dict = super().to_dict()
        base_dict.update(
            {
                "language": self.language,
                "parent_original_filename": self.parent_original_filename,
                "file_hash": self.file_hash,
                "video_file_size": self.video_file_size,
                "opensubtitles_id": self.opensubtitles_id,
            }
        )
        return base_dict

    @classmethod
    def create_subtitle_entry(
        cls,
        language: str,
        parent_original_filename: str,
        content: str = None,
        file_hash: str = None,
        video_file_size: int = None,
        opensubtitles_id: str = None,
        subtitle_file_size: int = None,
    ) -> "SubtitleEntry":
        """
        Create a SubtitleEntry for a virtual subtitle file in RivenVFS.

        In the new architecture, subtitles don't have a fixed path. Instead, they reference
        their parent video's original_filename, and RivenVFS generates subtitle paths
        dynamically alongside the video file.

        Parameters:
            language (str): ISO 639-3 language code (e.g., 'eng', 'spa', 'fra').
            parent_original_filename (str): Original filename of the parent MediaEntry (video file).
            content (str | None): Subtitle content in SRT format.
            file_hash (str | None): OpenSubtitles hash of the video file.
            video_file_size (int | None): Size of the VIDEO file in bytes (for OpenSubtitles API).
            opensubtitles_id (str | None): OpenSubtitles subtitle ID for tracking.
            subtitle_file_size (int | None): Size of the subtitle file itself in bytes.

        Returns:
            SubtitleEntry: A new SubtitleEntry instance populated with the provided values.
        """
        # Calculate subtitle file size from content if not provided
        if subtitle_file_size is None and content:
            subtitle_file_size = len(content.encode("utf-8"))

        return cls(
            language=language,
            parent_original_filename=parent_original_filename,
            content=content,
            file_hash=file_hash,
            video_file_size=video_file_size,
            opensubtitles_id=opensubtitles_id,
            file_size=subtitle_file_size or 0,  # Set the base class file_size
        )
