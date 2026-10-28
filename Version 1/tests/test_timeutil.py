from datetime import date, datetime, timezone

import pytest

from gso_archive.timeutil import (
    ensure_utc,
    gso_date_param,
    myt_day_bounds_utc,
    myt_today,
    parse_source_timestamp,
    to_myt_iso,
)

UTC = timezone.utc


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("2026-10-27T00:30:00", datetime(2026, 10, 26, 16, 30, tzinfo=UTC)),  # naive → MYT
        ("2026-10-27 08:00", datetime(2026, 10, 27, 0, 0, tzinfo=UTC)),
        ("27/10/2026 13:15", datetime(2026, 10, 27, 5, 15, tzinfo=UTC)),
        ("27/10/2026 01:15:00 PM", datetime(2026, 10, 27, 5, 15, tzinfo=UTC)),
        ("2026-10-27T00:00:00Z", datetime(2026, 10, 27, 0, 0, tzinfo=UTC)),
        ("2026-10-27T00:00:00+08:00", datetime(2026, 10, 26, 16, 0, tzinfo=UTC)),
        ("/Date(1761523200000)/", datetime(2025, 10, 27, 0, 0, tzinfo=UTC)),
    ],
)
def test_parse_source_timestamp(raw, expected):
    assert parse_source_timestamp(raw) == expected


@pytest.mark.parametrize("raw", ["", None, "yesterday", "32/13/2026 00:00", 12345])
def test_unparseable_timestamps_raise(raw):
    with pytest.raises(ValueError):
        parse_source_timestamp(raw)


def test_midnight_myt_belongs_to_previous_utc_day():
    t = parse_source_timestamp("2026-01-01T00:00:00")
    assert t.date() == date(2025, 12, 31) and t.hour == 16


def test_day_bounds_and_params():
    start, end = myt_day_bounds_utc(date(2026, 10, 27))
    assert start == datetime(2026, 10, 26, 16, tzinfo=UTC)
    assert (end - start).total_seconds() == 86400
    assert gso_date_param(date(2026, 3, 5)) == "05/03/2026"


def test_myt_today_rolls_over_at_1600_utc():
    assert myt_today(datetime(2026, 10, 27, 15, 59, tzinfo=UTC)) == date(2026, 10, 27)
    assert myt_today(datetime(2026, 10, 27, 16, 0, tzinfo=UTC)) == date(2026, 10, 28)


def test_ensure_utc_and_display():
    naive_from_sqlite = datetime(2026, 10, 27, 4, 0)
    assert ensure_utc(naive_from_sqlite).tzinfo == UTC
    assert to_myt_iso(naive_from_sqlite) == "2026-10-27T12:00:00+08:00"
