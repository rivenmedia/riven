from datetime import datetime, timedelta, timezone

from program.utils import format_api_datetime


def test_format_api_datetime_naive_utc_suffix():
    dt = datetime(2026, 5, 20, 3, 33, 55)
    assert format_api_datetime(dt) == "2026-05-20T03:33:55.000Z"


def test_format_api_datetime_converts_offset_to_utc():
    dt = datetime(2026, 5, 20, 4, 33, 55, tzinfo=timezone(timedelta(hours=-4)))
    assert format_api_datetime(dt) == "2026-05-20T08:33:55.000Z"
