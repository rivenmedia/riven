from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from threading import Lock
from typing import Literal

from program.media.state import States

_RECENTLY_FINISHED_TTL = timedelta(minutes=2)


@dataclass
class RecentlyFinishedEntry:
    item_id: int
    completed_at: datetime
    outcome: Literal["success", "failed"] = "success"
    service_name: str | None = None
    failure_service: str | None = None
    completion_detail: str | None = None


class RecentlyFinishedStore:
    """In-memory Done column entries (not part of the six stage heaps)."""

    def __init__(self) -> None:
        self._entries: dict[int, RecentlyFinishedEntry] = {}
        self._lock = Lock()

    def record(
        self,
        item_id: int,
        *,
        outcome: Literal["success", "failed"] = "success",
        service_name: str | None = None,
        failure_service: str | None = None,
        completion_detail: str | None = None,
    ) -> None:
        now = datetime.now(UTC)
        with self._lock:
            self._prune_locked(now)
            self._entries[int(item_id)] = RecentlyFinishedEntry(
                item_id=int(item_id),
                completed_at=now,
                outcome=outcome,
                service_name=service_name,
                failure_service=failure_service if outcome == "failed" else None,
                completion_detail=completion_detail,
            )

    def pop(self, item_id: int) -> None:
        with self._lock:
            self._entries.pop(int(item_id), None)

    def failure_service_for(self, item_id: int) -> str | None:
        with self._lock:
            entry = self._entries.get(int(item_id))
            if entry is None:
                return None
            return entry.failure_service or entry.service_name

    def __contains__(self, item_id: int) -> bool:
        with self._lock:
            return int(item_id) in self._entries

    def completed_at_for(self, item_id: int) -> datetime | None:
        with self._lock:
            entry = self._entries.get(int(item_id))
            return entry.completed_at if entry else None

    def set_completed_at_for_test(self, item_id: int, completed_at: datetime) -> None:
        with self._lock:
            entry = self._entries.get(int(item_id))
            if entry is None:
                return
            self._entries[int(item_id)] = RecentlyFinishedEntry(
                item_id=entry.item_id,
                completed_at=completed_at,
                outcome=entry.outcome,
                service_name=entry.service_name,
                failure_service=entry.failure_service,
                completion_detail=entry.completion_detail,
            )

    def _prune_locked(self, now: datetime | None = None) -> None:
        cutoff = (now or datetime.now(UTC)) - _RECENTLY_FINISHED_TTL
        stale = [
            item_id
            for item_id, entry in self._entries.items()
            if entry.completed_at < cutoff
        ]
        for item_id in stale:
            del self._entries[item_id]

    def count(self) -> int:
        with self._lock:
            self._prune_locked()
            return len(self._entries)

    def display_rows(self) -> list[dict]:
        from sqlalchemy import select

        from program.db.db import db_session
        from program.media.item import MediaItem
        _chunk = 500
        now = datetime.now(UTC)
        with self._lock:
            self._prune_locked(now)
            entries = sorted(
                self._entries.values(),
                key=lambda e: e.completed_at,
                reverse=True,
            )

        item_ids = [int(entry.item_id) for entry in entries]
        states_by_id: dict[int, States] = {}
        if item_ids:
            with db_session() as session:
                for offset in range(0, len(item_ids), _chunk):
                    chunk = item_ids[offset : offset + _chunk]
                    for item_id, last_state in session.execute(
                        select(MediaItem.id, MediaItem.last_state).where(
                            MediaItem.id.in_(chunk)
                        )
                    ):
                        if last_state is not None:
                            states_by_id[int(item_id)] = last_state

        rows: list[dict] = []
        for entry in entries:
            failure_svc = entry.failure_service or entry.service_name
            if entry.outcome == "failed":
                state_name = States.Failed.name
            else:
                last_state = states_by_id.get(int(entry.item_id))
                state_name = (
                    last_state.name if last_state else States.Completed.name
                )
            rows.append(
                {
                    "item_id": entry.item_id,
                    "run_at": entry.completed_at,
                    "queued_at": entry.completed_at,
                    "item_state": state_name,
                    "emitted_by": entry.service_name or "Pipeline",
                    "deferred": False,
                    "in_flight": False,
                    "pipeline_phase": "recently_finished",
                    "kanban_column": "finish",
                    "completion_outcome": entry.outcome,
                    "failure_service": failure_svc,
                    "completion_detail": entry.completion_detail
                    or entry.service_name,
                }
            )
        return rows
