"""Keep the archive between GitHub Actions runs without a database server.

The same idea as Tech Comparison Hub's tools/seed_live.py: every run starts with a
fresh machine, so the archive (one SQLite file) is carried over from

  1. the Actions cache saved by the previous run (newest copy), and
  2. the copy published on the live site (data/archive.sqlite3.gz), in case the
     cache was cleared.

When both exist they are merged, never swapped: the union of every observation,
every revision, every forecast and every run is kept, so neither copy can roll
the other back. A daily copy also goes to a GitHub Release (see archive.yml).
"""

from __future__ import annotations

import gzip
import shutil
import sqlite3
import tempfile
import urllib.request
from pathlib import Path

from sqlalchemy import and_, func, select
from sqlalchemy.engine import Engine

from . import db
from .db import make_engine
from .migrations import migrate
from .timeutil import ensure_utc

ARCHIVE_FILE = "archive.sqlite3.gz"
UA = "gso-data-archive/2.0 (+https://github.com/Darren38/gso-data-archive)"


def _high_water(engine: Engine) -> tuple[int, str]:
    """(number of revision rows, newest change time): both only ever grow."""
    with engine.connect() as conn:
        n = conn.execute(select(func.count()).select_from(db.observation_revisions)).scalar() or 0
        newest = conn.execute(select(func.max(db.observations.c.last_changed_at))).scalar()
        runs = conn.execute(select(func.count()).select_from(db.collection_runs)).scalar() or 0
    return n + runs, ensure_utc(newest).isoformat() if newest else ""


def merge_archive(src: Engine, dst: Engine) -> dict:
    """Copy everything in `src` that `dst` lacks into `dst`. Safe to repeat."""
    migrate(dst)
    s_hw, d_hw = _high_water(src), _high_water(dst)
    if d_hw[0] >= s_hw[0] and d_hw[1] >= s_hw[1]:
        return {"skipped": "destination already has everything", "src": s_hw, "dst": d_hw}

    stats = {"datasets": 0, "series": 0, "runs": 0, "observations": 0, "observations_updated": 0,
             "revisions": 0, "forecasts": 0}
    with src.connect() as s, dst.begin() as d:
        # datasets and series, matched by their stable keys
        ds_map: dict[int, int] = {}
        for row in s.execute(select(db.datasets)):
            hit = d.execute(select(db.datasets.c.id).where(db.datasets.c.key == row.key)).first()
            if hit:
                ds_map[row.id] = hit.id
                continue
            values = {k: v for k, v in row._mapping.items() if k != "id"}
            ds_map[row.id] = d.execute(db.datasets.insert().values(**values)).inserted_primary_key[0]
            stats["datasets"] += 1
        se_map: dict[int, int] = {}
        for row in s.execute(select(db.series)):
            hit = d.execute(select(db.series.c.id, db.series.c.expected_interval_s).where(db.series.c.key == row.key)).first()
            if hit:
                se_map[row.id] = hit.id
                continue
            values = {k: v for k, v in row._mapping.items() if k != "id"}
            values["dataset_id"] = ds_map[row.dataset_id]
            se_map[row.id] = d.execute(db.series.insert().values(**values)).inserted_primary_key[0]
            stats["series"] += 1

        # collection runs, matched by (adapter, started_at)
        r = db.collection_runs.c
        known_runs = {(x.adapter, ensure_utc(x.started_at)): x.id for x in d.execute(select(r.id, r.adapter, r.started_at))}
        run_map: dict[int, int] = {}
        for row in s.execute(select(db.collection_runs)):
            key = (row.adapter, ensure_utc(row.started_at))
            if key in known_runs:
                run_map[row.id] = known_runs[key]
                continue
            values = {k: v for k, v in row._mapping.items() if k not in ("id", "raw_snapshot_id")}
            run_map[row.id] = d.execute(db.collection_runs.insert().values(**values)).inserted_primary_key[0]
            stats["runs"] += 1

        o, rv = db.observations.c, db.observation_revisions.c
        for src_sid, dst_sid in se_map.items():
            # revisions: union by (obs_time, collected_at, value)
            have = {(ensure_utc(x.obs_time), ensure_utc(x.collected_at), x.value)
                    for x in d.execute(select(rv.obs_time, rv.collected_at, rv.value).where(rv.series_id == dst_sid))}
            new_revs = []
            for x in s.execute(select(db.observation_revisions).where(rv.series_id == src_sid)):
                if (ensure_utc(x.obs_time), ensure_utc(x.collected_at), x.value) in have:
                    continue
                new_revs.append(dict(series_id=dst_sid, obs_time=x.obs_time, value=x.value, previous_value=x.previous_value,
                                     quality=x.quality, collected_at=x.collected_at,
                                     run_id=run_map.get(x.run_id), raw_snapshot_id=None))
            if new_revs:
                d.execute(db.observation_revisions.insert(), new_revs)
                stats["revisions"] += len(new_revs)

            # current values: missing rows are added; for a clash the most recently changed value wins
            current = {ensure_utc(x.obs_time): x for x in d.execute(
                select(o.obs_time, o.value, o.last_changed_at).where(o.series_id == dst_sid))}
            inserts = []
            for x in s.execute(select(db.observations).where(o.series_id == src_sid)):
                t = ensure_utc(x.obs_time)
                mine = current.get(t)
                if mine is None:
                    values = dict(x._mapping)
                    values.update(series_id=dst_sid, last_run_id=run_map.get(x.last_run_id))
                    inserts.append(values)
                elif mine.value != x.value and ensure_utc(x.last_changed_at) > ensure_utc(mine.last_changed_at):
                    d.execute(db.observations.update()
                              .where(and_(o.series_id == dst_sid, o.obs_time == mine.obs_time))
                              .values(value=x.value, quality=x.quality, last_changed_at=x.last_changed_at))
                    stats["observations_updated"] += 1
            if inserts:
                d.execute(db.observations.insert(), inserts)
                stats["observations"] += len(inserts)
            if new_revs or inserts:
                # revision_count = number of distinct values seen, recomputed after the union
                counts = d.execute(select(rv.obs_time, func.count()).where(rv.series_id == dst_sid).group_by(rv.obs_time)).all()
                for t, n in counts:
                    d.execute(db.observations.update().where(and_(o.series_id == dst_sid, o.obs_time == t)).values(revision_count=n))

            f = db.forecasts.c
            fhave = {(ensure_utc(x.target_time), ensure_utc(x.issue_time))
                     for x in d.execute(select(f.target_time, f.issue_time).where(f.series_id == dst_sid))}
            fnew = []
            for x in s.execute(select(db.forecasts).where(f.series_id == src_sid)):
                if (ensure_utc(x.target_time), ensure_utc(x.issue_time)) in fhave:
                    continue
                values = dict(x._mapping)
                values.update(series_id=dst_sid, run_id=run_map.get(x.run_id))
                fnew.append(values)
            if fnew:
                d.execute(db.forecasts.insert(), fnew)
                stats["forecasts"] += len(fnew)

        # operational state: the newer entry of each key wins
        st = db.system_state.c
        for row in s.execute(select(db.system_state)):
            mine = d.execute(select(st.updated_at).where(st.key == row.key)).first()
            if mine is None:
                d.execute(db.system_state.insert().values(**dict(row._mapping)))
            elif ensure_utc(row.updated_at) > ensure_utc(mine.updated_at):
                d.execute(db.system_state.update().where(st.key == row.key).values(value=row.value, updated_at=row.updated_at))
    return stats


