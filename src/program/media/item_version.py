from datetime import datetime
from typing import List, Optional
from sqlalchemy import Index
import sqlalchemy
from sqlalchemy.orm import Mapped, mapped_column, object_session, relationship

from src.program.db import db
from src.program.media.file_system_info import FileSystemInfo
from src.program.media.mediaitem import MediaItem
from src.program.media.metadata_ids import MetadataIds
from src.program.media.request_info import RequestInfo
from src.program.media.state import States
from src.program.media.stream import Stream
from src.program.media.subtitle import Subtitle


class ItemVersion(db.Model):
    __tablename__ = 'ItemVersion'
    id: Mapped[int] = mapped_column(sqlalchemy.Integer, primary_key=True, autoincrement=True)
    mediaitem: Mapped[MediaItem] = relationship(back_populates='versions')
    active_stream: Mapped[Optional[dict]] = mapped_column(sqlalchemy.JSON, nullable=True)
    streams: Mapped[list[Stream]] = relationship(secondary="StreamRelation", back_populates="parents", lazy="selectin", cascade="all")
    blacklisted_streams: Mapped[list[Stream]] = relationship(secondary="StreamBlacklistRelation", back_populates="blacklisted_parents", lazy="selectin", cascade="all")
    filesystem_info: Mapped[FileSystemInfo] = relationship()
    update_folder: Mapped[Optional[str]] = mapped_column(sqlalchemy.String, nullable=True)
    subtitles: Mapped[list[Subtitle]] = relationship(Subtitle, back_populates="parent", lazy="selectin", cascade="all, delete-orphan")
    failed_attempts: Mapped[int] = mapped_column(sqlalchemy.Integer, default=0)
