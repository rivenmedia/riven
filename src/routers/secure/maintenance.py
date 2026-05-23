import os
from typing import Annotated, Literal

from fastapi import APIRouter, Body, HTTPException, status
from kink import di
from loguru import logger
import json

from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from program.db.db import db_session
from program.maintenance.tv_scrape_health import (
    TvScrapeHealthCandidate,
    analyze_tv_scrape_health,
)
from program.media.item import MediaItem, Season, Show
from program.program import Program
from routers.models.shared import MessageResponse
from routers.secure.items import apply_item_mutation

router = APIRouter(
    prefix="/maintenance",
    tags=["maintenance"],
    responses={404: {"description": "Not found"}},
)


class TvScrapeHealthCandidateResponse(BaseModel):
    item_id: int
    item_type: Literal["show", "season"]
    title: str
    reason: str
    episode_count: int
    streamless_count: int
    streamless_ratio: float
    recommended_reset: Literal["show", "season"]
    show_id: int | None = None
    details: str


class TvScrapeAnalyzeSummary(BaseModel):
    candidates: int
    shows: int
    seasons: int


class TvScrapeAnalyzeResponse(BaseModel):
    summary: TvScrapeAnalyzeSummary
    candidates: list[TvScrapeHealthCandidateResponse]


class TvScrapeApplyPayload(BaseModel):
    item_ids: list[int] = Field(min_length=1, description="Show or season IDs to reset")
    requeue: bool = Field(
        default=True,
        description="Re-queue pipeline work after reset via restore_pipeline_from_db",
    )

    @model_validator(mode="before")
    @classmethod
    def _coerce_json_string_body(cls, data: object) -> object:
        """Accept a JSON object or a double-encoded JSON string body."""

        if isinstance(data, str):
            parsed = json.loads(data)
            if isinstance(parsed, str):
                parsed = json.loads(parsed)
            return parsed
        return data


class TvScrapeApplyResponse(MessageResponse):
    reset_ids: list[int]
    requeued_count: int


def _candidate_to_response(
    candidate: TvScrapeHealthCandidate,
) -> TvScrapeHealthCandidateResponse:
    return TvScrapeHealthCandidateResponse(
        item_id=candidate.item_id,
        item_type=candidate.item_type,
        title=candidate.title,
        reason=candidate.reason,
        episode_count=candidate.episode_count,
        streamless_count=candidate.streamless_count,
        streamless_ratio=round(candidate.streamless_ratio, 4),
        recommended_reset=candidate.recommended_reset,
        show_id=candidate.show_id,
        details=candidate.details,
    )


@router.get(
    "/tv-scrape/analyze",
    summary="Analyze TV scrape health",
    description="Find shows/seasons with empty or streamless episode hierarchies after pack scrape.",
    operation_id="analyze_tv_scrape_health",
    response_model=TvScrapeAnalyzeResponse,
)
async def analyze_tv_scrape_health_endpoint() -> TvScrapeAnalyzeResponse:
    with db_session() as session:
        candidates = analyze_tv_scrape_health(session)

    show_rows = sum(1 for c in candidates if c.item_type == "show")
    season_rows = sum(1 for c in candidates if c.item_type == "season")

    return TvScrapeAnalyzeResponse(
        summary=TvScrapeAnalyzeSummary(
            candidates=len(candidates),
            shows=show_rows,
            seasons=season_rows,
        ),
        candidates=[_candidate_to_response(c) for c in candidates],
    )


def _reset_item(
    program: Program,
    session: Session,
    media_item: MediaItem,
    *,
    updater,
) -> None:
    refresh_paths: list[str] = []
    media_entry = media_item.media_entry

    if updater and media_entry:
        vfs_paths = media_entry.get_all_vfs_paths()
        for vfs_path in vfs_paths:
            abs_path = os.path.join(updater.library_path, vfs_path.lstrip("/"))
            refresh_path = os.path.dirname(os.path.dirname(os.path.dirname(abs_path)))
            if refresh_path not in refresh_paths:
                refresh_paths.append(refresh_path)

    def mutation(item: MediaItem, _session: Session) -> None:
        item.blacklist_active_stream()
        item.reset()

    apply_item_mutation(
        program,
        session,
        media_item,
        mutation,
        bubble_parents=True,
    )
    session.commit()

    if updater and updater.initialized:
        for refresh_path in refresh_paths:
            updater.refresh_path(refresh_path)


@router.post(
    "/tv-scrape/apply",
    summary="Apply TV scrape health cleanup",
    description="Reset selected shows/seasons and optionally re-queue pipeline work.",
    operation_id="apply_tv_scrape_health",
    response_model=TvScrapeApplyResponse,
)
async def apply_tv_scrape_health_endpoint(
    payload: Annotated[
        TvScrapeApplyPayload,
        Body(description="Cleanup apply payload"),
    ],
) -> TvScrapeApplyResponse:
    program = di[Program]
    services = program.services
    if services is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Program services not initialized",
        )

    updater = services.updater
    reset_ids: list[int] = []
    seen_reset: set[int] = set()

    try:
        with db_session() as session:
            for item_id in payload.item_ids:
                if item_id in seen_reset:
                    continue

                media_item = session.execute(
                    select(MediaItem).where(MediaItem.id == item_id)
                ).scalar_one_or_none()

                if media_item is None:
                    logger.warning(f"Maintenance apply: item {item_id} not found")
                    continue

                if not isinstance(media_item, (Show, Season)):
                    logger.warning(
                        f"Maintenance apply: item {item_id} is not a show or season"
                    )
                    continue

                try:
                    _reset_item(program, session, media_item, updater=updater)
                    reset_ids.append(int(media_item.id))
                    seen_reset.add(int(media_item.id))
                except Exception as e:
                    logger.error(
                        f"Failed to reset item {item_id} during maintenance apply: {e}"
                    )
                    continue

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e

    requeued_count = 0
    if payload.requeue and reset_ids:
        restored = program.em.restore_pipeline_from_db(
            program, source="maintenance"
        )
        requeued_count = len(restored)

    return TvScrapeApplyResponse(
        message=f"Reset {len(reset_ids)} item(s)"
        + (
            f"; re-queued {requeued_count} pipeline entries"
            if requeued_count
            else ""
        ),
        reset_ids=reset_ids,
        requeued_count=requeued_count,
    )
