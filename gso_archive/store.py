"""Persistence: datasets/series registration, observation upserts with revision
history, forecasts, collection-run bookkeeping.

Rules enforced here:
* An observation is never deleted or silently overwritten. A changed value
  updates the current row *and* appends to `observation_revisions`.
* Re-collecting an identical value is a no-op (deduplication).
* Missing source values never reach this module (they are counted, not stored).
"""

from __future__ import annotations

import statistics
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import and_, desc, func, select, update
from sqlalchemy.engine import Connection

from . import db
from .adapters.base import AdapterSpec, FieldSpec, Reading
from .timeutil import ensure_utc, utcnow


@dataclass
class ApplyStats:
    new: int = 0
    revised: int = 0
    unchanged: int = 0
    suspect: int = 0
    duplicates_in_payload: int = 0
    future: int = 0  # readings dated after they were collected (never stored)
    latest_obs_time: datetime | None = None


FUTURE_TOLERANCE = timedelta(minutes=15)


def _same(a: float, b: float) -> bool:
    return abs(a - b) <= 1e-9 * max(1.0, abs(a), abs(b))


def ensure_dataset(conn: Connection, spec: AdapterSpec, *, is_demo: bool = False) -> int:
    row = conn.execute(select(db.datasets.c.id).where(db.datasets.c.key == spec.key)).first()
    values = dict(
        name=spec.name,
        category=spec.category,
        source_url=spec.page,
        verification="demo" if is_demo else spec.verification,
        description=spec.description,
        is_demo=is_demo,
    )
    if row:
        conn.execute(update(db.datasets).where(db.datasets.c.id == row.id).values(**values))
        return row.id
    return conn.execute(db.datasets.insert().values(key=spec.key, created_at=utcnow(), **values)).inserted_primary_key[0]


def ensure_series(
    conn: Connection,
    dataset_id: int,
    key: str,
    fspec: FieldSpec,
    source_field: str,
    *,
    auto_discovered: bool,
    is_demo: bool = False,
    latitude: float | None = None,
    longitude: float | None = None,
) -> int:
    row = conn.execute(select(db.series.c.id, db.series.c.latitude, db.series.c.longitude).where(db.series.c.key == key)).first()
    if row:
        if latitude is not None and (row.latitude, row.longitude) != (latitude, longitude):
            conn.execute(update(db.series).where(db.series.c.id == row.id).values(latitude=latitude, longitude=longitude))
        return row.id
    return conn.execute(
        db.series.insert().values(
            dataset_id=dataset_id,
            key=key,
            name=fspec.name,
            unit=fspec.unit,
            kind=fspec.kind,
            source_field=source_field,
            auto_discovered=auto_discovered,
            is_demo=is_demo,
            created_at=utcnow(),
            latitude=latitude,
            longitude=longitude,
        )
    ).inserted_primary_key[0]


def resolve_series(
    conn: Connection, spec: AdapterSpec, dataset_id: int, readings: Iterable[Reading], *, is_demo: bool = False
) -> dict[str, int]:
    ids: dict[str, int] = {}
    for r in readings:
        if r.series in ids:
            continue
        if r.name:
            fspec, auto = FieldSpec(r.series, r.name, r.unit or spec.default_unit, r.kind), False
        elif r.source_field in spec.fields:
            fspec, auto = spec.fields[r.source_field], False
        elif r.series in spec.fields:  # transforms that name series by key (e.g. GSO's "$"-joined answers)
            fspec, auto = spec.fields[r.series], False
        elif r.kind == "capacity":
            fspec, auto = FieldSpec(r.series, f"Installed capacity — {r.source_field}", spec.default_unit, "capacity"), False
            if r.source_field == "*":
                fspec = FieldSpec(r.series, "Installed capacity — total", spec.default_unit, "capacity")
        else:
            fspec, auto = spec.field_spec(r.source_field), True
        ids[r.series] = ensure_series(
            conn, dataset_id, spec.series_key(r.series), fspec, r.source_field, auto_discovered=auto, is_demo=is_demo,
            latitude=r.latitude, longitude=r.longitude,
        )
    return ids


def apply_readings(
    conn: Connection,
    readings: list[Reading],
    series_ids: dict[str, int],
    *,
    run_id: int | None,
    snapshot_id: int | None,
    collected_at: datetime,
) -> ApplyStats:
    stats = ApplyStats()
    # A reading can't be from the future. GSO's "last available" time once dated night-time solar-farm readings at
    # 07:00 the next morning; anything stamped more than 15 minutes after collection is refused, never stored.
    too_late = ensure_utc(collected_at) + FUTURE_TOLERANCE
    # Deduplicate within the payload: last occurrence wins, but count it.
    latest: dict[tuple[int, datetime], Reading] = {}
    for r in readings:
        if r.kind != "forecast" and ensure_utc(r.obs_time) > too_late:
            stats.future += 1
            continue
        key = (series_ids[r.series], ensure_utc(r.obs_time))
        if key in latest:
            stats.duplicates_in_payload += 1
        latest[key] = r

    by_series: dict[int, dict[datetime, Reading]] = {}
    for (sid, t), r in latest.items():
        by_series.setdefault(sid, {})[t] = r

    for sid, points in by_series.items():
        actual = {t: r for t, r in points.items() if r.kind != "forecast"}
        forecast = {t: r for t, r in points.items() if r.kind == "forecast"}
        if actual:
            _apply_actual(conn, sid, actual, stats, run_id, snapshot_id, collected_at)
        if forecast:
            _apply_forecast(conn, sid, forecast, stats, run_id, collected_at)
        update_expected_interval(conn, sid)
    return stats


