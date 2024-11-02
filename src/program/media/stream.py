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
    )

class StreamBlacklistRelation(db.Model):
    __tablename__ = "StreamBlacklistRelation"

    id: Mapped[int] = mapped_column(sqlalchemy.Integer, primary_key=True)
    media_item_id: Mapped[str] = mapped_column(sqlalchemy.ForeignKey("MediaItem.id", ondelete="CASCADE"))
    stream_id: Mapped[int] = mapped_column(sqlalchemy.ForeignKey("Stream.id", ondelete="CASCADE"))

    __table_args__ = (
        Index("ix_streamblacklistrelation_media_item_id", "media_item_id"),
        Index("ix_streamblacklistrelation_stream_id", "stream_id"),
    )

class Stream(db.Model):
    __tablename__ = "Stream"

    id: Mapped[int] = mapped_column(sqlalchemy.Integer, primary_key=True)
    infohash: Mapped[str] = mapped_column(sqlalchemy.String, nullable=False)
    raw_title: Mapped[str] = mapped_column(sqlalchemy.String, nullable=False)
    parsed_title: Mapped[str] = mapped_column(sqlalchemy.String, nullable=False)
    rank: Mapped[int] = mapped_column(sqlalchemy.Integer, nullable=False)
    lev_ratio: Mapped[float] = mapped_column(sqlalchemy.Float, nullable=False)

    parents: Mapped[list["MediaItem"]] = relationship(secondary="StreamRelation", back_populates="streams", lazy="selectin")
    blacklisted_parents: Mapped[list["MediaItem"]] = relationship(secondary="StreamBlacklistRelation", back_populates="blacklisted_streams", lazy="selectin")

    __table_args__ = (
        Index("ix_stream_infohash", "infohash"),
        Index("ix_stream_raw_title", "raw_title"),
        Index("ix_stream_parsed_title", "parsed_title"),
        Index("ix_stream_rank", "rank"),
    )

    def __init__(self, torrent: Torrent):
        self.raw_title = torrent.raw_title
        self.infohash = torrent.infohash
        self.parsed_title = torrent.data.parsed_title
        self.parsed_data = torrent.data
        self.rank = torrent.rank
        self.lev_ratio = torrent.lev_ratio

    def __hash__(self):
        return self.infohash

    def __eq__(self, other):
        return isinstance(other, Stream) and self.infohash == other.infohash