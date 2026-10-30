"""Numbered, forward-only schema migrations.

Add a new migration by appending to MIGRATIONS with the next version number.
Each migration runs in its own transaction and is recorded in
`schema_migrations`, so `gso-archive migrate` is safe to run repeatedly.
"""

from __future__ import annotations

from collections.abc import Callable

from datetime import datetime, time, timedelta

from sqlalchemy import and_, delete, inspect, select, text, update
from sqlalchemy.engine import Connection, Engine

from .. import db
from ..timeutil import MYT, ensure_utc, utcnow


def _m001_initial(conn: Connection) -> None:
    tables = [
        db.datasets,
        db.series,
        db.observations,
        db.observation_revisions,
        db.forecasts,
        db.raw_snapshots,
        db.collection_runs,
        db.system_state,
    ]
    db.metadata.create_all(conn, tables=tables)


def _m002_drop_future_readings(conn: Connection) -> None:
    """Remove readings dated after they were collected. Before sunrise GSO's "last available" time is 07:00 of the
    coming morning, and the solar-farm readings were dated with it (fixed in GSO Grid Archive 5.6)."""
    o, rv = db.observations.c, db.observation_revisions.c
    bad = [(r.series_id, r.obs_time) for r in conn.execute(select(o.series_id, o.obs_time, o.first_collected_at))
           if r.obs_time - r.first_collected_at > timedelta(minutes=15)]
    for sid, t in bad:
        conn.execute(delete(db.observation_revisions).where(and_(rv.series_id == sid, rv.obs_time == t)))
        conn.execute(delete(db.observations).where(and_(o.series_id == sid, o.obs_time == t)))


def _m003_series_location(conn: Connection) -> None:
    """Where a series is measured (the solar farms on GSO's solar map have a latitude and longitude)."""
    have = {c["name"] for c in inspect(conn).get_columns("series")}
    for col in ("latitude", "longitude"):
        if col not in have:
            conn.execute(text(f"ALTER TABLE series ADD COLUMN {col} FLOAT"))


def _m004_refile_evening_solar(conn: Connection) -> None:
    """Put Solar page readings filed under the wrong day back on their own day. GSO's Solar page lists today only,
    but after sunset its "last available" time stops moving while the list keeps growing, and the collector judged
    the day by that time: each evening the whole list was filed under the day before (fixed in 5.7). A reading
    collected on day D after 01:00 can only be D's (just after midnight GSO may still serve yesterday's list), so
    each such write moves to the same time on D, and the earlier day keeps only the readings collected for it."""
    o, rv, s = db.observations.c, db.observation_revisions.c, db.series.c
    sids = [r.id for r in conn.execute(select(s.id).where(s.key.like("solar_profile.%")))]
    for sid in sids:
        revs = conn.execute(select(rv.id, rv.obs_time, rv.value, rv.quality, rv.collected_at, rv.run_id)
                            .where(rv.series_id == sid).order_by(rv.collected_at, rv.id)).all()
        wrong: dict[datetime, list] = {}  # right obs_time -> its misfiled writes
        touched: set[datetime] = set()
        for r in revs:
            t, got = ensure_utc(r.obs_time).astimezone(MYT), ensure_utc(r.collected_at).astimezone(MYT)
            if t.date() < got.date() and got.time() >= time(1, 0):
                right = datetime.combine(got.date(), t.time(), tzinfo=MYT).astimezone(ensure_utc(r.obs_time).tzinfo)
                touched.add(ensure_utc(r.obs_time))
                conn.execute(delete(db.observation_revisions).where(rv.id == r.id))
                if right - ensure_utc(r.collected_at) <= timedelta(minutes=15):
                    wrong.setdefault(right, []).append(r)
        # the earlier day: back to its last write collected for it, or no reading at all
        for t in touched:
            keep = conn.execute(select(rv.value, rv.quality, rv.collected_at, rv.run_id)
                                .where(and_(rv.series_id == sid, rv.obs_time == t))
                                .order_by(rv.collected_at, rv.id)).all()
            where = and_(o.series_id == sid, o.obs_time == t)
            if not keep:
                conn.execute(delete(db.observations).where(where))
            else:
                last = keep[-1]
                conn.execute(update(db.observations).where(where).values(
                    value=last.value, quality=last.quality, first_collected_at=keep[0].collected_at,
                    last_changed_at=last.collected_at, revision_count=len(keep), last_run_id=last.run_id))
        # the right day: only where it has no reading of its own
        for t, writes in wrong.items():
            if conn.execute(select(o.obs_time).where(and_(o.series_id == sid, o.obs_time == t))).first():
                continue
            prev = None
            for w in writes:
                conn.execute(db.observation_revisions.insert().values(
                    series_id=sid, obs_time=t, value=w.value, previous_value=prev, quality=w.quality,
                    collected_at=w.collected_at, run_id=w.run_id))
                prev = w.value
            last = writes[-1]
            conn.execute(db.observations.insert().values(
                series_id=sid, obs_time=t, value=last.value, quality=last.quality,
                first_collected_at=writes[0].collected_at, last_changed_at=last.collected_at,
                revision_count=len(writes), last_run_id=last.run_id))


def _m005_record_series(conn: Connection) -> None:
    """GSO's "Highest Grid Demand Recorded" is a record dated when it happened, not a reading that should keep
    arriving: mark it so the Status page doesn't call it stale."""
    conn.execute(update(db.series).where(db.series.c.key == "headlines.highest_grid_demand_recorded").values(kind="record"))


MIGRATIONS: list[tuple[int, str, Callable[[Connection], None]]] = [
    (1, "initial schema", _m001_initial),
    (2, "drop readings dated after they were collected", _m002_drop_future_readings),
    (3, "series latitude and longitude", _m003_series_location),
    (4, "put evening Solar page readings back on their own day", _m004_refile_evening_solar),
    (5, "mark record values (highest demand recorded)", _m005_record_series),
]


def applied_versions(engine: Engine) -> set[int]:
    if not inspect(engine).has_table("schema_migrations"):
        return set()
    with engine.connect() as conn:
        return {row[0] for row in conn.execute(select(db.schema_migrations.c.version))}


def migrate(engine: Engine) -> list[int]:
    """Apply pending migrations. Returns the versions applied."""
    db.metadata.create_all(engine, tables=[db.schema_migrations])
    done = applied_versions(engine)
    applied: list[int] = []
    for version, description, fn in MIGRATIONS:
        if version in done:
            continue
        with engine.begin() as conn:
            fn(conn)
            conn.execute(
                db.schema_migrations.insert().values(
                    version=version, description=description, applied_at=utcnow()
                )
            )
        applied.append(version)
    return applied


def current_version(engine: Engine) -> int:
    versions = applied_versions(engine)
    return max(versions) if versions else 0
