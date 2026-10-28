"""Backups.

Two independent formats, so retention never depends on one database engine:

* native   – `pg_dump -Fc` (PostgreSQL) or the SQLite online-backup API.
* portable – one gzip CSV per table + manifest with SHA-256 checksums.
             Restorable into an empty database of either dialect.

Copy the resulting directory off-site (object storage); see docs/BACKUP_RESTORE.md.
"""

from __future__ import annotations

import csv
import gzip
import hashlib
import json
import os
import sqlite3
import subprocess
from datetime import date, datetime, timezone
from pathlib import Path

from sqlalchemy import Boolean, Date, DateTime, Float, Integer, JSON, func, select, text
from sqlalchemy.engine import Engine

from . import db, store
from .migrations import current_version, migrate
from .timeutil import utcnow

TABLE_ORDER = [
    db.datasets, db.series, db.raw_snapshots, db.collection_runs,
    db.observations, db.observation_revisions, db.forecasts, db.system_state,
]


def _sha(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _record(engine: Engine, info: dict) -> None:
    with engine.begin() as conn:
        store.set_state(conn, "last_backup", info)


def native_backup(engine: Engine, database_url: str, out_dir: Path) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = utcnow().strftime("%Y%m%dT%H%M%SZ")
    if engine.dialect.name == "postgresql":
        target = out_dir / f"gso-archive-{stamp}.dump"
        url = database_url.replace("postgresql+psycopg://", "postgresql://")
        # Password is passed via the URL in the environment of the child only.
        subprocess.run(["pg_dump", "--format=custom", "--no-owner", "--file", str(target), url],
                       check=True, env={**os.environ})
    elif engine.dialect.name == "sqlite":
        target = out_dir / f"gso-archive-{stamp}.sqlite3"
        src = sqlite3.connect(engine.url.database)
        dst = sqlite3.connect(target)
        with dst:
            src.backup(dst)
        src.close()
        dst.close()
    else:  # pragma: no cover
        raise RuntimeError(f"unsupported dialect {engine.dialect.name}")
    info = {"kind": "native", "file": target.name, "bytes": target.stat().st_size, "sha256": _sha(target),
            "at": utcnow().isoformat(), "schema_version": current_version(engine)}
    (out_dir / f"{target.name}.sha256").write_text(f"{info['sha256']}  {target.name}\n")
    _record(engine, info)
    return info


def _encode(value) -> str:
    if value is None:
        return "\\N"
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, (dict, list)):
        return json.dumps(value)
    return str(value)


def _decode(column, raw: str):
    if raw == "\\N":
        return None
    t = column.type
    if isinstance(t, Boolean):
        return raw == "1"
    if isinstance(t, Integer):
        return int(raw)
    if isinstance(t, Float):
        return float(raw)
    if isinstance(t, DateTime):
        dt = datetime.fromisoformat(raw)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    if isinstance(t, Date):
        return date.fromisoformat(raw)
    if isinstance(t, JSON):
        return json.loads(raw)
    return raw


def portable_backup(engine: Engine, out_dir: Path) -> dict:
    stamp = utcnow().strftime("%Y%m%dT%H%M%SZ")
    target = out_dir / f"gso-archive-portable-{stamp}"
    target.mkdir(parents=True, exist_ok=True)
    manifest = {"format": "gso-archive-portable/1", "created_at": utcnow().isoformat(),
                "schema_version": current_version(engine), "tables": {}}
    with engine.connect() as conn:
        for table in TABLE_ORDER:
            path = target / f"{table.name}.csv.gz"
            cols = [c.name for c in table.columns]
            n = 0
            with gzip.open(path, "wt", encoding="utf-8", newline="") as fh:
                w = csv.writer(fh)
                w.writerow(cols)
                pk = list(table.primary_key.columns)
                for row in conn.execution_options(stream_results=True).execute(select(table).order_by(*pk)):
                    w.writerow([_encode(row._mapping[c]) for c in cols])
                    n += 1
            manifest["tables"][table.name] = {"rows": n, "sha256": _sha(path), "columns": cols}
    (target / "manifest.json").write_text(json.dumps(manifest, indent=2))
    info = {"kind": "portable", "file": target.name, "at": utcnow().isoformat(),
            "rows": {k: v["rows"] for k, v in manifest["tables"].items()}}
    _record(engine, info)
    return info


def portable_restore(engine: Engine, backup_dir: Path) -> dict:
    """Restore into an EMPTY database (refuses otherwise). Verifies checksums first."""
    manifest = json.loads((backup_dir / "manifest.json").read_text())
    for name, meta in manifest["tables"].items():
        actual = _sha(backup_dir / f"{name}.csv.gz")
        if actual != meta["sha256"]:
            raise ValueError(f"checksum mismatch for {name}: backup is corrupt")
    migrate(engine)
    with engine.connect() as conn:
        if conn.execute(select(func.count()).select_from(db.observations)).scalar():
            raise ValueError("target database is not empty; restore into a fresh database")
    counts = {}
    with engine.begin() as conn:
        for table in TABLE_ORDER:
            path = backup_dir / f"{table.name}.csv.gz"
            if not path.exists():
                continue
            with gzip.open(path, "rt", encoding="utf-8", newline="") as fh:
                reader = csv.reader(fh)
                header = next(reader)
                cols = [table.c[h] for h in header]
                batch, n = [], 0
                for raw in reader:
                    batch.append({c.name: _decode(c, v) for c, v in zip(cols, raw)})
                    if len(batch) >= 5000:
                        conn.execute(table.insert(), batch)
                        n += len(batch)
                        batch = []
                if batch:
                    conn.execute(table.insert(), batch)
                    n += len(batch)
            if n != manifest["tables"][table.name]["rows"]:
                raise ValueError(f"row count mismatch for {table.name}")
            counts[table.name] = n
        if engine.dialect.name == "postgresql":
            for table in TABLE_ORDER:
                if "id" in table.c and isinstance(table.c.id.type, Integer) and table.c.id.primary_key:
                    conn.execute(text(
                        f"SELECT setval(pg_get_serial_sequence('{table.name}', 'id'), "
                        f"COALESCE((SELECT MAX(id) FROM {table.name}), 0) + 1, false)"
                    ))
    return counts