def sqlite_path(database_url: str) -> Path:
    if not database_url.startswith("sqlite:///"):
        raise ValueError("the GitHub-only archive is a SQLite file (DATABASE_URL=sqlite:///...)")
    return Path(database_url[len("sqlite:///"):])


def write_snapshot(database_url: str, out_file: Path) -> int:
    """Consistent gzip copy of the SQLite archive (safe while it is in use)."""
    src_path = sqlite_path(database_url)
    out_file.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        copy = Path(tmp) / "copy.sqlite3"
        src, dst = sqlite3.connect(src_path), sqlite3.connect(copy)
        with dst:
            src.backup(dst)
        src.close()
        dst.execute("PRAGMA journal_mode=DELETE")
        dst.close()
        with open(copy, "rb") as fh, gzip.open(out_file, "wb", compresslevel=6) as gz:
            shutil.copyfileobj(fh, gz)
    return out_file.stat().st_size


def seed_from_live(database_url: str, base_url: str, timeout: float = 60) -> dict:
    """Download the published archive and merge it into the local one. Never raises for network trouble."""
    local = sqlite_path(database_url)
    url = base_url.rstrip("/") + "/data/" + ARCHIVE_FILE
    with tempfile.TemporaryDirectory() as tmp:
        gz_path, db_path = Path(tmp) / ARCHIVE_FILE, Path(tmp) / "live.sqlite3"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Cache-Control": "no-cache"})
            with urllib.request.urlopen(req, timeout=timeout) as res, open(gz_path, "wb") as fh:
                shutil.copyfileobj(res, fh)
            with gzip.open(gz_path, "rb") as gz, open(db_path, "wb") as fh:
                shutil.copyfileobj(gz, fh)
            sqlite3.connect(db_path).execute("PRAGMA integrity_check").fetchone()
        except Exception as exc:  # noqa: BLE001 - first deploy, offline, or a corrupt copy: keep what we have
            return {"seeded": False, "reason": f"live copy not available ({type(exc).__name__}: {exc})"}
        live = make_engine(f"sqlite:///{db_path}")
        migrate(live)
        if not local.exists() or local.stat().st_size == 0:
            live.dispose()
            local.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(db_path, local)
            return {"seeded": True, "how": "copied the live archive (no local copy yet)"}
        target = make_engine(database_url)
        try:
            result = merge_archive(live, target)
        finally:
            live.dispose()
            target.dispose()
        return {"seeded": True, "how": "merged", **result}
