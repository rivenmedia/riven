from __future__ import annotations

from typing import TYPE_CHECKING

from program.media.state import States
from program.queue.models import PipelineStage

if TYPE_CHECKING:
    from program.queue.models import QueueEntry

KANBAN_COLUMN_ORDER: tuple[str, ...] = (
    "added",
    "scrape",
    "download",
    "symlink",
    "update",
    "post_process",
    "finish",
)

KANBAN_SERVICE_NAMES: dict[str, str | None] = {
    "added": "IndexerService",
    "scrape": "Scraping",
    "download": "Downloader",
    "symlink": "FilesystemService",
    "update": "Updater",
    "post_process": "PostProcessing",
    "finish": None,
}

_IN_FLIGHT_SERVICE_TO_PHASE: dict[str, str] = {
    "IndexerService": "indexing",
    "Scraping": "scraping",
    "Downloader": "downloading",
    "FilesystemService": "symlinking",
    "Updater": "updating",
    "PostProcessing": "post_processing",
}

_PHASE_TO_KANBAN: dict[str, str] = {
    "indexing": "added",
    "queued_index": "added",
    "scraping": "scrape",
    "queued_scrape": "scrape",
    "downloading": "download",
    "queued_download": "download",
    "queued_download_deferred": "download",
    "symlinking": "symlink",
    "queued_symlink": "symlink",
    "updating": "update",
    "queued_update": "update",
    "post_processing": "post_process",
    "queued_post_process": "post_process",
    "queued_other": "finish",
}

_SERVICE_TO_STAGE: dict[str, PipelineStage] = {
    "IndexerService": PipelineStage.index,
    "Scraping": PipelineStage.scrape,
    "Downloader": PipelineStage.download,
    "FilesystemService": PipelineStage.symlink,
    "Updater": PipelineStage.update,
    "PostProcessing": PipelineStage.post_process,
}

_STAGE_TO_KANBAN: dict[PipelineStage, str] = {
    PipelineStage.index: "added",
    PipelineStage.scrape: "scrape",
    PipelineStage.download: "download",
    PipelineStage.symlink: "symlink",
    PipelineStage.update: "update",
    PipelineStage.post_process: "post_process",
}

_STAGE_DISPATCH_STATES: dict[PipelineStage, frozenset[States | None]] = {
    PipelineStage.index: frozenset({States.Unknown, States.Requested, None}),
    PipelineStage.scrape: frozenset({States.Indexed}),
    PipelineStage.download: frozenset({States.Scraped}),
    PipelineStage.symlink: frozenset({States.Downloaded}),
    PipelineStage.update: frozenset({States.Symlinked}),
    PipelineStage.post_process: frozenset(
        {States.Completed, States.PartiallyCompleted}
    ),
}

_STATE_DISPATCH_PRIORITY: dict[States | None, int] = {
    States.Completed: 0,
    States.PartiallyCompleted: 1,
    States.Symlinked: 2,
    States.Downloaded: 3,
    States.Scraped: 4,
    States.Indexed: 5,
    States.Unknown: 6,
    States.Requested: 6,
    None: 6,
}


def stage_for_state(state: States | None) -> PipelineStage:
    if state in (States.Requested, States.Unknown, None):
        return PipelineStage.index
    if state == States.Indexed:
        return PipelineStage.scrape
    if state == States.Scraped:
        return PipelineStage.download
    if state == States.Downloaded:
        return PipelineStage.symlink
    if state == States.Symlinked:
        return PipelineStage.update
    if state in (States.Completed, States.PartiallyCompleted):
        return PipelineStage.post_process
    return PipelineStage.index


def service_to_stage(service_name: str) -> PipelineStage | None:
    return _SERVICE_TO_STAGE.get(service_name)


def stage_to_kanban(stage: PipelineStage) -> str:
    return _STAGE_TO_KANBAN.get(stage, "finish")


def states_for_stage(stage: PipelineStage) -> frozenset[States | None]:
    return _STAGE_DISPATCH_STATES[stage]


def pipeline_phase_to_kanban(phase: str) -> str:
    return _PHASE_TO_KANBAN.get(phase, "finish")


def kanban_service_name(kanban_column: str) -> str | None:
    return KANBAN_SERVICE_NAMES.get(kanban_column)


def resolve_pipeline_phase(
    *,
    item_state: States | None,
    deferred: bool,
    in_flight_service: str | None,
) -> str:
    if in_flight_service:
        return _IN_FLIGHT_SERVICE_TO_PHASE.get(in_flight_service, "queued_other")
    return _queued_pipeline_phase(item_state, deferred=deferred)


def _queued_pipeline_phase(item_state: States | None, *, deferred: bool) -> str:
    if item_state in (States.Requested, States.Unknown, None):
        return "queued_index"
    if item_state == States.Indexed:
        return "queued_scrape"
    if item_state == States.Scraped:
        return "queued_download_deferred" if deferred else "queued_download"
    if item_state == States.Downloaded:
        return "queued_symlink"
    if item_state == States.Symlinked:
        return "queued_update"
    if item_state in (States.Completed, States.PartiallyCompleted):
        return "queued_post_process"
    return "queued_other"


def pipeline_phase_for_entry(
    entry: "QueueEntry",
    *,
    now,
    in_flight_service: str | None = None,
) -> str:
    from program.utils import naive_local_datetime

    if in_flight_service:
        return _IN_FLIGHT_SERVICE_TO_PHASE.get(in_flight_service, "queued_other")
    deferred = naive_local_datetime(entry.run_at) > now
    return _queued_pipeline_phase(entry.item_state, deferred=deferred)


def dispatch_priority(entry: QueueEntry) -> tuple[int, int, object, int]:
    """Lower = higher priority for dispatch ordering within a stage."""

    from program.utils import naive_local_datetime

    state_prio = _STATE_DISPATCH_PRIORITY.get(entry.item_state, 999)
    run_at = naive_local_datetime(entry.run_at)
    return (state_prio, 0, run_at, entry.item_id)
