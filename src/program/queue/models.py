"""
Dramatiq message models for Riven's queue system.

Defines job types, payload schemas, message structure, and factories
used for producing and consuming messages via Dramatiq/LavinMQ.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Final, List, Literal, Optional, TypedDict

from program.media.item import MediaItem

QUEUE_NAMES: Final[Dict[str, str]] = {
    "indexing": "indexing",
    "scraping": "scraping",
    "downloader": "downloader",
    "symlinker": "symlinker",
    "updater": "updater",
    "postprocessing": "postprocessing",
}

PayloadKind = Literal["existing_item", "content_item"]

class JobType(Enum):
    """Types of jobs that can be processed."""
    INDEX = "index"
    SCRAPE = "scrape"
    DOWNLOAD = "download"
    SYMLINK = "symlink"
    UPDATE = "update"
    POST_PROCESS = "post_process"


class ContentItemData(TypedDict, total=False):
    """Payload for new content that hasn't been persisted yet."""
    kind: Literal["content_item"]
    title: Optional[str]
    type: Optional[str]  # "movie" | "show" | "season" | "episode"
    tmdb_id: Optional[int]
    tvdb_id: Optional[int]
    imdb_id: Optional[str]
    year: Optional[int]
    requested_by: Optional[str]
    requested_at: Optional[str]  # ISO8601
    overseerr_id: Optional[int]
    log_string: Optional[str]


@dataclass
class JobMessage:
    """
    Canonical message structure for Dramatiq jobs.

    Exactly one of (item_id, content_item_data) is expected.
    'payload_kind' makes the explicit intent observable by workers and logs.
    """
    job_id: str
    job_type: JobType
    payload_kind: PayloadKind
    item_id: Optional[str] = None
    content_item_data: Optional[Dict[str, Any]] = None
    emitted_by: str = "Unknown"
    run_at: Optional[str] = None
    retry_count: int = 0
    max_retries: int = 3
    priority: int = 5  # 1=highest, 10=lowest
    dependencies: Optional[List[str]] = None  # List of job_ids that must complete first
    metadata: Optional[Dict[str, Any]] = None

    def __post_init__(self) -> None:
        if self.run_at is None:
            self.run_at = datetime.now().isoformat()
        if self.metadata is None:
            self.metadata = {}
        if self.dependencies is None:
            self.dependencies = []

    def to_dict(self) -> Dict[str, Any]:
        """Convert to a dict Dramatiq can serialize."""
        data = asdict(self)
        data["job_type"] = self.job_type.value
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "JobMessage":
        """Rehydrate from a dict passed into actors."""
        data = dict(data)
        data["job_type"] = JobType(data["job_type"])
        return cls(**data)

    @property
    def log_message(self) -> str:
        """Human-friendly log summary."""
        if self.payload_kind == "existing_item" and self.item_id:
            return f"Job {self.job_type.value} for Item ID {self.item_id}"
        if self.payload_kind == "content_item" and self.content_item_data:
            # Try multiple sources for a meaningful display name
            title = (self.content_item_data.get("log_string") or
                    self.content_item_data.get("title") or
                    f"{self.content_item_data.get('type', 'item').title()} ID {self.content_item_data.get('tmdb_id') or self.content_item_data.get('tvdb_id') or self.content_item_data.get('imdb_id') or 'Unknown'}")
            return f"Job {self.job_type.value} for {title}"
        return f"Job {self.job_type.value}"


# Type-specific job dataclasses. These mostly annotate emitted_by defaults.
# Note: We can't use dataclass inheritance with field defaults due to Python dataclass limitations
# Instead, we'll use the factory function with appropriate defaults

MESSAGE_CLASSES = {
    JobType.INDEX: JobMessage,
    JobType.SCRAPE: JobMessage,
    JobType.DOWNLOAD: JobMessage,
    JobType.SYMLINK: JobMessage,
    JobType.UPDATE: JobMessage,
    JobType.POST_PROCESS: JobMessage,
}

# Default emitted_by values for each job type
DEFAULT_EMITTED_BY: Final[Dict[JobType, str]] = {
    JobType.INDEX: "CompositeIndexer",
    JobType.SCRAPE: "Scraping",
    JobType.DOWNLOAD: "Downloader",
    JobType.SYMLINK: "Symlinker",
    JobType.UPDATE: "Updater",
    JobType.POST_PROCESS: "PostProcessing",
}


def create_job_message(
    job_type: JobType,
    *,
    payload_kind: PayloadKind,
    item: Optional[MediaItem] = None,
    item_id: Optional[str] = None,
    content_item_data: Optional[ContentItemData] = None,
    **kwargs: Any,
) -> JobMessage:
    """
    Factory for JobMessage with explicit payload kind.

    - payload_kind="existing_item" => set item_id (preferred for persisted items).
    - payload_kind="content_item"  => set content_item_data (new/transient).
    """
    job_id = f"{job_type.value}_{datetime.now().timestamp()}"

    # Defensive build for content_item_data if user passed a transient MediaItem.
    if payload_kind == "content_item" and not content_item_data and item and not getattr(item, "id", None):
        content_item_data = {
            "kind": "content_item",
            "title": item.title,
            "type": item.type,
            "tmdb_id": item.tmdb_id,
            "tvdb_id": item.tvdb_id,
            "imdb_id": item.imdb_id,
            "year": item.year,
        }

    # Set default emitted_by if not provided
    if "emitted_by" not in kwargs:
        kwargs["emitted_by"] = DEFAULT_EMITTED_BY.get(job_type, "Manual")

    message_class = MESSAGE_CLASSES[job_type]
    return message_class(
        job_id=job_id,
        job_type=job_type,
        payload_kind=payload_kind,                     # <-- explicit & early
        item_id=item_id or (item.id if item and getattr(item, "id", None) else None),
        content_item_data=content_item_data,
        **kwargs,
    )
