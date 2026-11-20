"""Figures for the maintenance check-up (docs/MAINTENANCE.md step 1), printed into the daily backup job's log.

Once the backups are locked (ARCHIVE_PASSPHRASE), a check-up can't open them; these counts let it judge completeness
without the archive: readings per source and MYT day (144 for 10-minute sources, 48 for half-hourly ones) and every
stop in collection longer than 12 minutes. Only counts and times, which the website shows anyway.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import and_, select
from sqlalchemy.engine import Engine

from . import db
from .timeutil import MYT, ensure_utc

STOP = timedelta(minutes=12)


def summary(engine: Engine, days: int = 8, today: date | None = None) -> dict:
    today = today or datetime.now(MYT).date()
    first = today - timedelta(days=days - 1)
    since = datetime.combine(first, datetime.min.time(), MYT).astimezone(timezone.utc)
    s, o, r = db.series.c, db.observations.c, db.collection_runs.c
    times: dict[str, set] = defaultdict(set)
    with engine.connect() as conn:
        rows = conn.execute(select(s.key, o.obs_time).join(db.series, s.id == o.series_id).where(and_(
            s.kind == "actual", s.is_demo.is_(False), o.quality != "frozen", o.obs_time >= since)))
        for key, t in rows:
            times[key.split(".", 1)[0]].add(ensure_utc(t))
        runs = sorted(ensure_utc(t) for (t,) in conn.execute(select(r.started_at).where(and_(
            r.adapter == "system_demand", r.started_at >= since))))
    day_list = [(first + timedelta(days=i)).isoformat() for i in range(days)]
    per_source = {}
    for src in sorted(times):
        c = Counter(t.astimezone(MYT).date().isoformat() for t in times[src])
        per_source[src] = {d: c.get(d, 0) for d in day_list}
    stops = [{"from_myt": a.astimezone(MYT).strftime("%Y-%m-%d %H:%M"), "to_myt": b.astimezone(MYT).strftime("%Y-%m-%d %H:%M"),
              "minutes": int((b - a).total_seconds() // 60)} for a, b in zip(runs, runs[1:]) if b - a > STOP]
    return {"days": day_list, "readings_per_day": per_source, "collection_stops_over_12_min": stops,
            "collection_runs": len(runs)}


def as_text(result: dict) -> str:
    days = result["days"]
    lines = ["Readings per source and day (MYT):", "source".ljust(24) + " ".join(d[5:] for d in days)]
    for src, c in result["readings_per_day"].items():
        lines.append(src.ljust(24) + " ".join(str(c[d]).rjust(5) for d in days))
    stops = result["collection_stops_over_12_min"]
    lines.append(f"Collection stops over 12 minutes ({len(stops)}, from {result['collection_runs']} runs):")
    lines += [f"  {x['from_myt']} -> {x['to_myt']} MYT ({x['minutes']} min)" for x in stops] or ["  none"]
    return "\n".join(lines)
