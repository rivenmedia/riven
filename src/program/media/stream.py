from RTN import Torrent
from program.db.db import db
import sqlalchemy
from sqlalchemy.orm import Mapped, mapped_column, relationship
from loguru import logger

class StreamRelation(db.Model):
    __tablename__ = "StreamRelation"

    _id: Mapped[int] = mapped_column(sqlalchemy.Integer, primary_key=True)
    parent_id: Mapped[int] = mapped_column(sqlalchemy.Integer, sqlalchemy.ForeignKey("MediaItem._id", ondelete="CASCADE"))
    child_id: Mapped[int] = mapped_column(sqlalchemy.Integer, sqlalchemy.ForeignKey("Stream._id", ondelete="CASCADE"))
    
class StreamBlacklistRelation(db.Model):
    __tablename__ = "StreamBlacklistRelation"

    _id: Mapped[int] = mapped_column(sqlalchemy.Integer, primary_key=True)
    media_item_id: Mapped[int] = mapped_column(sqlalchemy.Integer, sqlalchemy.ForeignKey("MediaItem._id", ondelete="CASCADE"))
    stream_id: Mapped[int] = mapped_column(sqlalchemy.Integer, sqlalchemy.ForeignKey("Stream._id", ondelete="CASCADE"))

class Stream(db.Model):
    __tablename__ = "Stream"

    _id: Mapped[int] = mapped_column(sqlalchemy.Integer, primary_key=True)
    infohash: Mapped[str] = mapped_column(sqlalchemy.String, nullable=False)
    raw_title: Mapped[str] = mapped_column(sqlalchemy.String, nullable=False)
    parsed_title: Mapped[str] = mapped_column(sqlalchemy.String, nullable=False)
    rank: Mapped[int] = mapped_column(sqlalchemy.Integer, nullable=False)
    lev_ratio: Mapped[float] = mapped_column(sqlalchemy.Float, nullable=False)

    parents: Mapped[list["MediaItem"]] = relationship(secondary="StreamRelation", back_populates="streams")
    blacklisted_parents: Mapped[list["MediaItem"]] = relationship(secondary="StreamBlacklistRelation", back_populates="blacklisted_streams")

    def __init__(self, torrent: Torrent):
        self.raw_title = torrent.raw_title
        self.infohash = torrent.infohash
        self.parsed_title = torrent.data.parsed_title
        self.rank = torrent.rank
        self.lev_ratio = torrent.lev_ratio

    def __hash__(self):
        return self.infohash
    
    def __eq__(self, other):
        return isinstance(other, Stream) and self.infohash == other.infohash