"""Read-side queries and derived metrics.

Conventions:
* Gaps are explicit: a gap longer than 1.5× the series' expected interval is
  emitted as a null point so charts break the line. Missing ≠ zero.
* Daily metrics use Malaysia calendar days (Asia/Kuala_Lumpur).
* Energy (MWh) is a *derived* trapezoidal integral over consecutive points
  that are not separated by a gap; completeness says how much of the day
  was covered.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from sqlalchemy import and_, desc, func, select
from sqlalchemy.engine import Connection

from . import db, store
from .adapters import ADAPTERS, NOT_IMPLEMENTED
from .timeutil import MYT, ensure_utc, myt_day_bounds_utc, to_utc_iso, utcnow

DEFAULT_INTERVAL_S = 1800  # used only until a series has enough points to infer its interval
MAX_POINTS = 20000


@dataclass
class SeriesInfo:
    id: int
    key: str
    name: str
    unit: str
    kind: str
    interval_s: int | None
    dataset_key: str
    category: str
    verification: str
    is_demo: bool
    auto_discovered: bool


def _series_query():
    s, d = db.series.c, db.datasets.c
    return select(
        s.id, s.key, s.name, s.unit, s.kind, s.expected_interval_s, s.is_demo, s.auto_discovered,
        d.key.label("dataset_key"), d.category, d.verification,
    ).join(db.datasets, db.datasets.c.id == db.series.c.dataset_id)


def _to_info(row) -> SeriesInfo:
    return SeriesInfo(row.id, row.key, row.name, row.unit, row.kind, row.expected_interval_s,
                      row.dataset_key, row.category, row.verification, bool(row.is_demo), bool(row.auto_discovered))


def get_series(conn: Connection, key: str) -> SeriesInfo | None:
    row = conn.execute(_series_query().where(db.series.c.key == key)).first()
    return _to_info(row) if row else None


def meta(conn: Connection) -> dict:
    o = db.observations.c
    stats = {
        row.series_id: row
        for row in conn.execute(
            select(o.series_id, func.count().label("n"), func.min(o.obs_time).label("first"),
                   func.max(o.obs_time).label("last")).group_by(o.series_id)
        )
    }
    fc = db.forecasts.c
    fstats = {
        row.series_id: row
        for row in conn.execute(
            select(fc.series_id, func.count().label("n"), func.min(fc.target_time).label("first"),
                   func.max(fc.target_time).label("last")).group_by(fc.series_id)
        )
    }
    series_out = []
    for row in conn.execute(_series_query().order_by(db.series.c.key)):
        st = stats.get(row.id) or fstats.get(row.id)
        latest_value = None
        if st and st.last is not None and row.kind != "forecast":
            latest_value = conn.execute(
                select(o.value, o.quality).where(and_(o.series_id == row.id, o.obs_time == st.last))
            ).first()
        series_out.append({
            "key": row.key, "name": row.name, "unit": row.unit, "kind": row.kind,
            "dataset": row.dataset_key, "category": row.category, "verification": row.verification,
            "is_demo": bool(row.is_demo), "auto_discovered": bool(row.auto_discovered),
            "interval_s": row.expected_interval_s,
            "count": st.n if st else 0,
            "first": to_utc_iso(st.first) if st and st.first else None,
            "last": to_utc_iso(st.last) if st and st.last else None,
            "latest_value": latest_value.value if latest_value else None,
            "latest_quality": latest_value.quality if latest_value else None,
        })
    datasets = [
        {"key": r.key, "name": r.name, "category": r.category, "source_url": r.source_url,
         "verification": r.verification, "description": r.description, "is_demo": bool(r.is_demo)}
        for r in conn.execute(select(db.datasets).order_by(db.datasets.c.key))
    ]
    known = {d["key"] for d in datasets}
    for spec in ADAPTERS.values():
        if spec.key not in known:
            datasets.append({"key": spec.key, "name": spec.name, "category": spec.category,
                             "source_url": spec.page, "verification": spec.verification,
                             "description": spec.description, "is_demo": False, "no_data_yet": True})
    return {
        "generated_at": to_utc_iso(utcnow()),
        "is_demo": any(s["is_demo"] for s in series_out),
        "datasets": datasets,
        "series": series_out,
        "not_implemented": NOT_IMPLEMENTED,
    }


def points(conn: Connection, info: SeriesInfo, start: datetime, end: datetime, max_points: int = MAX_POINTS) -> dict:
    """Return [t, value|null, quality] rows for [start, end), with gap markers."""
    if info.kind == "forecast":
        return forecast_points(conn, info, start, end)
    o = db.observations.c
    rows = conn.execute(
        select(o.obs_time, o.value, o.quality, o.revision_count)
        .where(and_(o.series_id == info.id, o.obs_time >= start, o.obs_time < end))
        .order_by(o.obs_time)
    ).all()
    interval = info.interval_s or DEFAULT_INTERVAL_S
    data: list[list] = []
    prev: datetime | None = None
    for r in rows:
        t = ensure_utc(r.obs_time)
        if prev is not None and (t - prev).total_seconds() > 1.5 * interval:
            data.append([to_utc_iso(prev + timedelta(seconds=interval)), None, "gap"])
        data.append([to_utc_iso(t), r.value, r.quality if r.revision_count == 1 else f"{r.quality}|revised"])
        prev = t
    downsampled = 0
    if len(data) > max_points:
        data, downsampled = _downsample(data, max_points), len(data)
    return {"series": info.key, "unit": info.unit, "interval_s": info.interval_s, "kind": info.kind,
            "points": data, "downsampled_from": downsampled or None, "is_demo": info.is_demo}


def _downsample(data: list[list], target: int) -> list[list]:
    """Bucket mean that preserves gaps (a bucket containing any gap emits a null)."""
    size = -(-len(data) // target)
    out = []
    for i in range(0, len(data), size):
        chunk = data[i:i + size]
        values = [p[1] for p in chunk if p[1] is not None]
        if len(values) < len(chunk) or not values:
            out.append([chunk[0][0], None, "gap"])
        else:
            out.append([chunk[0][0], sum(values) / len(values), "downsampled"])
    return out


def forecast_points(conn: Connection, info: SeriesInfo, start: datetime, end: datetime) -> dict:
    """Latest-issued forecast value for each target time."""
    fc = db.forecasts.c
    rows = conn.execute(
        select(fc.target_time, fc.issue_time, fc.value, fc.issue_time_inferred)
        .where(and_(fc.series_id == info.id, fc.target_time >= start, fc.target_time < end))
        .order_by(fc.target_time, fc.issue_time)
    ).all()
    latest: dict[datetime, tuple] = {}
    for r in rows:
        latest[ensure_utc(r.target_time)] = r
    data = [[to_utc_iso(t), r.value, "forecast", to_utc_iso(r.issue_time)] for t, r in sorted(latest.items())]
    return {"series": info.key, "unit": info.unit, "interval_s": info.interval_s, "kind": "forecast",
            "points": data, "issue_time_inferred": any(r.issue_time_inferred for r in rows), "is_demo": info.is_demo}


def daily(conn: Connection, info: SeriesInfo, start_day: date, end_day: date) -> list[dict]:
    """Per-MYT-day statistics for [start_day, end_day] inclusive."""
    start, _ = myt_day_bounds_utc(start_day)
    _, end = myt_day_bounds_utc(end_day)
    o = db.observations.c
    rows = conn.execute(
        select(o.obs_time, o.value).where(and_(o.series_id == info.id, o.obs_time >= start, o.obs_time < end))
        .order_by(o.obs_time)
    ).all()
    interval = info.interval_s or DEFAULT_INTERVAL_S
    per_day: dict[date, list[tuple[datetime, float]]] = defaultdict(list)
    for r in rows:
        t = ensure_utc(r.obs_time)
        per_day[t.astimezone(MYT).date()].append((t, r.value))
    expected = max(1, round(86400 / interval))
    out = []
    day = start_day
    while day <= end_day:
        pts = per_day.get(day, [])
        if not pts:
            out.append({"date": day.isoformat(), "count": 0, "expected": expected, "completeness": 0.0,
                        "max": None, "max_time": None, "min": None, "mean": None, "energy_mwh": None})
        else:
            values = [v for _, v in pts]
            peak_t, peak_v = max(pts, key=lambda p: p[1])
            energy = 0.0
            for (t0, v0), (t1, v1) in zip(pts, pts[1:]):
                dt = (t1 - t0).total_seconds()
                if dt <= 1.5 * interval:
                    energy += (v0 + v1) / 2 * dt / 3600
            out.append({
                "date": day.isoformat(), "count": len(pts), "expected": expected,
                "completeness": round(min(1.0, len(pts) / expected), 4),
                "max": peak_v, "max_time": to_utc_iso(peak_t), "min": min(values),
                "mean": sum(values) / len(values),
                "energy_mwh": round(energy, 3) if info.unit == "MW" else None,
            })
        day += timedelta(days=1)
    return out


def rollup(days: list[dict], period: str) -> list[dict]:
    """Aggregate daily rows into week/month/year rows."""
    buckets: dict[str, list[dict]] = defaultdict(list)
    for d in days:
        day = date.fromisoformat(d["date"])
        if period == "week":
            iso = day.isocalendar()
            key = f"{iso.year}-W{iso.week:02d}"
        elif period == "month":
            key = f"{day.year}-{day.month:02d}"
        elif period == "year":
            key = str(day.year)
        else:
            key = d["date"]
        buckets[key].append(d)
    out = []
    for key in sorted(buckets):
        group = buckets[key]
        with_data = [g for g in group if g["count"]]
        peak = max(with_data, key=lambda g: g["max"]) if with_data else None
        energies = [g["energy_mwh"] for g in with_data if g["energy_mwh"] is not None]
        out.append({
            "period": key, "days": len(group), "days_with_data": len(with_data),
            "completeness": round(sum(g["completeness"] for g in group) / len(group), 4),
            "max": peak["max"] if peak else None, "max_time": peak["max_time"] if peak else None,
            "mean_daily_peak": (sum(g["max"] for g in with_data) / len(with_data)) if with_data else None,
            "energy_mwh": round(sum(energies), 3) if energies else None,
        })
    return out


def revisions(conn: Connection, info: SeriesInfo, start: datetime, end: datetime, limit: int = 1000) -> list[dict]:
    r = db.observation_revisions.c
    rows = conn.execute(
        select(r.obs_time, r.value, r.previous_value, r.collected_at, r.run_id)
        .where(and_(r.series_id == info.id, r.obs_time >= start, r.obs_time < end, r.previous_value.is_not(None)))
        .order_by(desc(r.collected_at)).limit(limit)
    ).all()
    return [{"obs_time": to_utc_iso(x.obs_time), "value": x.value, "previous_value": x.previous_value,
             "revised_at": to_utc_iso(x.collected_at), "run_id": x.run_id} for x in rows]


def status(conn: Connection, configured_adapters: list[str], live_enabled: bool) -> dict:
    """Monitoring summary: collection health is reported separately from data freshness."""
    now = utcnow()
    r = db.collection_runs.c
    adapters_out = []
    for key in sorted(set(configured_adapters) | set(ADAPTERS)):
        recent = conn.execute(
            select(db.collection_runs).where(r.adapter == key).order_by(desc(r.started_at)).limit(50)
        ).all()
        consecutive_failures = 0
        for run in recent:
            if run.status == "failed":
                consecutive_failures += 1
            elif run.status == "success":
                break
        last = recent[0] if recent else None
        last_ok = next((x for x in recent if x.status == "success"), None)
        day_ago = now - timedelta(hours=24)
        last24 = [x for x in recent if ensure_utc(x.started_at) >= day_ago]
        durations = [x.duration_ms for x in last24 if x.duration_ms is not None]
        adapters_out.append({
            "adapter": key,
            "enabled": key in configured_adapters,
            "verification": ADAPTERS[key].verification if key in ADAPTERS else "unknown",
            "last_run_at": to_utc_iso(last.started_at) if last else None,
            "last_status": last.status if last else None,
            "last_error": (f"{last.error_type}: {last.error_message}" if last and last.status == "failed" else None),
            "last_success_at": to_utc_iso(last_ok.started_at) if last_ok else None,
            "last_duration_ms": last.duration_ms if last else None,
            "consecutive_failures": consecutive_failures,
            "runs_24h": len(last24),
            "failures_24h": sum(x.status == "failed" for x in last24),
            "new_records_24h": sum(x.records_new or 0 for x in last24),
            "revised_records_24h": sum(x.records_revised or 0 for x in last24),
            "median_duration_ms_24h": sorted(durations)[len(durations) // 2] if durations else None,
            "schema_changed_recently": any(x.schema_changed for x in recent),
            "parse_errors_24h": sum(x.error_type in ("parse_error", "schema_error") for x in last24),
        })

    o = db.observations.c
    freshness = []
    for row in conn.execute(_series_query().where(db.series.c.kind != "forecast").order_by(db.series.c.key)):
        latest = conn.execute(select(func.max(o.obs_time)).where(o.series_id == row.id)).scalar()
        interval = row.expected_interval_s or DEFAULT_INTERVAL_S
        window_start = now - timedelta(hours=24)
        got = conn.execute(select(func.count()).where(and_(o.series_id == row.id, o.obs_time >= window_start))).scalar()
        expected = int(86400 / interval) if row.kind != "capacity" else 1
        age = (now - ensure_utc(latest)).total_seconds() if latest else None
        freshness.append({
            "series": row.key, "kind": row.kind, "latest_obs_time": to_utc_iso(latest) if latest else None,
            "age_s": int(age) if age is not None else None, "interval_s": row.expected_interval_s,
            "observed_24h": got, "expected_24h": expected,
            "missing_24h": max(0, expected - got) if row.kind != "capacity" else None,
            "stale": age is None or age > max(3 * interval, 3600) if row.kind != "capacity" else (age is None or age > 3 * 86400),
        })

    heartbeat = store.get_state(conn, "collector_heartbeat")
    backup = store.get_state(conn, "last_backup")
    totals = {
        "observations": conn.execute(select(func.count()).select_from(db.observations)).scalar(),
        "revisions": conn.execute(
            select(func.count()).select_from(db.observation_revisions).where(db.observation_revisions.c.previous_value.is_not(None))
        ).scalar(),
        "forecasts": conn.execute(select(func.count()).select_from(db.forecasts)).scalar(),
        "runs": conn.execute(select(func.count()).select_from(db.collection_runs)).scalar(),
        "raw_snapshots": conn.execute(select(func.count()).select_from(db.raw_snapshots)).scalar(),
    }
    return {
        "generated_at": to_utc_iso(now),
        "database": {"ok": True, "dialect": conn.dialect.name},
        "live_enabled": live_enabled,
        "collector_heartbeat": heartbeat,
        "backup": backup,
        "adapters": adapters_out,
        "freshness": freshness,
        "totals": totals,
        "not_implemented": NOT_IMPLEMENTED,
    }


def observed_interval(conn: Connection, sample: int = 30) -> int | None:
    """Median seconds between recent scheduled collection cycles (None until there are enough)."""
    r = db.collection_runs.c
    adapter = conn.execute(
        select(r.adapter).where(r.trigger == "schedule").order_by(desc(r.started_at)).limit(1)
    ).scalar()
    if adapter is None:
        return None
    times = [ensure_utc(t) for (t,) in conn.execute(
        select(r.started_at).where(and_(r.trigger == "schedule", r.adapter == adapter))
        .order_by(desc(r.started_at)).limit(sample + 1))]
    gaps = sorted(int((a - b).total_seconds()) for a, b in zip(times, times[1:]) if a > b)
    if len(gaps) < 3:
        return None
    return gaps[len(gaps) // 2]
