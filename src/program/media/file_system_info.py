from datetime import datetime
from typing import Optional
from sqlalchemy import Index
import sqlalchemy
from sqlalchemy.orm import Mapped, mapped_column, object_session, relationship

from src.program.db import db
from src.program.media.state import States


class FileSystemInfo(db.Model):
    __tablename__ = 'FileSystemInfo'
    id: Mapped[int] = mapped_column(sqlalchemy.Integer, primary_key=True, autoincrement=True)
    symlink_attempts: Mapped[int] = mapped_column(sqlalchemy.Integer, nullable=False, default=0)
    symlink_path: Mapped[Optional[str]] = mapped_column(sqlalchemy.String, nullable=True)
    file_path: Mapped[str] = mapped_column(sqlalchemy.String, nullable=True)
    folder_path: Mapped[str] = mapped_column(sqlalchemy.String, nullable=True)
    alternative_folder_path: Mapped[Optional[str]] = mapped_column(sqlalchemy.String, nullable=True)
    symlinked: Mapped[bool] = mapped_column(sqlalchemy.Boolean, nullable=False, default=False)