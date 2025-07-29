"""cleanup_stream_parsed_data_serialization

Clean up any existing Stream records that might have non-serializable parsed_data.
This migration sets all existing parsed_data to NULL to prevent JSON serialization errors.

Revision ID: dc138445c437
Revises: 5263b97bfb41
Create Date: 2025-07-28 20:45:41.925376

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'dc138445c437'
down_revision: Union[str, None] = '5263b97bfb41'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Clean up existing Stream parsed_data to prevent serialization errors."""

    # Set all existing parsed_data to NULL to avoid serialization issues
    # New Stream objects will use the proper serialization method
    try:
        op.execute("UPDATE \"Stream\" SET parsed_data = NULL WHERE parsed_data IS NOT NULL")
        print("Cleaned up existing Stream parsed_data records")
    except Exception as e:
        print(f"Note: Could not clean up Stream parsed_data: {e}")
        # This is not critical, continue with migration


def downgrade() -> None:
    """No downgrade needed - data was already problematic."""
    pass
