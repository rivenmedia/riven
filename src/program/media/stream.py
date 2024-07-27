from typing import Optional
from RTN import Torrent
from program.db.db import db
import sqlalchemy
from sqlalchemy.orm import Mapped, mapped_column, relationship


class Stream(db.Model):
    __tablename__ = "Stream"
    _id: Mapped[int] = mapped_column(primary_key=True)
    infohash: Mapped[str] = mapped_column(sqlalchemy.String, nullable=False)
    raw_title: Mapped[str] = mapped_column(sqlalchemy.String, nullable=False)
    parsed_title: Mapped[str] = mapped_column(sqlalchemy.String, nullable=False)
    rank: Mapped[int] = mapped_column(sqlalchemy.Integer, nullable=False)
    lev_ratio: Mapped[float] = mapped_column(sqlalchemy.Float, nullable=False)
    blacklisted: Mapped[bool] = mapped_column(sqlalchemy.Boolean, nullable=False)

    parent_id: Mapped[int] = mapped_column(sqlalchemy.ForeignKey("MediaItem._id"))
    parent: Mapped["MediaItem"] = relationship(lazy=False, back_populates="streams", foreign_keys="Stream.parent_id")

    def __init__(self, torrent: Torrent, parent):
        self.raw_title = torrent.raw_title
        self.infohash = torrent.infohash
        self.parsed_title = torrent.data.parsed_title
        self.rank = torrent.rank
        self.lev_ratio = torrent.lev_ratio
        self.blacklisted = False
        self.parent = parent

    def __hash__(self):
        return self.infohash
    
    def __eq__(self, other):
        return isinstance(other, Stream) and self.infohash == other.infohash
    