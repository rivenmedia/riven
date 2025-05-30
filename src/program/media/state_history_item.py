from datetime import datetime
from typing import Optional
from sqlalchemy import Index
import sqlalchemy
from sqlalchemy.orm import Mapped, mapped_column, object_session, relationship

from src.program.db import db
from src.program.media.state import States


class StateHistoryItem(db.Model):
    __tablename__ = 'StateHistory'
    id: Mapped[int] = mapped_column(sqlalchemy.Integer, primary_key=True, autoincrement=True)
    state: Mapped[States] = mapped_column(sqlalchemy.Enum(States), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(sqlalchemy.DateTime, nullable=False, default=datetime.now(datetime.timezone.utc))