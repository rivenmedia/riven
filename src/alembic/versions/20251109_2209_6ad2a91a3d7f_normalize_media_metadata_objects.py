"""normalize_media_metadata_objects

Normalize MediaEntry.media_metadata values to JSON objects (dicts),
undoing earlier double-serialization that stored them as JSON strings.

Revision ID: 6ad2a91a3d7f
Revises: f109995eb51e
Create Date: 2025-11-09 22:09:00

"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import Table, MetaData

# revision identifiers, used by Alembic.
revision: str = "6ad2a91a3d7f"
down_revision: Union[str, None] = "f109995eb51e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Coerce any JSON-string values in media_metadata into JSON objects.

    Cross-dialect approach: iterate rows and json.loads() strings, then update.
    Safe for both PostgreSQL and SQLite.
    """
    import json

    connection = op.get_bind()
    inspector = sa.inspect(connection)
    tables = inspector.get_table_names()

    # Case-insensitive check for table existence
    mediaentry_exists = any(t.lower() == "mediaentry" for t in tables)
    if not mediaentry_exists:
        return

    # Preserve actual casing of the table name
    actual_table_name = next(
        (t for t in tables if t.lower() == "mediaentry"), "MediaEntry"
    )

    metadata = MetaData()
    media_entry_table = Table(actual_table_name, metadata, autoload_with=connection)

    # Select rows where media_metadata is not null
    stmt = sa.select(media_entry_table.c.id, media_entry_table.c.media_metadata).where(
        media_entry_table.c.media_metadata.isnot(None)
    )
    result = connection.execute(stmt)

    rows_to_fix: list[tuple[int, dict]] = []

    for row in result:
        entry_id = row[0]
        media_metadata = row[1]
        if isinstance(media_metadata, str):
            try:
                parsed = json.loads(media_metadata)
                if isinstance(parsed, (dict, list)):
                    # We only coerce to dict/list; downstream expects dict but list is harmless
                    rows_to_fix.append((entry_id, parsed))
            except Exception:
                # Ignore unparsable strings; leave as-is
                pass

    # Apply updates in small batches
    for entry_id, parsed in rows_to_fix:
        connection.execute(
            sa.update(media_entry_table)
            .where(media_entry_table.c.id == entry_id)
            .values(media_metadata=parsed)
        )


def downgrade() -> None:
    """No-op. We do not re-stringify JSON objects on downgrade."""
    pass
