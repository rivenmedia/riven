from datetime import datetime
from typing import Optional
from sqlalchemy import Index
import sqlalchemy
from sqlalchemy.orm import Mapped, mapped_column, object_session, relationship

from src.program.db import db
from src.program.media.state import States


class MetadataIds(db.Model):
    __tablename__ = 'MetadataIds'
    id: Mapped[int] = mapped_column(sqlalchemy.Integer, primary_key=True, autoincrement=True)
    trakt_id: Mapped[Optional[int]] = mapped_column(sqlalchemy.Integer, nullable=True)
    imdb_id: Mapped[Optional[str]] = mapped_column(sqlalchemy.String, nullable=True)
    tvdb_id: Mapped[Optional[str]] = mapped_column(sqlalchemy.String, nullable=True)
    tmdb_id: Mapped[Optional[str]] = mapped_column(sqlalchemy.String, nullable=True)