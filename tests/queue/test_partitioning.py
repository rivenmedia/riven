import pytest

from program.queue.partitioning import PARTITION_COUNTS, resolve_partitioned_names
from program.queue.models import JobType


def test_partitioned_names_consistency():
    base_map = {
        JobType.INDEX: "indexing",
        JobType.SCRAPE: "scraping",
        JobType.DOWNLOAD: "downloader",
        JobType.SYMLINK: "symlinker",
        JobType.UPDATE: "updater",
        JobType.POST_PROCESS: "postprocessing",
    }
    for jt, base in base_map.items():
        count = max(1, PARTITION_COUNTS.get(jt, 1))
        for p in range(count):
            q, a = resolve_partitioned_names(jt, p)
            assert q == f"{base}.p{p}"
            assert a.endswith(f"_p{p}")

