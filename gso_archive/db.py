"""Database schema (SQLAlchemy Core) and engine helpers.

Works with PostgreSQL (production) and SQLite (local development / tests).
All timestamps are stored as UTC. Schema changes go through numbered
migrations in `gso_archive/migrations/` — never edit an applied migration.
"""

from __future__ import annotations

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    PrimaryKeyConstraint,
    String,
    Table,
    Text,
    create_engine,
    event,
)
from sqlalchemy.engine import Engine

metadata = MetaData()

TS = DateTime(timezone=True)

schema_migrations = Table(
    "schema_migrations",
    metadata,
    Column("version", Integer, primary_key=True, autoincrement=False),
    Column("description", String(200), nullable=False),
    Column("applied_at", TS, nullable=False),
)

datasets = Table(
    "datasets",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("key", String(64), nullable=False, unique=True),
    Column("name", String(200), nullable=False),
    Column("category", String(32), nullable=False),  # solar|demand|generation|tieline|bess|constraints|capacity
    Column("source_url", String(500), nullable=False),
    # verified | third_party_documented | unverified | demo
    Column("verification", String(32), nullable=False),
    Column("description", Text, nullable=False, default=""),
    Column("is_demo", Boolean, nullable=False, default=False),
    Column("created_at", TS, nullable=False),
)

series = Table(
    "series",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("dataset_id", Integer, ForeignKey("datasets.id"), nullable=False),
    Column("key", String(128), nullable=False, unique=True),
    Column("name", String(200), nullable=False),
    Column("unit", String(16), nullable=False),
    Column("kind", String(16), nullable=False),  # actual | forecast | capacity
    Column("source_field", String(128), nullable=False),
    Column("auto_discovered", Boolean, nullable=False, default=False),
    Column("expected_interval_s", Integer, nullable=True),
    Column("is_demo", Boolean, nullable=False, default=False),
    Column("created_at", TS, nullable=False),
)

# Current best-known value for each (series, observation time).
observations = Table(
    "observations",
    metadata,
    Column("series_id", Integer, ForeignKey("series.id"), nullable=False),
    Column("obs_time", TS, nullable=False),  # source observation time (UTC)
    Column("value", Float, nullable=False),
    Column("quality", String(32), nullable=False, default="ok"),
    Column("first_collected_at", TS, nullable=False),
    Column("last_changed_at", TS, nullable=False),  # record revision time
    Column("revision_count", Integer, nullable=False, default=1),
    Column("last_run_id", Integer, nullable=True),
    PrimaryKeyConstraint("series_id", "obs_time", name="pk_observations"),
)

# Append-only history: one row per distinct value ever seen. Never updated.
observation_revisions = Table(
    "observation_revisions",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("series_id", Integer, ForeignKey("series.id"), nullable=False),
    Column("obs_time", TS, nullable=False),
    Column("value", Float, nullable=False),
    Column("previous_value", Float, nullable=True),
    Column("quality", String(32), nullable=False),
    Column("collected_at", TS, nullable=False),
    Column("run_id", Integer, nullable=True),
    Column("raw_snapshot_id", Integer, nullable=True),
    Index("ix_revisions_series_time", "series_id", "obs_time"),
)

forecasts = Table(
    "forecasts",
    metadata,
    Column("series_id", Integer, ForeignKey("series.id"), nullable=False),
    Column("target_time", TS, nullable=False),
    Column("issue_time", TS, nullable=False),
    # True when the source gives no issue time and collection time was used.
    Column("issue_time_inferred", Boolean, nullable=False, default=True),
    Column("value", Float, nullable=False),
    Column("collected_at", TS, nullable=False),
    Column("run_id", Integer, nullable=True),
    PrimaryKeyConstraint("series_id", "target_time", "issue_time", name="pk_forecasts"),
)

raw_snapshots = Table(
    "raw_snapshots",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("adapter", String(64), nullable=False),
    Column("url", String(500), nullable=False),
    Column("request_body", Text, nullable=True),
    Column("fetched_at", TS, nullable=False),
    Column("http_status", Integer, nullable=True),
    Column("content_type", String(128), nullable=True),
    Column("sha256", String(64), nullable=False),
    Column("size_bytes", Integer, nullable=False),
    Column("storage_path", String(500), nullable=True),
    Index("ix_raw_adapter_time", "adapter", "fetched_at"),
)

collection_runs = Table(
    "collection_runs",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("adapter", String(64), nullable=False),
    Column("target_date", Date, nullable=True),  # MYT calendar day requested
    Column("trigger", String(16), nullable=False),  # schedule|recheck|auto_backfill|backfill|manual
    Column("started_at", TS, nullable=False),
    Column("finished_at", TS, nullable=True),
    Column("status", String(16), nullable=False),  # running|success|failed|disabled
    Column("http_status", Integer, nullable=True),
    Column("records_seen", Integer, nullable=False, default=0),
    Column("records_new", Integer, nullable=False, default=0),
    Column("records_revised", Integer, nullable=False, default=0),
    Column("records_unchanged", Integer, nullable=False, default=0),
    Column("records_missing", Integer, nullable=False, default=0),
    Column("records_suspect", Integer, nullable=False, default=0),
    Column("records_rejected", Integer, nullable=False, default=0),
    Column("duration_ms", Integer, nullable=True),
    Column("error_type", String(64), nullable=True),
    Column("error_message", Text, nullable=True),
    Column("schema_signature", String(500), nullable=True),
    Column("schema_changed", Boolean, nullable=False, default=False),
    Column("latest_obs_time", TS, nullable=True),
    Column("raw_snapshot_id", Integer, nullable=True),
    Index("ix_runs_adapter_started", "adapter", "started_at"),
    Index("ix_runs_adapter_date", "adapter", "target_date"),
)

# Small key/value store for operational state (scheduler heartbeat, backups).
system_state = Table(
    "system_state",
    metadata,
    Column("key", String(64), primary_key=True),
    Column("value", JSON, nullable=False),
    Column("updated_at", TS, nullable=False),
)

def make_engine(url: str) -> Engine:
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://"):]
    kwargs: dict = {"future": True, "pool_pre_ping": True}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False, "timeout": 30}
    engine = create_engine(url, **kwargs)
    if engine.dialect.name == "sqlite":
        _ensure_sqlite_dir(url)

        @event.listens_for(engine, "connect")
        def _sqlite_pragmas(dbapi_conn, _record):  # pragma: no cover - trivial
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA journal_mode=WAL")
            cur.execute("PRAGMA foreign_keys=ON")
            cur.execute("PRAGMA synchronous=NORMAL")
            cur.close()

    return engine


def _ensure_sqlite_dir(url: str) -> None:
    from pathlib import Path

    path = url.split(":///", 1)[-1]
    if path and path != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
