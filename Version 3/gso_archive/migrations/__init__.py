"""Numbered, forward-only schema migrations.

Add a new migration by appending to MIGRATIONS with the next version number.
Each migration runs in its own transaction and is recorded in
`schema_migrations`, so `gso-archive migrate` is safe to run repeatedly.
"""

from __future__ import annotations

from collections.abc import Callable

from sqlalchemy import inspect, select
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


MIGRATIONS: list[tuple[int, str, Callable[[Connection], None]]] = [
    (1, "initial schema", _m001_initial),
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
