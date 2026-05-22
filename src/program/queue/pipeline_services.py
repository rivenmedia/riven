"""Pipeline dispatch service names (pause / capacity)."""

from __future__ import annotations

from typing import Literal

PipelineServiceName = Literal[
    "IndexerService",
    "Scraping",
    "Downloader",
    "FilesystemService",
    "Updater",
    "PostProcessing",
]

PIPELINE_DISPATCH_SERVICES: tuple[PipelineServiceName, ...] = (
    "FilesystemService",
    "Updater",
    "PostProcessing",
    "Downloader",
    "Scraping",
    "IndexerService",
)

_PIPELINE_SERVICE_SET = frozenset(PIPELINE_DISPATCH_SERVICES)


def is_pipeline_service(name: str) -> bool:
    return name in _PIPELINE_SERVICE_SET
