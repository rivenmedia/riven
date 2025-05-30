from datetime import datetime
from typing import Optional
from sqlalchemy import Index
import sqlalchemy
from sqlalchemy.orm import Mapped, mapped_column, object_session, relationship

from src.program.db import db
from src.program.media.state import States


class RequestInfo(db.Model):
    __tablename__ = 'RequestInfo'
    id: Mapped[int] = mapped_column(sqlalchemy.Integer, primary_key=True, autoincrement=True)
    requested_by: Mapped[str] = mapped_column(sqlalchemy.String, nullable=False)
    request_id: Mapped[str] = mapped_column(sqlalchemy.String, nullable=False)
    overseerr_id: Mapped[Optional[int]] = mapped_column(sqlalchemy.Integer, nullable=True)