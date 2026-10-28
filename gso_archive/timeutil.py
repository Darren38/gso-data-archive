"""Timestamp handling.

Storage is always timezone-aware UTC. GSO publishes naive local timestamps
which are interpreted as Malaysia Standard Time (UTC+8, no DST).
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

MYT = ZoneInfo("Asia/Kuala_Lumpur")
UTC = timezone.utc

# ASP.NET JSON date, e.g. "/Date(1700000000000)/" or "/Date(1700000000000+0800)/"
_MS_DATE = re.compile(r"^/Date\((-?\d+)([+-]\d{4})?\)/$")

_FORMATS = (
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%dT%H:%M",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%d/%m/%Y %H:%M:%S",
    "%d/%m/%Y %H:%M",
    "%d/%m/%Y %I:%M:%S %p",
    "%d/%m/%Y %I:%M %p",
)


def utcnow() -> datetime:
    return datetime.now(UTC)


def parse_source_timestamp(value: object) -> datetime:
    """Parse a GSO timestamp into aware UTC. Naive values are taken as MYT.

    Raises ValueError for anything unparseable — callers must never guess.
    """
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"empty or non-string timestamp: {value!r}")
    text = value.strip()

    match = _MS_DATE.match(text)
    if match:
        # Epoch milliseconds are UTC by definition; the offset suffix is informational.
        return datetime.fromtimestamp(int(match.group(1)) / 1000, tz=UTC)

    parsed: datetime | None = None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        for fmt in _FORMATS:
            try:
                parsed = datetime.strptime(text, fmt)
                break
            except ValueError:
                continue
    if parsed is None:
        raise ValueError(f"unrecognised timestamp format: {value!r}")
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=MYT)
    return parsed.astimezone(UTC)


def ensure_utc(dt: datetime) -> datetime:
    """Normalise a datetime read back from the database (SQLite drops tzinfo)."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def myt_today(now: datetime | None = None) -> date:
    return (now or utcnow()).astimezone(MYT).date()


def myt_day_bounds_utc(day: date) -> tuple[datetime, datetime]:
    start = datetime(day.year, day.month, day.day, tzinfo=MYT)
    return start.astimezone(UTC), (start + timedelta(days=1)).astimezone(UTC)


def gso_date_param(day: date) -> str:
    """GSO PageMethods take dates as DD/MM/YYYY."""
    return day.strftime("%d/%m/%Y")


def to_myt_iso(dt: datetime) -> str:
    return ensure_utc(dt).astimezone(MYT).isoformat()


def to_utc_iso(dt: datetime) -> str:
    return ensure_utc(dt).isoformat().replace("+00:00", "Z")
