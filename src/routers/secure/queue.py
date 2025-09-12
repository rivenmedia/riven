# Queue management API endpoints
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, HTTPException
from loguru import logger
from pydantic import BaseModel, Field, field_validator

from program.queue.models import JobType, create_job_message
from program.queue.monitoring import dependency_manager, queue_monitor
from program.queue.queue_manager import QueueManager

router = APIRouter(prefix="/queue", tags=["queue"])


class QueueStatusResponse(BaseModel):
    """Response model for queue status."""
    queue_name: str
    length: int
    status: str


class QueueStatsResponse(BaseModel):
    """Response model for overall queue statistics."""
    total_queues: int
    active_queues: int
    total_jobs: int
    queues: List[QueueStatusResponse]


PayloadKind = Literal["existing_item", "content_item"]


class ContentItemPayload(BaseModel):
    """
    Payload for a NEW item that does not exist in the DB yet.
    Used ONLY with job_type == "index" (CompositeIndexer).
    """
    title: Optional[str] = None
    type: Optional[str] = Field(default=None, description='One of "movie" | "show" | "season" | "episode"')
    tmdb_id: Optional[int] = None
    tvdb_id: Optional[int] = None
    imdb_id: Optional[str] = None
    year: Optional[int] = None
    requested_by: Optional[str] = None
    requested_at: Optional[str] = None  # ISO8601
    overseerr_id: Optional[int] = None
    log_string: Optional[str] = None


class JobSubmissionRequest(BaseModel):
    """
    Unified job submission:
    - For EXISTING items, provide: payload_kind="existing_item" and item_id.
    - For NEW content, provide:   payload_kind="content_item" and content fields.
      In this case, job_type MUST be "index".
    """
    job_type: str
    payload_kind: PayloadKind
    # existing_item:
    item_id: Optional[str] = None
    # content_item:
    content: Optional[ContentItemPayload] = None

    priority: int = Field(default=0, ge=0, le=10)
    metadata: Optional[Dict[str, Any]] = None

    @field_validator("job_type")
    @classmethod
    def _validate_job_type(cls, v: str) -> str:
        # Normalize and also fail early if not in enum values.
        try:
            JobType(v)
        except ValueError:
            allowed = ", ".join(t.value for t in JobType)
            raise ValueError(f"Invalid job type '{v}'. Allowed: {allowed}")
        return v

    @field_validator("payload_kind")
    @classmethod
    def _validate_payload_kind(cls, v: PayloadKind) -> PayloadKind:
        if v not in ("existing_item", "content_item"):
            raise ValueError("payload_kind must be 'existing_item' or 'content_item'")
        return v

    @field_validator("content")
    @classmethod
    def _coerce_requested_at(cls, v: Optional[ContentItemPayload]) -> Optional[ContentItemPayload]:
        # Accept datetime-like inputs if you later add them; keep simple for now.
        return v

    def ensure_consistent(self) -> None:
        """
        Enforce our strict standard:
          - existing_item => item_id required; content must be None
          - content_item  => content required; job_type must be 'index'; item_id must be None
        """
        if self.payload_kind == "existing_item":
            if not self.item_id:
                raise ValueError("existing_item submissions require 'item_id'.")
            if self.content is not None:
                raise ValueError("existing_item must not include 'content' payload.")
        else:
            # content_item
            if not self.content:
                raise ValueError("content_item submissions require 'content' payload.")
            if self.item_id is not None:
                raise ValueError("content_item must not include 'item_id'.")
            if JobType(self.job_type) is not JobType.INDEX:
                raise ValueError("content_item submissions must use job_type='index'.")


class JobSubmissionResponse(BaseModel):
    """Response model for job submission."""
    job_id: str
    status: str
    message: str


