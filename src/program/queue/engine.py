from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, List, Optional

from loguru import logger

from program.media.item import MediaItem
from program.media.state import States
from program.queue.models import JobMessage, JobType, create_job_message
from program.services.post_processing.subliminal import Subliminal
from program.services.scrapers import Scraping
from program.settings.manager import settings_manager


@dataclass(frozen=True)
class EnqueueRequest:
    """Declarative request to enqueue a job for an item id at optional time."""
    job_type: JobType
    item_id: str
    emit_by: str = "System"
    run_at: Optional[datetime] = None
    priority: int = 5


def _episode_ids_for_post_processing(item: MediaItem) -> Iterable[str]:
    if item.type == "episode" and item.id:
        yield item.id
        return
    if item.type == "season":
        for e in getattr(item, "episodes", []) or []:
            if e.state == States.Completed and e.id and Subliminal.should_submit(e):
                yield e.id
    if item.type == "show":
        for s in getattr(item, "seasons", []) or []:
            for e in getattr(s, "episodes", []) or []:
                if e.state == States.Completed and e.id and Subliminal.should_submit(e):
                    yield e.id


def decide_next_jobs(item: MediaItem, emitted_by: str) -> List[EnqueueRequest]:
    """
    Simplified, proven state transition logic based on legacy process_event.
    Returns a list of EnqueueRequest for the next service(s).
    """
    out: List[EnqueueRequest] = []

    current_state: States = item.last_state or item.state

    # Skip Paused/Failed/Unknown
    if current_state in (States.Paused, States.Failed):
        return out

    # Completed => post-processing (handled here like legacy)
    elif current_state == States.Completed and emitted_by != "PostProcessing":
        if settings_manager.settings.post_processing.subliminal.enabled:
            for episode_id in _episode_ids_for_post_processing(item):
                out.append(EnqueueRequest(JobType.POST_PROCESS, episode_id, emit_by=emitted_by, priority=5))
        return out
    
        if emitted_by != PostProcessing:
            if settings_manager.settings.post_processing.subliminal.enabled:
                next_service = PostProcessing
                if existing_item.type in ["movie", "episode"] and Subliminal.should_submit(existing_item):
                    items_to_submit = [existing_item]
                    logger.debug(f"Next service: {next_service.__name__} for {existing_item.id}")
                elif existing_item.type == "show":
                    items_to_submit = [e for s in existing_item.seasons for e in s.episodes if e.last_state == States.Completed and Subliminal.should_submit(e)]
                    if items_to_submit:
                        logger.debug(f"Next service: {next_service.__name__} for {len(items_to_submit)} episodes from {existing_item.id}")
                elif existing_item.type == "season":
                    items_to_submit = [e for e in existing_item.episodes if e.last_state == States.Completed and Subliminal.should_submit(e)]
                    if items_to_submit:
                        logger.debug(f"Next service: {next_service.__name__} for {len(items_to_submit)} episodes from {existing_item.id}")
                if not items_to_submit:
                    logger.debug(f"No post-processing needed for {existing_item.id}")
                    return no_further_processing
        else:
            return no_further_processing

    # Ongoing / PartiallyCompleted => fan-out down the hierarchy
    elif current_state in (States.PartiallyCompleted, States.Ongoing):
        if item.type == "show":
            for s in getattr(item, "seasons", []) or []:
                if (getattr(s, "last_state", None) or getattr(s, "state", None)) not in (States.Completed, States.Unreleased):
                    out.extend(decide_next_jobs(s, emitted_by))
            return out
        if item.type == "season":
            for e in getattr(item, "episodes", []) or []:
                if (getattr(e, "last_state", None) or getattr(e, "state", None)) != States.Completed:
                    out.extend(decide_next_jobs(e, emitted_by))
            return out
        # Leaf/other types: fall through to linear mapping below

    # Indexed => Scraping first. If already emitted by Scraping, fan-out to children.
    elif current_state == States.Indexed:
        def maybe_enqueue_scrape(obj) -> None:
            if Scraping.should_submit(obj) and getattr(obj, "id", None):
                out.append(EnqueueRequest(JobType.SCRAPE, obj.id, emit_by=emitted_by, priority=5))

        if emitted_by != "Scraping" and Scraping.should_submit(item):
            if getattr(item, "id", None):
                maybe_enqueue_scrape(item)
            return out

        if item.type == "show":
            for s in getattr(item, "seasons", []) or []:
                s_state = getattr(s, "last_state", None)
                if s_state and s_state in (States.Indexed, States.PartiallyCompleted, States.Unknown) and Scraping.should_submit(s):
                    if getattr(s, "id", None):
                        out.append(EnqueueRequest(JobType.SCRAPE, s.id, emit_by=emitted_by, priority=5))
            return out

        if item.type == "season":
            for e in getattr(item, "episodes", []) or []:
                e_state = getattr(e, "last_state", None)
                if e_state and e_state in (States.Indexed, States.Unknown) and Scraping.should_submit(e):
                    if getattr(e, "id", None):
                        out.append(EnqueueRequest(JobType.SCRAPE, e.id, emit_by=emitted_by, priority=5))
            return out

    # Linear mapping for remaining states
    linear_map = {
        States.Requested: JobType.INDEX,
        States.Scraped: JobType.DOWNLOAD,
        States.Downloaded: JobType.SYMLINK,
        States.Symlinked: JobType.UPDATE,
        States.Completed: JobType.POST_PROCESS,
    }
    job_type = linear_map.get(current_state)
    if job_type and getattr(item, "id", None):
        out.append(EnqueueRequest(job_type, item.id, emit_by=emitted_by, priority=5))
    else:
        logger.debug(f"No next job for {item.log_string} in state {current_state}")
    return out


def build_messages(reqs: Iterable[EnqueueRequest]) -> List[JobMessage]:
    """Helper: convert EnqueueRequests to JobMessages."""
    msgs: List[JobMessage] = []
    for r in reqs:
        msg = create_job_message(
            r.job_type,
            payload_kind="existing_item",
            item_id=r.item_id,
            emitted_by=r.emit_by,
            priority=r.priority or 5,
            run_at=r.run_at.isoformat() if r.run_at else None,
        )
        msgs.append(msg)
    return msgs
