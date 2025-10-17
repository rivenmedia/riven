from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

import sqlalchemy
from sqlalchemy import Index
from sqlalchemy.orm import Mapped, mapped_column

from program.db.db import db


class ScheduledStatus(str, Enum):
    """Status values for scheduled tasks."""

    Pending = "pending"
    Completed = "completed"
    Failed = "failed"
    Cancelled = "cancelled"


class ScheduledTask(db.Model):
    """Persisted schedule entry for running item-related tasks at specific times.

    Decoupled by design: references item_id without foreign keys.
    """

    __tablename__ = "ScheduledTask"

    id: Mapped[int] = mapped_column(sqlalchemy.Integer, primary_key=True)
    item_id: Mapped[int] = mapped_column(sqlalchemy.Integer, nullable=False)
    task_type: Mapped[str] = mapped_column(sqlalchemy.String, nullable=False)
    scheduled_for: Mapped[datetime] = mapped_column(sqlalchemy.DateTime, nullable=False)
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
    executed_at: Mapped[Optional[datetime]] = mapped_column(
        sqlalchemy.DateTime, nullable=True
    )
    reason: Mapped[Optional[str]] = mapped_column(sqlalchemy.String, nullable=True)
    offset_seconds: Mapped[Optional[int]] = mapped_column(
        sqlalchemy.Integer, nullable=True
    )

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

    def to_dict(self) -> dict:
        """Serialize to a dict for logging/debugging."""
        return {
            "id": self.id,
            "item_id": self.item_id,
            "task_type": self.task_type,
            "scheduled_for": (
                self.scheduled_for.isoformat() if self.scheduled_for else None
            ),
            "status": (
                self.status.value
                if isinstance(self.status, ScheduledStatus)
                else str(self.status)
            ),
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "executed_at": self.executed_at.isoformat() if self.executed_at else None,
            "offset_seconds": self.offset_seconds,
            "reason": self.reason,
        }
