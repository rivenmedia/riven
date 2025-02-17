"""add failed attempts

Revision ID: d6c06f357feb
Revises: c99709e3648f
Create Date: 2025-02-10 07:39:51.600870

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector


# revision identifiers, used by Alembic.
revision: str = 'd6c06f357feb'
down_revision: Union[str, None] = 'c99709e3648f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    """
    Perform upgrade migration by adding a 'Paused' state to the existing 'states' enum type and a 'failed_attempts' column to the 'MediaItem' table if they are not already present.
    
    This function executes the following steps:
    1. Executes an SQL command to add the enum value 'Paused' to the 'states' type, ensuring it exists.
    2. Retrieves the list of existing columns in the 'MediaItem' table using SQLAlchemy's Inspector.
    3. Checks for the existence of the 'failed_attempts' column and adds it as an Integer column (nullable and with a server default of 0) if it is absent.
    
    Any exceptions raised during the execution of these operations will propagate to the caller.
    """
    op.execute("ALTER TYPE states ADD VALUE IF NOT EXISTS 'Paused'")

    conn = op.get_bind()
    inspector = Inspector.from_engine(conn)
    columns = [col['name'] for col in inspector.get_columns('MediaItem')]
    
    if 'failed_attempts' not in columns:
        op.add_column('MediaItem', 
            sa.Column('failed_attempts', 
                     sa.Integer(), 
                     nullable=True, 
                     server_default='0')
        )


def downgrade():
    """
    Reverts the migration changes applied in the upgrade function.
    
    This function inspects the "MediaItem" table and drops the "failed_attempts" column if it exists,
    thereby reversing the schema changes introduced in the upgrade. It establishes a database connection,
    retrieves the current columns of "MediaItem", and conditionally removes "failed_attempts".
    
    Note:
        - The function contains commented-out code that outlines how to remove values from the "states" enum
          type. Due to PostgreSQL limitations (which do not allow direct removal of enum values), this logic
          is provided as a reference and is not executed.
    """
    conn = op.get_bind()
    inspector = Inspector.from_engine(conn)
    columns = [col['name'] for col in inspector.get_columns('MediaItem')]
    
    if 'failed_attempts' in columns:
        op.drop_column('MediaItem', 'failed_attempts')
        
    # Note: PostgreSQL doesn't support removing enum values
    # If we need to remove the states, we'd need to:
    # 1. Create a new enum without those values
    # 2. Update the column to use the new enum
    # 3. Drop the old enum
    # This is left commented out as it's usually not worth the complexity
    """
    # Example of how to remove enum values (if needed):
    op.execute('''
        CREATE TYPE states_new AS ENUM (
            'Unknown', 'Unreleased', 'Ongoing', 'Requested', 'Indexed',
            'Scraped', 'Downloaded', 'Symlinked', 'Completed', 'PartiallyCompleted'
        )
    ''')
    op.execute('ALTER TABLE "MediaItem" ALTER COLUMN last_state TYPE states_new USING last_state::text::states_new')
    op.execute('DROP TYPE states')
    op.execute('ALTER TYPE states_new RENAME TO states')
    """