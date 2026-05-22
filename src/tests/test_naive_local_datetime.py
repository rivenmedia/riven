"""Guard against naive vs aware datetime comparison crashes."""

from datetime import UTC, datetime, timedelta

import pytest

from program.utils import naive_local_datetime


def test_naive_local_datetime_strips_utc_awareness():
    aware = datetime.now(UTC)
    naive = naive_local_datetime(aware)
    assert naive.tzinfo is None
    assert naive <= datetime.now()


def test_naive_local_datetime_none_passthrough():
    assert naive_local_datetime(None) is None


def test_compare_aware_scraped_at_with_now():
    scraped_at = datetime.now(UTC) - timedelta(hours=1)
    assert (datetime.now() - naive_local_datetime(scraped_at)).total_seconds() > 0


def test_sort_mixed_run_at_keys():
    naive = datetime.now()
    aware = datetime.now(UTC)
    keys = [
        (0, naive_local_datetime(naive)),
        (0, naive_local_datetime(aware)),
    ]
    keys.sort()


def test_max_run_at_mixed():
    naive = datetime.now()
    aware = datetime.now(UTC)
    assert max(naive_local_datetime(naive), naive_local_datetime(aware))
