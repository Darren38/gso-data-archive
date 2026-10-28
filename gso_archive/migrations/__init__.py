"""Numbered, forward-only schema migrations.

Add a new migration by appending to MIGRATIONS with the next version number.
Each migration runs in its own transaction and is recorded in
`schema_migrations`, so `gso-archive migrate` is safe to run repeatedly.
"""

from __future__ import annotations

from collections.abc import Callable

from datetime import timedelta

from sqlalchemy import and_, delete, inspect, select, text
from sqlalchemy.engine import Connection, Engine

from .. import db
from ..timeutil import utcnow


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


MIGRATIONS: list[tuple[int, str, Callable[[Connection], None]]] = [
    (1, "initial schema", _m001_initial),
    (2, "drop readings dated after they were collected", _m002_drop_future_readings),
    (3, "series latitude and longitude", _m003_series_location),
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
