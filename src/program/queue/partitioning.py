"""
Partitioning utilities for queue sharding.

- Defines partition counts per job type.
- Provides consistent hashing to select partition index.
- Resolves partitioned queue and actor names.
"""
from __future__ import annotations

import hashlib
import os

from typing import Dict, Tuple

from loguru import logger

from .models import JobType, QUEUE_NAMES

# Agreed partition counts per job type
PARTITION_COUNTS: Dict[JobType, int] = {
    JobType.DOWNLOAD: 8,
    JobType.SCRAPE: 4,
    JobType.INDEX: 2,
    JobType.SYMLINK: 2,
    JobType.UPDATE: 2,
    JobType.POST_PROCESS: 2,
}


def _base_queue_name(job_type: JobType) -> str:
    mapping = {
        JobType.INDEX: QUEUE_NAMES["indexing"],
        JobType.SCRAPE: QUEUE_NAMES["scraping"],
        JobType.DOWNLOAD: QUEUE_NAMES["downloader"],
        JobType.SYMLINK: QUEUE_NAMES["symlinker"],
        JobType.UPDATE: QUEUE_NAMES["updater"],
        JobType.POST_PROCESS: QUEUE_NAMES["postprocessing"],
    }
    return mapping[job_type]


def _base_actor_name(job_type: JobType) -> str:
    return {
        JobType.INDEX: "indexing_actor",
        JobType.SCRAPE: "scraping_actor",
        JobType.DOWNLOAD: "downloader_actor",
        JobType.SYMLINK: "symlinker_actor",
        JobType.UPDATE: "updater_actor",
        JobType.POST_PROCESS: "postprocessing_actor",
    }[job_type]


def _hash(s: str) -> int:
    return int(hashlib.md5(s.encode("utf-8")).hexdigest(), 16)


def select_partition(job_type: JobType, key: str) -> int:
    count = PARTITION_COUNTS.get(job_type, 1)
    if count <= 1:
        return 0
    return _hash(key) % count


def resolve_partitioned_names(job_type: JobType, partition_index: int) -> Tuple[str, str]:
    """Return (queue_name, actor_name) for the given job_type and partition index."""
    base_q = _base_queue_name(job_type)
    base_a = _base_actor_name(job_type)
    qname, aname = f"{base_q}.p{partition_index}", f"{base_a}_p{partition_index}"
    if os.getenv("RIVEN_QUEUE_DEBUG", "0") == "1":
        logger.debug(f"resolve_names: {job_type} base={base_q} idx={partition_index} -> {qname}/{aname}")
    return (qname, aname)


def queue_base_and_count(job_type: JobType) -> Tuple[str, int]:
    return _base_queue_name(job_type), PARTITION_COUNTS.get(job_type, 1)


def all_partitioned_queue_names() -> Dict[str, int]:
    """Map of base queue name -> partition count (>=1)."""
    return {
        _base_queue_name(jt): PARTITION_COUNTS.get(jt, 1)
        for jt in JobType
    }

