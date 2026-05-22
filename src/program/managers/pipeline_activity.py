"""Report live pipeline step text for Activity dashboard cards."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from program.media.item import MediaItem


def report_pipeline_activity(item_id: int | None, detail: str) -> None:
    if item_id is None:
        return
    try:
        from kink import di

        from program.program import Program

        di[Program].em.set_pipeline_activity(int(item_id), detail)
    except Exception:
        pass


def report_pipeline_activity_for_item(item: "MediaItem", detail: str) -> None:
    report_pipeline_activity(getattr(item, "id", None), detail)
