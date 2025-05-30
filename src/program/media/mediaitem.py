from datetime import datetime
from typing import List, Optional
from sqlalchemy import Index
import sqlalchemy
from sqlalchemy.orm import Mapped, mapped_column, object_session, relationship

from src.program.db import db
from src.program.media.item_version import ItemVersion
from src.program.media.metadata_ids import MetadataIds
from src.program.media.request_info import RequestInfo
from src.program.media.state import States


class MediaItem(db.Model):
    __tablename__ = 'MediaItem'
    id: Mapped[int] = mapped_column(sqlalchemy.Integer, primary_key=True, autoincrement=True)
    metadata: Mapped[Optional[MetadataIds]] = relationship()
    request_info: Mapped[Optional[RequestInfo]] = relationship()
    versions: Mapped[List[ItemVersion]] = relationship(back_populates='mediaitem')