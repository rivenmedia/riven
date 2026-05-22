from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from program.media.item import MediaItem
from program.media.state import States


class PipelineStage(str, Enum):
    index = "index"
    scrape = "scrape"
    download = "download"
    symlink = "symlink"
    update = "update"
    post_process = "post_process"


class EnqueueResult(str, Enum):
    added = "added"
    merged = "merged"
    deduped_skipped = "deduped_skipped"


@dataclass
class QueueEntry:
    item_id: int
    item_state: States | None
    run_at: datetime
    queued_at: datetime
    emitted_by: str
    overrides: dict[str, Any] | None = None


@dataclass
class ContentQueueEntry:
    content_item: MediaItem
    run_at: datetime
    queued_at: datetime
    emitted_by: str
    overrides: dict[str, Any] | None = None


@dataclass
class QueueStats:
    total_queued: int
    deferred: int
    next_deferred: datetime | None
    column_counts: dict[str, int]
    phase_counts: dict[str, int]
    queue_by_source: dict[str, int]
    queue_truncated: bool
    stage_counts: dict[PipelineStage, int] = field(default_factory=dict)
