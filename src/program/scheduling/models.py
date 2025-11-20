from __future__ import annotations

from datetime import datetime
from enum import Enum

import sqlalchemy
from sqlalchemy import Index
from sqlalchemy.orm import Mapped, mapped_column

from program.db.db import Base


class ScheduledStatus(str, Enum):
    """Status values for scheduled tasks."""

    Pending = "pending"
    Completed = "completed"
    Failed = "failed"
    Cancelled = "cancelled"


class ScheduledTask(Base):
    """Persisted schedule entry for running item-related tasks at specific times.

    Decoupled by design: references item_id without foreign keys.
    """

    __tablename__ = "ScheduledTask"

    id: Mapped[int] = mapped_column(sqlalchemy.Integer, primary_key=True)
    item_id: Mapped[int]
    task_type: Mapped[str]
    scheduled_for: Mapped[datetime]
    status: Mapped[ScheduledStatus] = mapped_column(
        sqlalchemy.Enum(
            ScheduledStatus,
            name="scheduledstatus",
            values_callable=lambda enum: [e.value for e in enum],
        ),
        default=ScheduledStatus.Pending,
    )
    created_at: Mapped[datetime] = mapped_column(
        sqlalchemy.DateTime, default=datetime.now
    )
    executed_at: Mapped[datetime | None]
    reason: Mapped[str | None]
    offset_seconds: Mapped[int | None]

    __table_args__ = (
        Index("ix_scheduledtask_scheduled_for", "scheduled_for"),
        Index("ix_scheduledtask_status", "status"),
        Index(
            "ux_scheduledtask_item_task_time",
            "item_id",
            "task_type",
            "scheduled_for",
            unique=True,
        ),
    )

    def to_dict(self) -> dict[str, int | str | datetime | None]:
        """Serialize to a dict for logging/debugging."""
        return {
            "id": self.id,
            "item_id": self.item_id,
            "task_type": self.task_type,
            "scheduled_for": (
                self.scheduled_for.isoformat() if self.scheduled_for else None
            ),
            "status": self.status.value,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "executed_at": self.executed_at.isoformat() if self.executed_at else None,
            "offset_seconds": self.offset_seconds,
            "reason": self.reason,
        }
