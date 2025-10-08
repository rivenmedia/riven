"""
Stream models for Riven.

This module defines Stream and its relationship tables:
- Stream: Torrent stream discovered by scrapers
- StreamRelation: Many-to-many between MediaItem and Stream
- StreamBlacklistRelation: MediaItem-level stream blacklisting
- MediaEntryStreamBlacklistRelation: MediaEntry-level (profile-specific) stream blacklisting

Streams are shared across all scraping profiles at the MediaItem level.
Individual MediaEntry instances can blacklist streams independently per profile.
"""
from typing import TYPE_CHECKING, Optional

import sqlalchemy
from RTN import ParsedData, Torrent
from sqlalchemy import Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from program.db.db import db
from program.types import ParsedDataType

if TYPE_CHECKING:
    from program.media.item import MediaItem
    from program.media.media_entry import MediaEntry


class StreamRelation(db.Model):
    """
    Many-to-many relationship between MediaItem and Stream.

    Links discovered streams to the items they can fulfill (movies, shows, seasons, episodes).
    """
    __tablename__ = "StreamRelation"

    id: Mapped[int] = mapped_column(sqlalchemy.Integer, primary_key=True)
    parent_id: Mapped[int] = mapped_column(sqlalchemy.ForeignKey("MediaItem.id", ondelete="CASCADE"))
    child_id: Mapped[int] = mapped_column(sqlalchemy.ForeignKey("Stream.id", ondelete="CASCADE"))

    __table_args__ = (
        Index("ix_streamrelation_parent_id", "parent_id"),
        Index("ix_streamrelation_child_id", "child_id"),
    )

class StreamBlacklistRelation(db.Model):
    """
    MediaItem-level stream blacklisting.

    Tracks streams that failed for a MediaItem and should be avoided across all profiles.
    """
    __tablename__ = "StreamBlacklistRelation"

    id: Mapped[int] = mapped_column(sqlalchemy.Integer, primary_key=True)
    media_item_id: Mapped[int] = mapped_column(sqlalchemy.ForeignKey("MediaItem.id", ondelete="CASCADE"))
    stream_id: Mapped[int] = mapped_column(sqlalchemy.ForeignKey("Stream.id", ondelete="CASCADE"))

    __table_args__ = (
        Index("ix_streamblacklistrelation_media_item_id", "media_item_id"),
        Index("ix_streamblacklistrelation_stream_id", "stream_id"),
    )

class MediaEntryStreamBlacklistRelation(db.Model):
    """
    MediaEntry-level (profile-specific) stream blacklisting.

    Tracks streams that failed for a specific MediaEntry/profile combination.
    Allows different profiles to try different streams independently.
    """
    __tablename__ = "MediaEntryStreamBlacklistRelation"

    id: Mapped[int] = mapped_column(sqlalchemy.Integer, primary_key=True)
    media_entry_id: Mapped[int] = mapped_column(sqlalchemy.ForeignKey("MediaEntry.id", ondelete="CASCADE"))
    stream_id: Mapped[int] = mapped_column(sqlalchemy.ForeignKey("Stream.id", ondelete="CASCADE"))

    __table_args__ = (
        Index("ix_mediaentrystreamblacklistrelation_media_entry_id", "media_entry_id"),
        Index("ix_mediaentrystreamblacklistrelation_stream_id", "stream_id"),
    )

class Stream(db.Model):
    """
    Torrent stream discovered by scrapers.

    Represents a torrent that can fulfill a MediaItem's download requirements.
    Contains parsed metadata from RTN (resolution, codec, quality, etc.) and
    ranking information for stream selection.

    Attributes:
        id: Primary key.
        infohash: Torrent infohash (unique identifier).
        raw_title: Original torrent title from scraper.
        parsed_title: Cleaned/parsed title from RTN.
        rank: Ranking score from RTN (higher = better match).
        lev_ratio: Levenshtein ratio for title matching.
        resolution: Video resolution (e.g., "1080p", "4k").
        parsed_data: Full RTN ParsedData with detailed metadata.
        parents: MediaItems that can use this stream.
        blacklisted_parents: MediaItems that blacklisted this stream.
        blacklisted_media_entries: MediaEntries that blacklisted this stream.
    """
    __tablename__ = "Stream"

    id: Mapped[int] = mapped_column(sqlalchemy.Integer, primary_key=True)
    infohash: Mapped[str] = mapped_column(sqlalchemy.String, nullable=False)
    raw_title: Mapped[str] = mapped_column(sqlalchemy.String, nullable=False)
    parsed_title: Mapped[str] = mapped_column(sqlalchemy.String, nullable=False)
    rank: Mapped[int] = mapped_column(sqlalchemy.Integer, nullable=False)
    lev_ratio: Mapped[float] = mapped_column(sqlalchemy.Float, nullable=False)
    resolution: Mapped[Optional[str]] = mapped_column(sqlalchemy.String, nullable=True)
    parsed_data: Mapped[Optional[ParsedData]] = mapped_column(ParsedDataType, nullable=True)

    parents: Mapped[list["MediaItem"]] = relationship(secondary="StreamRelation", back_populates="streams", lazy="selectin")
    blacklisted_parents: Mapped[list["MediaItem"]] = relationship(secondary="StreamBlacklistRelation", back_populates="blacklisted_streams", lazy="selectin")
    blacklisted_media_entries: Mapped[list["MediaEntry"]] = relationship(secondary="MediaEntryStreamBlacklistRelation", back_populates="blacklisted_streams", lazy="selectin")

    __table_args__ = (
        Index("ix_stream_infohash", "infohash"),
        Index("ix_stream_raw_title", "raw_title"),
        Index("ix_stream_parsed_title", "parsed_title"),
        Index("ix_stream_rank", "rank"),
        Index("ix_stream_resolution", "resolution"),
    )

    def __init__(self, torrent: Torrent):
        """
        Initialize a Stream from an RTN Torrent object.

        Args:
            torrent: RTN Torrent object containing parsed metadata.
        """
        self.raw_title = torrent.raw_title
        self.infohash = torrent.infohash
        self.parsed_title = torrent.data.parsed_title
        self.parsed_data = torrent.data  # Store ParsedData directly
        self.rank = torrent.rank
        self.lev_ratio = torrent.lev_ratio
        self.resolution = torrent.data.resolution.lower() if torrent.data.resolution else "unknown"

    def __hash__(self):
        """Hash based on infohash for use in sets/dicts."""
        return hash(self.infohash)

    def __eq__(self, other):
        """
        Check equality based on infohash.

        Args:
            other: Object to compare with.

        Returns:
            bool: True if both are Streams with same infohash, False otherwise.
        """
        return isinstance(other, Stream) and self.infohash == other.infohash

    def to_dict(self):
        """
        Convert stream to dictionary for API serialization.

        Returns:
            dict: Stream data without full parsed_data (use parsed_data field for details).
        """
        return {
            "id": self.id,
            "infohash": self.infohash,
            "raw_title": self.raw_title,
            "parsed_title": self.parsed_title,
            "rank": self.rank,
            "lev_ratio": self.lev_ratio,
            "resolution": self.resolution,
        }