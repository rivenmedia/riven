"""Metadata model extracted from item.py to avoid reserved-name conflicts.

This model stores shared descriptive data for MediaItem rows.
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

import sqlalchemy
from sqlalchemy import Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from program.db.db import db

from .item import MediaItem


class Metadata(db.Model):
    """Unified metadata for movies, shows, seasons and episodes.

    Multiple MediaItem rows (e.g., different qualities) can point to the same Metadata.
    """

    __tablename__ = "Metadata"

    id: Mapped[int] = mapped_column(sqlalchemy.Integer, primary_key=True)
    media_type: Mapped[str] = mapped_column(sqlalchemy.String, nullable=False)

    # External IDs
    imdb_id: Mapped[Optional[str]] = mapped_column(sqlalchemy.String, nullable=True)
    tvdb_id: Mapped[Optional[str]] = mapped_column(sqlalchemy.String, nullable=True)
    tmdb_id: Mapped[Optional[str]] = mapped_column(sqlalchemy.String, nullable=True)

    # Core descriptive fields
    title: Mapped[Optional[str]] = mapped_column(sqlalchemy.String, nullable=True)
    year: Mapped[Optional[int]] = mapped_column(sqlalchemy.Integer, nullable=True)
    aired_at: Mapped[Optional[datetime]] = mapped_column(
        sqlalchemy.DateTime, nullable=True
    )
    genres: Mapped[Optional[List[str]]] = mapped_column(sqlalchemy.JSON, nullable=True)
    rating: Mapped[Optional[float]] = mapped_column(sqlalchemy.Float, nullable=True)
    content_rating: Mapped[Optional[str]] = mapped_column(
        sqlalchemy.String, nullable=True
    )

    # Extended metadata (future-proof; indexers may populate gradually)
    plot: Mapped[Optional[str]] = mapped_column(sqlalchemy.Text, nullable=True)
    cast: Mapped[Optional[list[str]]] = mapped_column(sqlalchemy.JSON, nullable=True)
    crew: Mapped[Optional[list[str]]] = mapped_column(sqlalchemy.JSON, nullable=True)
    runtime: Mapped[Optional[int]] = mapped_column(sqlalchemy.Integer, nullable=True)

    # Locale/network and flags
    language: Mapped[Optional[str]] = mapped_column(sqlalchemy.String, nullable=True)
    country: Mapped[Optional[str]] = mapped_column(sqlalchemy.String, nullable=True)
    network: Mapped[Optional[str]] = mapped_column(sqlalchemy.String, nullable=True)
    is_anime: Mapped[Optional[bool]] = mapped_column(sqlalchemy.Boolean, default=False)
    aliases: Mapped[Optional[dict]] = mapped_column(sqlalchemy.JSON, default={})

    # Show-centric metadata
    release_data: Mapped[Optional[dict]] = mapped_column(sqlalchemy.JSON, default={})
    status: Mapped[Optional[str]] = mapped_column(sqlalchemy.String, nullable=True)

    # Backref to items
    items: Mapped[list["MediaItem"]] = relationship(
        back_populates="meta", cascade="save-update", lazy="selectin"
    )

    __table_args__ = (
        # Fast lookups
        Index("ix_metadata_media_type", "media_type"),
        Index("ix_metadata_title", "title"),
        Index("ix_metadata_imdb_id", "imdb_id"),
        Index("ix_metadata_tvdb_id", "tvdb_id"),
        Index("ix_metadata_tmdb_id", "tmdb_id"),
        Index("ix_metadata_network", "network"),
        Index("ix_metadata_country", "country"),
        Index("ix_metadata_language", "language"),
        Index("ix_metadata_aired_at", "aired_at"),
        Index("ix_metadata_year", "year"),
        Index("ix_metadata_rating", "rating"),
        Index("ix_metadata_content_rating", "content_rating"),
        # Ensure shared metadata by unique external IDs (each non-null must be unique)
        sqlalchemy.UniqueConstraint("imdb_id", name="ux_metadata_imdb_id"),
        sqlalchemy.UniqueConstraint("tmdb_id", name="ux_metadata_tmdb_id"),
        sqlalchemy.UniqueConstraint("tvdb_id", name="ux_metadata_tvdb_id"),
    )
