import json
from dataclasses import replace
from datetime import date

import pytest
from sqlalchemy import func, select

from gso_archive import db
from gso_archive.adapters import get_adapter
from gso_archive.backup import native_backup, portable_backup, portable_restore
from gso_archive.collector import collect_one
from gso_archive.db import make_engine
from gso_archive.demo import DemoRefused, seed_demo
from gso_archive.export_static import export_site
from gso_archive.migrations import migrate

GEN = "SystemData/CurrentGen.aspx/GetChartDataSource"


def _collect(engine, settings, client, fake):
    fake.add(GEN, "currentgen_2026-10-27.json", "currentgen_revised.json")
    spec = get_adapter("generation_mix")
    collect_one(engine, client, settings, spec, date(2026, 10, 27))
    collect_one(engine, client, settings, spec, date(2026, 10, 27))


def _counts(engine):
    with engine.connect() as conn:
        return {t.name: conn.execute(select(func.count()).select_from(t)).scalar()
                for t in (db.observations, db.observation_revisions, db.collection_runs, db.series)}


def test_portable_backup_roundtrip(engine, settings, client, fake, tmp_path):
    _collect(engine, settings, client, fake)
    info = portable_backup(engine, tmp_path / "bk")
    target = make_engine(f"sqlite:///{tmp_path / 'restored.sqlite3'}")
    counts = portable_restore(target, tmp_path / "bk" / info["file"])
    assert counts["observations"] == 288 and counts["observation_revisions"] == 289
    assert _counts(target) == _counts(engine)
    with target.connect() as conn:
        assert conn.execute(select(func.max(db.observations.c.value))).scalar() == 9999.0


def test_restore_refuses_corrupt_or_nonempty(engine, settings, client, fake, tmp_path):
    _collect(engine, settings, client, fake)
    info = portable_backup(engine, tmp_path / "bk")
    folder = tmp_path / "bk" / info["file"]
    with pytest.raises(ValueError, match="not empty"):
        portable_restore(engine, folder)
    manifest = json.loads((folder / "manifest.json").read_text())
    manifest["tables"]["observations"]["sha256"] = "0" * 64
    (folder / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="checksum"):
        portable_restore(make_engine(f"sqlite:///{tmp_path / 'x.sqlite3'}"), folder)


def test_native_sqlite_backup(engine, settings, client, fake, tmp_path):
    if engine.dialect.name != "sqlite":
        pytest.skip("pg_dump path covered by the PostgreSQL run")
    _collect(engine, settings, client, fake)
    info = native_backup(engine, settings.database_url, tmp_path / "nb")
    copy = make_engine(f"sqlite:///{tmp_path / 'nb' / info['file']}")
    assert _counts(copy)["observations"] == 288


def test_static_export(engine, settings, client, fake, tmp_path):
    _collect(engine, settings, client, fake)
    out = tmp_path / "site"
    export_site(engine, settings, out)
    assert "static" in (out / "config.js").read_text()
    meta = json.loads((out / "data" / "meta.json").read_text())
    assert any(s["key"] == "generation_mix.solar" for s in meta["series"])
    month = json.loads((out / "data" / "points" / "generation_mix.solar" / "2026-10.json").read_text())
    assert len(month["points"]) == 48
    assert (out / "data" / "exports" / "generation_mix.solar" / "2026-10.csv").exists()
    assert (out / "index.html").exists() and (out / "vendor" / "echarts-5.5.1.min.js").exists()


def test_demo_refuses_real_database(engine, settings, client, fake):
    _collect(engine, settings, client, fake)
    with pytest.raises(DemoRefused):
        seed_demo(engine, days=2)


def test_demo_data_is_flagged(tmp_path):
    eng = make_engine(f"sqlite:///{tmp_path / 'demo.sqlite3'}")
    migrate(eng)
    seed_demo(eng, days=2)
    with eng.connect() as conn:
        assert conn.execute(select(func.count()).select_from(db.series).where(db.series.c.is_demo.is_(False))).scalar() == 0
        assert {r[0] for r in conn.execute(select(db.datasets.c.verification))} == {"demo"}
