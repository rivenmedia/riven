from datetime import datetime, timedelta
from unittest.mock import patch

from program.services.downloaders import _ThrottledLog


def test_throttled_log_suppresses_duplicates_within_interval():
    throttled = _ThrottledLog(interval_seconds=60.0)
    fixed_now = datetime(2026, 5, 16, 15, 0, 0)

    with patch("program.services.downloaders.logger") as mock_logger:
        with patch(
            "program.services.downloaders.datetime"
        ) as mock_datetime:
            mock_datetime.now.return_value = fixed_now

            throttled.warning("key", "first")
            throttled.warning("key", "second")
            throttled.warning("key", "third")

    assert mock_logger.warning.call_count == 1
    mock_logger.warning.assert_called_with("first")


def test_throttled_log_reports_suppressed_count_after_interval():
    throttled = _ThrottledLog(interval_seconds=60.0)
    t0 = datetime(2026, 5, 16, 15, 0, 0)
    t1 = t0 + timedelta(seconds=61)

    with patch("program.services.downloaders.logger") as mock_logger:
        with patch(
            "program.services.downloaders.datetime"
        ) as mock_datetime:
            mock_datetime.now.side_effect = [t0, t0, t1]

            throttled.warning("key", "first")
            throttled.warning("key", "ignored")
            throttled.warning("key", "second")

    assert mock_logger.warning.call_count == 2
    mock_logger.warning.assert_any_call("first")
    mock_logger.warning.assert_any_call("second (1 similar events suppressed)")
