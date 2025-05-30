from datetime import datetime
from typing import List, Optional
from sqlalchemy import Index
import sqlalchemy
from sqlalchemy.orm import Mapped, mapped_column, object_session, relationship

from src.program.db import db
from src.program.media.metadata_ids import MetadataIds
from src.program.media.state import States


class Metadata(db.Model):
    __tablename__ = 'Metadata'
    id: Mapped[int] = mapped_column(sqlalchemy.Integer, primary_key=True, autoincrement=True)
    ids: Mapped[MetadataIds] = relationship()
    title: Mapped[Optional[str]] = mapped_column(sqlalchemy.String, nullable=True)
    type: Mapped[str] = mapped_column(sqlalchemy.String, nullable=False)
    aliases: Mapped[List[str]] = mapped_column(sqlalchemy.ARRAY(sqlalchemy.String), nullable=True)
    is_anime: Mapped[bool] = mapped_column(sqlalchemy.Boolean, nullable=False, default=False)
    genres: Mapped[List[str]] = mapped_column(sqlalchemy.ARRAY(sqlalchemy.String), nullable=True)
    network: Mapped[Optional[str]] = mapped_column(sqlalchemy.String, nullable=True)
    country: Mapped[Optional[str]] = mapped_column(sqlalchemy.String, nullable=True)
    language: Mapped[Optional[str]] = mapped_column(sqlalchemy.String, nullable=True)
    aired_at: Mapped[Optional[datetime]] = mapped_column(sqlalchemy.DateTime, nullable=True)
    year: Mapped[Optional[int]] = mapped_column(sqlalchemy.Integer, nullable=True)