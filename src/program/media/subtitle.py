from pathlib import Path
from program.db.db import db
from sqlalchemy import Integer, String, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship


class Subtitle(db.Model):
    __tablename__ = "Subtitle"
    
    _id: Mapped[int] = mapped_column(Integer, primary_key=True)
    language: Mapped[str] = mapped_column(String)
    file: Mapped[str] = mapped_column(String, nullable=True)
    
    parent_id: Mapped[int] = mapped_column(Integer, ForeignKey("MediaItem._id", ondelete="CASCADE"))
    parent: Mapped["MediaItem"] = relationship("MediaItem", back_populates="subtitles")

    __table_args__ = (
        Index('ix_subtitle_language', 'language'),
        Index('ix_subtitle_file', 'file'),
        Index('ix_subtitle_parent_id', 'parent_id'),
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