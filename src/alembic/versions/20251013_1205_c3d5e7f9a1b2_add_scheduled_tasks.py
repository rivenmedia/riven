"""add_scheduled_tasks

Revision ID: c3d5e7f9a1b2
Revises: b2c3d4e5f8g9
Create Date: 2025-10-13 12:05:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c3d5e7f9a1b2"
down_revision: Union[str, None] = "b2c3d4e5f8g9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def get_table_names():
    bind = op.get_bind()
    inspector = Inspector.from_engine(bind)
    return inspector.get_table_names()

def upgrade() -> None:
    existing_tables = get_table_names()

    if "ScheduledTask" not in existing_tables:
        op.create_table(
            "ScheduledTask",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("item_id", sa.Integer(), nullable=False),
            sa.Column("task_type", sa.String(), nullable=False),
            sa.Column("scheduled_for", sa.DateTime(), nullable=False),
            sa.Column("status", sa.Enum("pending", "completed", "failed", "cancelled", name="scheduledstatus"), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("executed_at", sa.DateTime(), nullable=True),
            sa.Column("reason", sa.String(), nullable=True),
            sa.Column("offset_seconds", sa.Integer(), nullable=True),
        )
        op.create_index("ix_scheduledtask_scheduled_for", "ScheduledTask", ["scheduled_for"], unique=False)
        op.create_index("ix_scheduledtask_status", "ScheduledTask", ["status"], unique=False)
        op.create_index(
            "ux_scheduledtask_item_task_time",
            "ScheduledTask",
            ["item_id", "task_type", "scheduled_for"],
            unique=True,
        )


def downgrade() -> None:
    tables = get_table_names()

    if "ScheduledTask" in tables:
        op.drop_index("ux_scheduledtask_item_task_time", table_name="ScheduledTask")
        op.drop_index("ix_scheduledtask_status", table_name="ScheduledTask")
        op.drop_index("ix_scheduledtask_scheduled_for", table_name="ScheduledTask")
        op.drop_table("ScheduledTask")

