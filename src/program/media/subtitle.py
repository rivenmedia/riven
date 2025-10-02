from pathlib import Path
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from program.db.db import db

if TYPE_CHECKING:
    from program.media.item import MediaItem


class Subtitle(db.Model):
    __tablename__ = "Subtitle"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    language: Mapped[str] = mapped_column(String)
    file: Mapped[str] = mapped_column(String, nullable=True)

    parent_id: Mapped[int] = mapped_column(ForeignKey("MediaItem.id", ondelete="CASCADE"))
    parent: Mapped["MediaItem"] = relationship("MediaItem", back_populates="subtitles")

    __table_args__ = (
        Index("ix_subtitle_language", "language"),
        Index("ix_subtitle_file", "file"),
        Index("ix_subtitle_parent_id", "parent_id"),
    )

    def __init__(self, optional={}):
        for key in optional.keys():
            self.language = key
            self.file = optional[key]

    def remove(self):
        if self.file and Path(self.file).exists():
            Path(self.file).unlink()
        self.file = None
        return self

    def to_dict(self):
        return {
            "id": str(self.id),
            "language": self.language,
            "file": self.file,
            "parent_id": self.parent_id
        }


# ============================================================================
# SQLAlchemy Event Listener for Automatic File Cleanup
# ============================================================================

from sqlalchemy import event
from loguru import logger

def cleanup_subtitle_file(mapper, connection, target: Subtitle):
    """Automatically delete subtitle file from disk when Subtitle is deleted"""
    try:
        if target.file and Path(target.file).exists():
            Path(target.file).unlink()
            logger.debug(f"Deleted subtitle file {target.file}")
    except Exception as e:
        logger.warning(f"Failed to delete subtitle file {target.file}: {e}")


# Register event listener explicitly
event.listen(Subtitle, "before_delete", cleanup_subtitle_file)