@router.get("/status", response_model=QueueStatsResponse)
async def get_queue_status():
    """Get status of all queues."""
    try:
        qm = QueueManager()
        status = qm.get_queue_status()

        queues: List[QueueStatusResponse] = []
        total_jobs = 0
        active_queues = 0

        for queue_name, queue_info in status.items():
            if isinstance(queue_info, dict) and "length" in queue_info:
                queue_status = QueueStatusResponse(
                    queue_name=queue_name,
                    length=queue_info["length"],
                    status=queue_info["status"],
                )
                queues.append(queue_status)
                total_jobs += int(queue_info["length"]) if isinstance(queue_info["length"], int) else 0
                if queue_info["status"] == "active":
                    active_queues += 1

        return QueueStatsResponse(
            total_queues=len(queues),
            active_queues=active_queues,
            total_jobs=total_jobs,
            queues=queues,
        )
    except Exception as e:
        logger.error(f"Failed to get queue status: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get queue status: {str(e)}")


@router.get("/status/{queue_name}", response_model=QueueStatusResponse)
async def get_queue_status_by_name(queue_name: str):
    """Get status of a specific queue."""
    try:
        qm = QueueManager()
        status = qm.get_queue_status()

        if queue_name not in status:
            raise HTTPException(status_code=404, detail=f"Queue '{queue_name}' not found")

        queue_info = status[queue_name]
        if not isinstance(queue_info, dict) or "length" not in queue_info:
            raise HTTPException(status_code=500, detail=f"Invalid queue info for '{queue_name}'")

        return QueueStatusResponse(
            queue_name=queue_name,
            length=queue_info["length"],
            status=queue_info["status"],
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get queue status for {queue_name}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get queue status: {str(e)}")


@router.post("/submit", response_model=JobSubmissionResponse)
async def submit_job(request: JobSubmissionRequest):
    """
    Submit a job to the queue.

    Strict rules:
    - existing_item: payload_kind='existing_item', item_id provided.
    - content_item:  payload_kind='content_item', content provided, job_type='index'.
    """
    try:
        qm = QueueManager()
        # Validate enum and strict payload
        job_type = JobType(request.job_type)
        request.ensure_consistent()

        if request.payload_kind == "existing_item":
            # Pre-flight duplicate/lock checks to avoid enqueue storms
            active_job_id = queue_monitor.get_active_job_id_for_item(request.item_id)  # type: ignore[arg-type]
            if active_job_id:
                raise HTTPException(status_code=409, detail=f"Item '{request.item_id}' already has active job {active_job_id}")
            locks = dependency_manager.get_item_locks(request.item_id)  # type: ignore[arg-type]
            if locks:
                raise HTTPException(status_code=409, detail=f"Item '{request.item_id}' locked by jobs: {sorted(list(locks))}")

            job = create_job_message(
                job_type=job_type,
                payload_kind="existing_item",
                item_id=request.item_id,
                priority=request.priority,
                metadata=request.metadata or {},
            )

        else:
            # content_item path: build content_item_data for the indexer
            content_item_data = request.content.model_dump() if request.content else None
            # Optional: set requested_at default if omitted
            if content_item_data is not None and not content_item_data.get("requested_at"):
                content_item_data["requested_at"] = datetime.now().isoformat()

            # Deduplication based on external IDs to reduce duplicate index jobs
            tmdb_id = (content_item_data or {}).get("tmdb_id")
            tvdb_id = (content_item_data or {}).get("tvdb_id")
            imdb_id = (content_item_data or {}).get("imdb_id")
            if queue_monitor.has_duplicate_job(tmdb_id=tmdb_id, tvdb_id=tvdb_id, imdb_id=imdb_id):
                dup = queue_monitor.get_duplicate_job_info(tmdb_id=tmdb_id, tvdb_id=tvdb_id, imdb_id=imdb_id)
                detail = f"Duplicate job in-flight: {dup.job_id}" if dup else "Duplicate job in-flight"
                raise HTTPException(status_code=409, detail=detail)

            job = create_job_message(
                job_type=job_type,               # must be JobType.INDEX; validated above
                payload_kind="content_item",
                content_item_data=content_item_data,  # required; factory will enforce
                priority=request.priority,
                metadata=request.metadata or {},
                emitted_by="API",
            )

        success = qm.submit_job(job)
        if success:
            return JobSubmissionResponse(
                job_id=job.job_id,
                status="submitted",
                message=f"Job {job.job_id} submitted successfully to {job_type.value} queue",
            )

        raise HTTPException(status_code=500, detail="Failed to submit job")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to submit job: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to submit job: {str(e)}")
