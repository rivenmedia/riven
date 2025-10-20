"""
Separate metadata into dedicated Metadata table and link from MediaItem.

- Adds Metadata table with unique constraints on external IDs
- Adds MediaItem.metadata_id FK to Metadata
- Migrates existing data from MediaItem/Show into Metadata
- Drops metadata columns from MediaItem and Show

This enables multiple MediaItem rows (e.g., different qualities) to share a single Metadata record.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from alembic import op
import sqlalchemy as sa
from sqlalchemy.orm import Session

# revision identifiers, used by Alembic.
revision = "9f1e2d3c4b5a"
down_revision = "7e5b5cf430ff"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    # 1) Create Metadata table (idempotent)
    if not insp.has_table("Metadata"):
        op.create_table(
            "Metadata",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("media_type", sa.String(), nullable=False),
            sa.Column("imdb_id", sa.String(), nullable=True),
            sa.Column("tvdb_id", sa.String(), nullable=True),
            sa.Column("tmdb_id", sa.String(), nullable=True),
            sa.Column("title", sa.String(), nullable=True),
            sa.Column("year", sa.Integer(), nullable=True),
            sa.Column("aired_at", sa.DateTime(), nullable=True),
            sa.Column("genres", sa.JSON(), nullable=True),
            sa.Column("rating", sa.Float(), nullable=True),
            sa.Column("content_rating", sa.String(), nullable=True),
            sa.Column("plot", sa.Text(), nullable=True),
            sa.Column("cast", sa.JSON(), nullable=True),
            sa.Column("crew", sa.JSON(), nullable=True),
            sa.Column("runtime", sa.Integer(), nullable=True),
            sa.Column("language", sa.String(), nullable=True),
            sa.Column("country", sa.String(), nullable=True),
            sa.Column("network", sa.String(), nullable=True),
            sa.Column("is_anime", sa.Boolean(), nullable=True),
            sa.Column("aliases", sa.JSON(), nullable=True),
            sa.Column("release_data", sa.JSON(), nullable=True),
            sa.Column("status", sa.String(), nullable=True),
        )

    # Indexes and unique constraints on Metadata
    if not _has_index("Metadata", "ix_metadata_media_type"):
        op.create_index("ix_metadata_media_type", "Metadata", ["media_type"])
    if not _has_index("Metadata", "ix_metadata_title"):
        op.create_index("ix_metadata_title", "Metadata", ["title"])
    if not _has_index("Metadata", "ix_metadata_imdb_id"):
        op.create_index("ix_metadata_imdb_id", "Metadata", ["imdb_id"])
    if not _has_index("Metadata", "ix_metadata_tvdb_id"):
        op.create_index("ix_metadata_tvdb_id", "Metadata", ["tvdb_id"])
    if not _has_index("Metadata", "ix_metadata_tmdb_id"):
        op.create_index("ix_metadata_tmdb_id", "Metadata", ["tmdb_id"])
    if not _has_index("Metadata", "ix_metadata_network"):
        op.create_index("ix_metadata_network", "Metadata", ["network"])
    if not _has_index("Metadata", "ix_metadata_country"):
        op.create_index("ix_metadata_country", "Metadata", ["country"])
    if not _has_index("Metadata", "ix_metadata_language"):
        op.create_index("ix_metadata_language", "Metadata", ["language"])
    if not _has_index("Metadata", "ix_metadata_aired_at"):
        op.create_index("ix_metadata_aired_at", "Metadata", ["aired_at"])
    if not _has_index("Metadata", "ix_metadata_year"):
        op.create_index("ix_metadata_year", "Metadata", ["year"])
    if not _has_index("Metadata", "ix_metadata_rating"):
        op.create_index("ix_metadata_rating", "Metadata", ["rating"])
    if not _has_index("Metadata", "ix_metadata_content_rating"):
        op.create_index("ix_metadata_content_rating", "Metadata", ["content_rating"])

    try:
        with op.batch_alter_table("Metadata") as batch_op:
            batch_op.create_unique_constraint("ux_metadata_imdb_id", ["imdb_id"])
            batch_op.create_unique_constraint("ux_metadata_tmdb_id", ["tmdb_id"])
            batch_op.create_unique_constraint("ux_metadata_tvdb_id", ["tvdb_id"])
    except Exception:
        # Constraints may already exist (e.g., created via create_all in a previous migration)
        pass

    # 2) Add metadata_id to MediaItem (idempotent)
    existing_cols = {c["name"] for c in insp.get_columns("MediaItem")}
    if "metadata_id" not in existing_cols:
        with op.batch_alter_table("MediaItem") as batch_op:
            batch_op.add_column(sa.Column("metadata_id", sa.Integer(), nullable=True))
            try:
                batch_op.create_foreign_key(
                    "fk_mediaitem_metadata_id",
                    "Metadata",
                    ["metadata_id"],
                    ["id"],
                    ondelete="SET NULL",
                )
            except Exception:
                pass

    # 3) Data migration: Move existing metadata into Metadata and link (only if legacy columns exist)
    legacy_cols = {
        "title",
        "imdb_id",
        "tvdb_id",
        "tmdb_id",
        "network",
        "country",
        "language",
        "aired_at",
        "year",
        "genres",
        "rating",
        "content_rating",
        "aliases",
        "is_anime",
    }
    if legacy_cols.issubset(existing_cols):
        session = Session(bind=bind)

        mediaitem = sa.table(
            "MediaItem",
            sa.column("id", sa.Integer()),
            sa.column("type", sa.String()),
            sa.column("title", sa.String()),
            sa.column("imdb_id", sa.String()),
            sa.column("tvdb_id", sa.String()),
            sa.column("tmdb_id", sa.String()),
            sa.column("network", sa.String()),
            sa.column("country", sa.String()),
            sa.column("language", sa.String()),
            sa.column("aired_at", sa.DateTime()),
            sa.column("year", sa.Integer()),
            sa.column("genres", sa.JSON()),
            sa.column("rating", sa.Float()),
            sa.column("content_rating", sa.String()),
            sa.column("aliases", sa.JSON()),
            sa.column("is_anime", sa.Boolean()),
            sa.column("metadata_id", sa.Integer()),
        )

    show = sa.table(
        "Show",
        sa.column("id", sa.Integer()),
        sa.column("release_data", sa.JSON()),
        sa.column("tvdb_status", sa.String()),
    )

    metadata_tbl = sa.table(
        "Metadata",
        sa.column("id", sa.Integer()),
        sa.column("media_type", sa.String()),
        sa.column("imdb_id", sa.String()),
        sa.column("tvdb_id", sa.String()),
        sa.column("tmdb_id", sa.String()),
        sa.column("title", sa.String()),
        sa.column("year", sa.Integer()),
        sa.column("aired_at", sa.DateTime()),
        sa.column("genres", sa.JSON()),
        sa.column("rating", sa.Float()),
        sa.column("content_rating", sa.String()),
        sa.column("language", sa.String()),
        sa.column("country", sa.String()),
        sa.column("network", sa.String()),
        sa.column("is_anime", sa.Boolean()),
        sa.column("aliases", sa.JSON()),
        sa.column("release_data", sa.JSON()),
        sa.column("status", sa.String()),
    )

    # Preload show extras and migrate legacy data only if legacy columns were present
    if "session" in locals() and session is not None:
        show_extras = {
            r.id: (r.release_data, r.tvdb_status)
            for r in session.execute(
                sa.select(show.c.id, show.c.release_data, show.c.tvdb_status)
            ).all()
        }

        cache: dict[tuple[str, str], int] = {}

        rows = session.execute(
            sa.select(
                mediaitem.c.id,
                mediaitem.c.type,
                mediaitem.c.title,
                mediaitem.c.imdb_id,
                mediaitem.c.tvdb_id,
                mediaitem.c.tmdb_id,
                mediaitem.c.network,
                mediaitem.c.country,
                mediaitem.c.language,
                mediaitem.c.aired_at,
                mediaitem.c.year,
                mediaitem.c.genres,
                mediaitem.c.rating,
                mediaitem.c.content_rating,
                mediaitem.c.aliases,
                mediaitem.c.is_anime,
            )
        ).all()

        for r in rows:
            # Key by strongest available external ID, else by unique row id to avoid accidental merges
            key: tuple[str, str]
            if r.imdb_id:
                key = ("imdb", str(r.imdb_id))
            elif r.tmdb_id:
                key = ("tmdb", str(r.tmdb_id))
            elif r.tvdb_id:
                key = ("tvdb", str(r.tvdb_id))
            else:
                key = ("row", str(r.id))

            md_id: Optional[int] = cache.get(key)
            if md_id is None:
                release_data, status = show_extras.get(r.id, (None, None))
                res = session.execute(
                    sa.insert(metadata_tbl)
                    .values(
                        media_type=r.type,
                        imdb_id=r.imdb_id,
                        tvdb_id=r.tvdb_id,
                        tmdb_id=r.tmdb_id,
                        title=r.title,
                        year=r.year,
                        aired_at=r.aired_at,
                        genres=r.genres,
                        rating=r.rating,
                        content_rating=r.content_rating,
                        language=r.language,
                        country=r.country,
                        network=r.network,
                        is_anime=r.is_anime,
                        aliases=r.aliases,
                        release_data=release_data,
                        status=status,
                    )
                    .returning(metadata_tbl.c.id)
                )
                md_id = res.scalar_one()
                cache[key] = md_id

            # Link item to metadata
            session.execute(
                sa.update(mediaitem)
                .where(mediaitem.c.id == r.id)
                .values(metadata_id=md_id)
            )

            session.commit()

    # 4) Drop old columns and indexes from MediaItem
    _safe_drop_index("MediaItem", "ix_mediaitem_title")
    _safe_drop_index("MediaItem", "ix_mediaitem_imdb_id")
    _safe_drop_index("MediaItem", "ix_mediaitem_tvdb_id")
    _safe_drop_index("MediaItem", "ix_mediaitem_tmdb_id")
    _safe_drop_index("MediaItem", "ix_mediaitem_network")
    _safe_drop_index("MediaItem", "ix_mediaitem_country")
    _safe_drop_index("MediaItem", "ix_mediaitem_language")
    _safe_drop_index("MediaItem", "ix_mediaitem_aired_at")
    _safe_drop_index("MediaItem", "ix_mediaitem_year")
    _safe_drop_index("MediaItem", "ix_mediaitem_rating")
    _safe_drop_index("MediaItem", "ix_mediaitem_content_rating")
    _safe_drop_index("MediaItem", "ix_mediaitem_type_aired_at")

    with op.batch_alter_table("MediaItem") as batch_op:
        for col in [
            "imdb_id",
            "tvdb_id",
            "tmdb_id",
            "title",
            "network",
            "country",
            "language",
            "aired_at",
            "year",
            "genres",
            "rating",
            "content_rating",
            "aliases",
            "is_anime",
        ]:
            try:
                batch_op.drop_column(col)
            except Exception:
                pass

    # 5) Drop metadata columns from Show (moved to Metadata)
    if insp.has_table("Show"):
        with op.batch_alter_table("Show") as batch_op:
            for col in ["release_data", "tvdb_status"]:
                try:
                    batch_op.drop_column(col)
                except Exception:
                    pass


def downgrade() -> None:
    # Downgrade is non-trivial; avoid accidental data loss by refusing to auto-downgrade.
    raise RuntimeError("Downgrade for metadata refactor is not supported.")


# --- helpers ---


def _has_index(table: str, index_name: str) -> bool:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    try:
        existing = {ix["name"] for ix in insp.get_indexes(table)}
        return index_name in existing
    except Exception:
        return False


def _safe_drop_index(table: str, index_name: str) -> None:
    try:
        op.drop_index(index_name, table_name=table)
    except Exception:
        pass
