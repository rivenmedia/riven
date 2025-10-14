"""Reseed FilesystemEntry.id sequence to prevent duplicate primary keys

Revision ID: f7ea12c9d1ab
Revises: a1b2c3d4e5f6
Create Date: 2025-10-04 15:10:00.000000

This migration ensures the PostgreSQL sequence backing FilesystemEntry.id is
in sync with the data after refactors, restores, or bulk imports. It is safe to
run multiple times and works for both legacy serial and modern identity columns.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "f7ea12c9d1ab"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Reseed the FilesystemEntry.id sequence to MAX(id)+1.

    Rationale:
    - After schema refactors, data restores, or manual imports, the sequence that
      provides new primary keys can fall behind the current MAX(id). When that
      happens, the next INSERT raises `UniqueViolation: duplicate key value violates
      unique constraint`.
    - This migration uses pg_get_serial_sequence to locate the backing sequence and
      sets it to MAX(id)+1 in an idempotent manner. It is safe to re-run.
    - It works for both SERIAL and IDENTITY-based columns in PostgreSQL.
    """
    op.execute(
        sa.text(
            """
DO $$
DECLARE
    seq_name text;
    max_id bigint;
BEGIN
    -- Find the sequence backing FilesystemEntry.id (works for serial/identity)
    SELECT pg_get_serial_sequence('"FilesystemEntry"', 'id') INTO seq_name;

    IF seq_name IS NULL THEN
        -- If no sequence is found, skip reseeding (nothing to do)
        RAISE NOTICE 'No sequence found for FilesystemEntry.id; skipping reseed';
        RETURN;
    END IF;

    -- Compute the current maximum id
    SELECT COALESCE(MAX(id), 0) FROM "FilesystemEntry" INTO max_id;

    -- Set sequence to max(id)+1; use is_called=false so nextval returns exactly that
    EXECUTE format('SELECT setval(%L, %s, false)', seq_name, max_id + 1);
END
$$;
            """
        )
    )


def downgrade() -> None:
    """No-op: sequence reseeding is safe to keep; leaving as is on downgrade."""
    pass
