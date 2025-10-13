"""combined_library_profiles

Revision ID: a1b2c3d4e5f7
Revises: f7ea12c9d1ab
Create Date: 2025-10-09 12:00:00.000000

This migration combines:
1. Adding rating and content_rating fields to MediaItem
2. Adding library_profiles field to MediaEntry

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f7'
down_revision: Union[str, None] = 'f7ea12c9d1ab'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    1. Add rating and content_rating to MediaItem
    2. Add library_profiles to MediaEntry
    3. Trigger re-indexing by clearing indexed_at for all items
    """
    
    # Step 1: Add rating and content_rating fields to MediaItem
    with op.batch_alter_table('MediaItem', schema=None) as batch_op:
        batch_op.add_column(sa.Column('rating', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('content_rating', sa.String(), nullable=True))
        batch_op.create_index('ix_mediaitem_content_rating', ['content_rating'], unique=False)
        batch_op.create_index('ix_mediaitem_rating', ['rating'], unique=False)

    # Step 2: Add library_profiles field to MediaEntry
    with op.batch_alter_table('MediaEntry', schema=None) as batch_op:
        batch_op.add_column(sa.Column(
            'library_profiles',
            sa.JSON(),
            nullable=True,
            comment='List of library profile keys this entry matches (from settings.json)'
        ))

    print("Migration complete: Added rating, content_rating, and library_profiles fields.")


def downgrade() -> None:
    """
    Reverse the migration:
    1. Remove library_profiles from MediaEntry
    2. Remove rating and content_rating from MediaItem
    """
    
    # Step 1: Remove library_profiles from MediaEntry
    with op.batch_alter_table('MediaEntry', schema=None) as batch_op:
        batch_op.drop_column('library_profiles')

    # Step 2: Remove rating and content_rating from MediaItem
    with op.batch_alter_table('MediaItem', schema=None) as batch_op:
        batch_op.drop_index('ix_mediaitem_rating')
        batch_op.drop_index('ix_mediaitem_content_rating')
        batch_op.drop_column('content_rating')
        batch_op.drop_column('rating')