def _apply_actual(conn, sid, points, stats, run_id, snapshot_id, collected_at) -> None:
    lo, hi = min(points), max(points)
    obs = db.observations.c
    existing = {
        ensure_utc(row.obs_time): row
        for row in conn.execute(
            select(obs.obs_time, obs.value, obs.revision_count).where(
                and_(obs.series_id == sid, obs.obs_time >= lo, obs.obs_time <= hi)
            )
        )
    }
    new_rows, revision_rows = [], []
    for t, r in sorted(points.items()):
        if r.quality != "ok":
            stats.suspect += 1
        if stats.latest_obs_time is None or t > stats.latest_obs_time:
            stats.latest_obs_time = t
        cur = existing.get(t)
        if cur is None:
            stats.new += 1
            new_rows.append(
                dict(series_id=sid, obs_time=t, value=r.value, quality=r.quality, first_collected_at=collected_at,
                     last_changed_at=collected_at, revision_count=1, last_run_id=run_id)
            )
            revision_rows.append(
                dict(series_id=sid, obs_time=t, value=r.value, previous_value=None, quality=r.quality,
                     collected_at=collected_at, run_id=run_id, raw_snapshot_id=snapshot_id)
            )
        elif _same(cur.value, r.value):
            stats.unchanged += 1
        else:
            stats.revised += 1
            conn.execute(
                update(db.observations)
                .where(and_(obs.series_id == sid, obs.obs_time == t))
                .values(value=r.value, quality=r.quality, last_changed_at=collected_at,
                        revision_count=cur.revision_count + 1, last_run_id=run_id)
            )
            revision_rows.append(
                dict(series_id=sid, obs_time=t, value=r.value, previous_value=cur.value, quality=r.quality,
                     collected_at=collected_at, run_id=run_id, raw_snapshot_id=snapshot_id)
            )
    if new_rows:
        conn.execute(db.observations.insert(), new_rows)
    if revision_rows:
        conn.execute(db.observation_revisions.insert(), revision_rows)


def _apply_forecast(conn, sid, points, stats, run_id, collected_at) -> None:
    """Store a forecast value only when it differs from the latest stored issue for that target."""
    fc = db.forecasts.c
    for t, r in sorted(points.items()):
        prev = conn.execute(
            select(fc.value).where(and_(fc.series_id == sid, fc.target_time == t)).order_by(desc(fc.issue_time)).limit(1)
        ).first()
        if prev is not None and _same(prev.value, r.value):
            stats.unchanged += 1
            continue
        stats.new += 1
        conn.execute(
            db.forecasts.insert().values(series_id=sid, target_time=t, issue_time=collected_at,
                                         issue_time_inferred=True, value=r.value, collected_at=collected_at,
                                         run_id=run_id)
        )


def update_expected_interval(conn: Connection, sid: int, sample: int = 300) -> None:
    obs = db.observations.c
    times = [
        ensure_utc(row[0])
        for row in conn.execute(
            select(obs.obs_time).where(obs.series_id == sid).order_by(desc(obs.obs_time)).limit(sample)
        )
    ]
    if len(times) < 3:
        return
    diffs = [int((a - b).total_seconds()) for a, b in zip(times, times[1:]) if a != b]
    diffs = [d for d in diffs if d > 0]
    if diffs:
        conn.execute(update(db.series).where(db.series.c.id == sid).values(expected_interval_s=int(statistics.median(diffs))))


# ---------------------------------------------------------------- runs


def start_run(conn: Connection, adapter: str, target_date, trigger: str) -> int:
    return conn.execute(
        db.collection_runs.insert().values(adapter=adapter, target_date=target_date, trigger=trigger,
                                           started_at=utcnow(), status="running")
    ).inserted_primary_key[0]


def finish_run(conn: Connection, run_id: int, **values) -> None:
    values.setdefault("finished_at", utcnow())
    conn.execute(update(db.collection_runs).where(db.collection_runs.c.id == run_id).values(**values))


def last_signature(conn: Connection, adapter: str) -> str | None:
    r = db.collection_runs.c
    row = conn.execute(
        select(r.schema_signature)
        .where(and_(r.adapter == adapter, r.status == "success", r.schema_signature.is_not(None), r.schema_signature != ""))
        .order_by(desc(r.started_at))
        .limit(1)
    ).first()
    return row[0] if row else None


def last_success(conn: Connection, adapter: str, target_date=None) -> datetime | None:
    r = db.collection_runs.c
    cond = and_(r.adapter == adapter, r.status == "success")
    if target_date is not None:
        cond = and_(cond, r.target_date == target_date)
    value = conn.execute(select(func.max(r.started_at)).where(cond)).scalar()
    return ensure_utc(value) if value else None


def set_state(conn: Connection, key: str, value: dict) -> None:
    now = utcnow()
    exists = conn.execute(select(db.system_state.c.key).where(db.system_state.c.key == key)).first()
    if exists:
        conn.execute(update(db.system_state).where(db.system_state.c.key == key).values(value=value, updated_at=now))
    else:
        conn.execute(db.system_state.insert().values(key=key, value=value, updated_at=now))


def get_state(conn: Connection, key: str) -> dict | None:
    row = conn.execute(select(db.system_state.c.value, db.system_state.c.updated_at).where(db.system_state.c.key == key)).first()
    if not row:
        return None
    return {**row.value, "_updated_at": ensure_utc(row.updated_at).isoformat()}
