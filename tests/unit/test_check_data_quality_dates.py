from argparse import Namespace
from datetime import datetime, timedelta, timezone

from scripts.check_data_quality import calculate_date_range


def test_days_range_uses_completed_utc_day():
    today_utc = datetime.now(timezone.utc).date()
    expected = (today_utc - timedelta(days=1)).strftime("%Y-%m-%d")

    start, end = calculate_date_range(
        Namespace(days=1, start=None, end=None)
    )

    assert start == expected
    assert end == expected


def test_days_range_spans_from_completed_utc_day():
    today_utc = datetime.now(timezone.utc).date()
    expected_end = today_utc - timedelta(days=1)
    expected_start = expected_end - timedelta(days=2)

    start, end = calculate_date_range(
        Namespace(days=3, start=None, end=None)
    )

    assert start == expected_start.strftime("%Y-%m-%d")
    assert end == expected_end.strftime("%Y-%m-%d")
