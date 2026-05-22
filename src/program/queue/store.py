from __future__ import annotations

import heapq
from dataclasses import dataclass
from datetime import datetime
from threading import Lock
from typing import Any

from program.media.item import MediaItem
from program.media.state import States
from program.queue.mapping import (
    KANBAN_COLUMN_ORDER,
    dispatch_priority,
    pipeline_phase_for_entry,
    pipeline_phase_to_kanban,
    stage_for_state,
    stage_to_kanban,
    states_for_stage,
)
from program.queue.models import (
    ContentQueueEntry,
    EnqueueResult,
    PipelineStage,
    QueueEntry,
    QueueStats,
)
from program.utils import naive_local_datetime

SortTuple = tuple[int, int, datetime, int]


@dataclass
class _StageBucket:
    items: set[int]
    heap: list[SortTuple]


def _sort_tuple(entry: QueueEntry, now: datetime) -> SortTuple:
    run_at = naive_local_datetime(entry.run_at)
    defer_rank = 1 if run_at > now else 0
    state_prio = dispatch_priority(entry)[0]
    return (defer_rank, state_prio, run_at, entry.item_id)


class PipelineQueueStore:
    """Six dispatch-stage sub-queues backed by a global item_id index."""

    _STAGES = tuple(PipelineStage)

    def __init__(self) -> None:
        self._lock = Lock()
        self._entries: dict[int, QueueEntry] = {}
        self._stage_of: dict[int, PipelineStage] = {}
        self._buckets: dict[PipelineStage, _StageBucket] = {
            stage: _StageBucket(items=set(), heap=[]) for stage in self._STAGES
        }
        self._content: list[ContentQueueEntry] = []

    def get(self, item_id: int) -> QueueEntry | None:
        with self._lock:
            return self._entries.get(int(item_id))

    def contains_item(self, item_id: int) -> bool:
        with self._lock:
            return int(item_id) in self._entries

    def contains_content(self, content_item: MediaItem) -> bool:
        with self._lock:
            return self._content_matches_locked(content_item)

    def count_by_stage(self) -> dict[PipelineStage, int]:
        with self._lock:
            return {stage: len(self._buckets[stage].items) for stage in self._STAGES}

    def item_ids_in_stage(self, stage: PipelineStage) -> set[int]:
        with self._lock:
            return set(self._buckets[stage].items)

    def all_item_entries(self) -> list[QueueEntry]:
        with self._lock:
            return list(self._entries.values())

    def content_entries(self) -> list[ContentQueueEntry]:
        with self._lock:
            return list(self._content)

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()
            self._stage_of.clear()
            self._content.clear()
            for bucket in self._buckets.values():
                bucket.items.clear()
                bucket.heap.clear()

    def normalize_run_at(self) -> None:
        with self._lock:
            for entry in self._entries.values():
                if entry.run_at.tzinfo is not None:
                    entry.run_at = naive_local_datetime(entry.run_at)
            for entry in self._content:
                if entry.run_at.tzinfo is not None:
                    entry.run_at = naive_local_datetime(entry.run_at)

    def enqueue(self, entry: QueueEntry) -> EnqueueResult:
        entry.run_at = naive_local_datetime(entry.run_at)
        entry.queued_at = naive_local_datetime(entry.queued_at)
        item_id = int(entry.item_id)

        with self._lock:
            existing = self._entries.get(item_id)
            if existing is not None:
                existing.run_at = max(
                    naive_local_datetime(existing.run_at),
                    entry.run_at,
                )
                if entry.item_state is not None:
                    self._move_item_locked(item_id, entry.item_state, existing)
                return EnqueueResult.merged

            stage = stage_for_state(entry.item_state)
            self._entries[item_id] = entry
            self._stage_of[item_id] = stage
            self._buckets[stage].items.add(item_id)
            self._push_heap_locked(stage, entry, datetime.now())
            return EnqueueResult.added

    def enqueue_many(self, entries: list[QueueEntry]) -> int:
        added = 0
        for entry in entries:
            if self.enqueue(entry) == EnqueueResult.added:
                added += 1
        return added

    def enqueue_content(self, entry: ContentQueueEntry) -> EnqueueResult:
        entry.run_at = naive_local_datetime(entry.run_at)
        entry.queued_at = naive_local_datetime(entry.queued_at)

        with self._lock:
            if self._content_matches_locked(entry.content_item):
                return EnqueueResult.deduped_skipped
            self._content.append(entry)
            return EnqueueResult.added

    def merge_item(
        self,
        item_id: int,
        *,
        run_at: datetime | None = None,
        item_state: States | None = None,
    ) -> bool:
        with self._lock:
            existing = self._entries.get(int(item_id))
            if existing is None:
                return False
            if run_at is not None:
                existing.run_at = min(
                    naive_local_datetime(existing.run_at),
                    naive_local_datetime(run_at),
                )
                stage = self._stage_of[int(item_id)]
                self._push_heap_locked(stage, existing, datetime.now())
            if item_state is not None:
                self._move_item_locked(int(item_id), item_state, existing)
            return True

    def dequeue(self, item_id: int) -> bool:
        with self._lock:
            return self._remove_item_locked(int(item_id))

    def dequeue_content(self, content_item: MediaItem) -> bool:
        with self._lock:
            before = len(self._content)
            self._content = [
                e
                for e in self._content
                if not self._content_entry_matches(e.content_item, content_item)
            ]
            return len(self._content) < before

    def update_run_at(self, item_id: int, run_at: datetime) -> bool:
        with self._lock:
            entry = self._entries.get(int(item_id))
            if entry is None:
                return False
            entry.run_at = naive_local_datetime(run_at)
            stage = self._stage_of[int(item_id)]
            self._push_heap_locked(stage, entry, datetime.now())
            return True

    def update_state(self, item_id: int, state: States) -> bool:
        with self._lock:
            entry = self._entries.get(int(item_id))
            if entry is None:
                return False
            self._move_item_locked(int(item_id), state, entry)
            return True

    def peek_ordered(
        self, stage: PipelineStage, now: datetime, limit: int
    ) -> list[QueueEntry]:
        if limit <= 0:
            return []
        with self._lock:
            return self._select_top_locked(stage, now, limit, due_only=False)

    def peek_due(
        self, stage: PipelineStage, now: datetime, limit: int
    ) -> list[QueueEntry]:
        if limit <= 0:
            return []
        with self._lock:
            return self._select_top_locked(stage, now, limit, due_only=True)

    def pop_due(self, stage: PipelineStage, now: datetime) -> QueueEntry | None:
        """Remove and return the highest-priority due entry in a stage."""

        target_states = states_for_stage(stage)
        with self._lock:
            top = self._select_top_locked(stage, now, 1, due_only=True)
            if not top:
                return None
            entry = top[0]
            if entry.item_state not in target_states:
                return None
            self._remove_item_locked(entry.item_id)
            return entry

    def pop_content_due(self, now: datetime) -> ContentQueueEntry | None:
        with self._lock:
            ready = [
                e
                for e in self._content
                if naive_local_datetime(e.run_at) <= now
            ]
            if not ready:
                return None
            ready.sort(key=lambda e: naive_local_datetime(e.run_at))
            winner = ready[0]
            self._content.remove(winner)
            return winner

    def stats(self, now: datetime) -> QueueStats:
        now = naive_local_datetime(now) if now.tzinfo else now
        total_queued = 0
        deferred = 0
        next_deferred: datetime | None = None
        phase_counts: dict[str, int] = {}
        column_counts: dict[str, int] = {col: 0 for col in KANBAN_COLUMN_ORDER}
        queue_by_source: dict[str, int] = {}
        stage_counts: dict[PipelineStage, int] = {}

        with self._lock:
            for entry in self._entries.values():
                total_queued += 1
                run_at = naive_local_datetime(entry.run_at)
                deferred_flag = run_at > now
                phase = pipeline_phase_for_entry(entry, now=now)
                kanban = pipeline_phase_to_kanban(phase)
                stage = self._stage_of[entry.item_id]

                stage_counts[stage] = stage_counts.get(stage, 0) + 1
                phase_counts[phase] = phase_counts.get(phase, 0) + 1
                column_counts[kanban] = column_counts.get(kanban, 0) + 1
                queue_by_source[entry.emitted_by] = (
                    queue_by_source.get(entry.emitted_by, 0) + 1
                )

                if deferred_flag:
                    deferred += 1
                    if next_deferred is None or run_at < next_deferred:
                        next_deferred = run_at

            for entry in self._content:
                total_queued += 1
                run_at = naive_local_datetime(entry.run_at)
                if run_at > now:
                    deferred += 1
                    if next_deferred is None or run_at < next_deferred:
                        next_deferred = run_at
                phase = "queued_index"
                kanban = pipeline_phase_to_kanban(phase)
                phase_counts[phase] = phase_counts.get(phase, 0) + 1
                column_counts[kanban] = column_counts.get(kanban, 0) + 1
                queue_by_source[entry.emitted_by] = (
                    queue_by_source.get(entry.emitted_by, 0) + 1
                )

        return QueueStats(
            total_queued=total_queued,
            deferred=deferred,
            next_deferred=next_deferred,
            column_counts=column_counts,
            phase_counts=phase_counts,
            queue_by_source=queue_by_source,
            queue_truncated=False,
            stage_counts=stage_counts,
        )

    def peek_display_for_kanban(
        self,
        kanban_column: str,
        now: datetime,
        limit: int,
    ) -> tuple[list[QueueEntry], bool]:
        """Top-N queued rows for one Activity column; truncated if more exist."""

        stages = [
            stage
            for stage in self._STAGES
            if stage_to_kanban(stage) == kanban_column
        ]
        if not stages:
            return [], False

        collected: list[QueueEntry] = []
        truncated = False
        total_in_column = 0

        with self._lock:
            for stage in stages:
                total_in_column += len(self._buckets[stage].items)

        if total_in_column > limit:
            truncated = True

        per_stage_limit = limit
        for stage in stages:
            chunk = self.peek_ordered(stage, now, per_stage_limit)
            collected.extend(chunk)

        def display_key(entry: QueueEntry) -> tuple[int, datetime]:
            run_at = naive_local_datetime(entry.run_at)
            defer_rank = 1 if run_at > now else 0
            return (defer_rank, run_at)

        collected.sort(key=display_key)
        if len(collected) > limit:
            truncated = True
            collected = collected[:limit]
        return collected, truncated

    def downloader_entries(self, now: datetime) -> list[QueueEntry]:
        """Scraped rows and Downloader-emitted rows (deduped by item_id)."""

        with self._lock:
            matched: dict[int, QueueEntry] = {}
            for entry in self._entries.values():
                if entry.item_state == States.Scraped or entry.emitted_by == "Downloader":
                    item_id = entry.item_id
                    current = matched.get(item_id)
                    if current is None:
                        matched[item_id] = entry
                        continue
                    if _sort_tuple(entry, now) < _sort_tuple(current, now):
                        matched[item_id] = entry
            return list(matched.values())

    def _content_matches_locked(self, content_item: MediaItem) -> bool:
        return any(
            self._content_entry_matches(e.content_item, content_item)
            for e in self._content
        )

    @staticmethod
    def _content_entry_matches(a: MediaItem, b: MediaItem) -> bool:
        if a.id and b.id and a.id == b.id:
            return True
        if a.tmdb_id and b.tmdb_id and a.tmdb_id == b.tmdb_id:
            return True
        if a.tvdb_id and b.tvdb_id and a.tvdb_id == b.tvdb_id:
            return True
        if a.imdb_id and b.imdb_id and a.imdb_id == b.imdb_id:
            return True
        return False

    def _push_heap_locked(
        self, stage: PipelineStage, entry: QueueEntry, now: datetime
    ) -> None:
        heapq.heappush(self._buckets[stage].heap, _sort_tuple(entry, now))

    def _move_item_locked(
        self, item_id: int, state: States | None, entry: QueueEntry
    ) -> None:
        entry.item_state = state
        new_stage = stage_for_state(state)
        old_stage = self._stage_of.get(item_id)
        if old_stage == new_stage:
            self._push_heap_locked(new_stage, entry, datetime.now())
            return
        if old_stage is not None:
            self._buckets[old_stage].items.discard(item_id)
        self._stage_of[item_id] = new_stage
        self._buckets[new_stage].items.add(item_id)
        self._push_heap_locked(new_stage, entry, datetime.now())

    def _remove_item_locked(self, item_id: int) -> bool:
        if item_id not in self._entries:
            return False
        stage = self._stage_of.pop(item_id, None)
        del self._entries[item_id]
        if stage is not None:
            self._buckets[stage].items.discard(item_id)
        return True

    def _pop_valid_head_locked(
        self, stage: PipelineStage, now: datetime
    ) -> QueueEntry | None:
        bucket = self._buckets[stage]
        while bucket.heap:
            defer_rank, state_prio, run_at, item_id = heapq.heappop(bucket.heap)
            if item_id not in bucket.items:
                continue
            entry = self._entries.get(item_id)
            if entry is None:
                bucket.items.discard(item_id)
                continue
            current = _sort_tuple(entry, now)
            if (defer_rank, state_prio, run_at, item_id) != current:
                continue
            bucket.items.discard(item_id)
            del self._entries[item_id]
            del self._stage_of[item_id]
            return entry
        return None

    def _select_top_locked(
        self,
        stage: PipelineStage,
        now: datetime,
        limit: int,
        *,
        due_only: bool,
    ) -> list[QueueEntry]:
        candidates: list[QueueEntry] = []
        for item_id in self._buckets[stage].items:
            entry = self._entries.get(item_id)
            if entry is None:
                continue
            if due_only and naive_local_datetime(entry.run_at) > now:
                continue
            candidates.append(entry)

        candidates.sort(key=lambda e: _sort_tuple(e, now))
        return candidates[:limit]
