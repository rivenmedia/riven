from typing import TYPE_CHECKING

import sqlalchemy
from RTN import Torrent
from sqlalchemy import Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from program.db.db import db

if TYPE_CHECKING:
    from program.media.item import MediaItem


class StreamRelation(db.Model):
    __tablename__ = "StreamRelation"

    id: Mapped[int] = mapped_column(sqlalchemy.Integer, primary_key=True)
    parent_id: Mapped[str] = mapped_column(sqlalchemy.ForeignKey("MediaItem.id", ondelete="CASCADE"))
    child_id: Mapped[int] = mapped_column(sqlalchemy.ForeignKey("Stream.id", ondelete="CASCADE"))

    __table_args__ = (
        Index("ix_streamrelation_parent_id", "parent_id"),
        Index("ix_streamrelation_child_id", "child_id"),
        # Composite index for efficient lookups of parent-child pairs
        Index("ix_streamrelation_parent_child", "parent_id", "child_id", unique=True),
    )

class StreamBlacklistRelation(db.Model):
    __tablename__ = "StreamBlacklistRelation"

    id: Mapped[int] = mapped_column(sqlalchemy.Integer, primary_key=True)
    media_item_id: Mapped[str] = mapped_column(sqlalchemy.ForeignKey("MediaItem.id", ondelete="CASCADE"))
    stream_id: Mapped[int] = mapped_column(sqlalchemy.ForeignKey("Stream.id", ondelete="CASCADE"))

    __table_args__ = (
        Index("ix_streamblacklistrelation_media_item_id", "media_item_id"),
        Index("ix_streamblacklistrelation_stream_id", "stream_id"),
        # Composite index for efficient lookups of media_item-stream pairs
        Index("ix_streamblacklistrelation_item_stream", "media_item_id", "stream_id", unique=True),
    )

class Stream(db.Model):
    __tablename__ = "Stream"

    id: Mapped[int] = mapped_column(sqlalchemy.Integer, primary_key=True)
    infohash: Mapped[str] = mapped_column(sqlalchemy.String, nullable=False)
    raw_title: Mapped[str] = mapped_column(sqlalchemy.String, nullable=False)
    parsed_title: Mapped[str] = mapped_column(sqlalchemy.String, nullable=False)
    parsed_data: Mapped[dict] = mapped_column(sqlalchemy.JSON, nullable=True)  # Store parsed torrent data
    rank: Mapped[int] = mapped_column(sqlalchemy.Integer, nullable=False)
    lev_ratio: Mapped[float] = mapped_column(sqlalchemy.Float, nullable=False)

    parents: Mapped[list["MediaItem"]] = relationship(secondary="StreamRelation", back_populates="streams", lazy="selectin")
    blacklisted_parents: Mapped[list["MediaItem"]] = relationship(secondary="StreamBlacklistRelation", back_populates="blacklisted_streams", lazy="selectin")

    __table_args__ = (
        Index("ix_stream_infohash", "infohash", unique=True),  # Infohash should be unique
        Index("ix_stream_raw_title", "raw_title"),
        Index("ix_stream_parsed_title", "parsed_title"),
        Index("ix_stream_rank", "rank"),
        # Composite index for sorting streams by rank within infohash queries
        Index("ix_stream_infohash_rank", "infohash", "rank"),
    )

    def __init__(self, torrent: Torrent):
        self.raw_title = torrent.raw_title
        self.infohash = torrent.infohash
        self.parsed_title = torrent.data.parsed_title
        # Safely serialize parsed data
        try:
            self.parsed_data = self._serialize_parsed_data(torrent.data)
        except Exception as e:
            # If serialization fails, store None and log the error
            from loguru import logger
            logger.debug(f"Failed to serialize parsed data for {torrent.infohash}: {e}")
            self.parsed_data = None
        self.rank = torrent.rank
        self.lev_ratio = torrent.lev_ratio

    def _serialize_parsed_data(self, parsed_data) -> dict:
        """Convert ParsedData object to JSON-serializable dictionary."""
        try:
            # Convert ParsedData object to dictionary
            if hasattr(parsed_data, '__dict__'):
                data_dict = {}
                for key, value in parsed_data.__dict__.items():
                    # Handle different types of values
                    if isinstance(value, (str, int, float, bool, type(None))):
                        data_dict[key] = value
                    elif isinstance(value, (list, tuple)):
                        # Convert lists/tuples to lists of serializable items
                        data_dict[key] = [str(item) for item in value]
                    elif hasattr(value, '__dict__'):
                        # Nested objects - convert to string representation
                        data_dict[key] = str(value)
                    else:
                        # Fallback to string representation
                        data_dict[key] = str(value)
                return data_dict
            else:
                # Fallback: convert entire object to string
                return {"raw_data": str(parsed_data)}
        except Exception as e:
            # If serialization fails, store minimal info
            return {
                "error": f"Serialization failed: {str(e)}",
                "type": str(type(parsed_data)),
                "raw_data": str(parsed_data)[:500]  # Truncate to avoid huge strings
            }

    def __hash__(self):
        return hash(self.infohash)

    def __eq__(self, other):
        return isinstance(other, Stream) and self.infohash == other.infohash