from dataclasses import replace
from datetime import date, datetime, timedelta, timezone

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError

from gso_archive import collector, db, store
from gso_archive.adapters import get_adapter
from gso_archive.collector import backfill, collect_one, plan_cycle, run_cycle
from gso_archive.http import GsoClient
from gso_archive.locks import collector_lock
from gso_archive.timeutil import myt_today

GEN = "SystemData/CurrentGen.aspx/GetChartDataSource"
DEM = "SystemData/SystemDemand.aspx/GetChartDataSource"
DAY = date(2026, 10, 27)


def count(engine, table):
    with engine.connect() as conn:
        return conn.execute(select(func.count()).select_from(table)).scalar()


def runs(engine):
    with engine.connect() as conn:
        return conn.execute(select(db.collection_runs).order_by(db.collection_runs.c.id)).all()


def test_successful_run_stores_data_and_raw(engine, settings, client, fake):
    fake.add(GEN, "currentgen_2026-10-27.json")
    r = collect_one(engine, client, settings, get_adapter("generation_mix"), DAY)
    assert r.status == "success" and r.records_new == 288
    assert fake.bodies(GEN)[0] == {"Fromdate": "27/10/2026", "Todate": "27/10/2026"}
    assert fake.posts(GEN)[0].headers["content-type"].startswith("application/json")
    assert count(engine, db.observations) == 288
    run = runs(engine)[0]
    assert run.status == "success" and run.http_status == 200 and run.raw_snapshot_id
    assert list(settings.raw_store_dir.rglob("*.json.gz"))


def test_rerun_dedupes_and_raw_unchanged_is_not_rewritten(engine, settings, client, fake):
    fake.add(GEN, "currentgen_2026-10-27.json")
    spec = get_adapter("generation_mix")
    collect_one(engine, client, settings, spec, DAY)
    r2 = collect_one(engine, client, settings, spec, DAY)
    assert r2.status == "success" and r2.records_new == 0 and r2.records_unchanged == 288
    assert len(list(settings.raw_store_dir.rglob("*.json.gz"))) == 1  # identical bytes stored once
    assert count(engine, db.raw_snapshots) == 2  # but each fetch is recorded


def test_revised_reading_detected(engine, settings, client, fake):
    spec = get_adapter("generation_mix")
    fake.add(GEN, "currentgen_2026-10-27.json", "currentgen_revised.json")
    collect_one(engine, client, settings, spec, DAY)
    r = collect_one(engine, client, settings, spec, DAY)
    assert r.records_revised == 1
    with engine.connect() as conn:
        rev = conn.execute(select(db.observation_revisions).where(db.observation_revisions.c.previous_value.is_not(None))).one()
    assert rev.value == 9999.0 and rev.previous_value == 7005.0


def test_network_failure_is_retried_then_recorded(engine, settings, client, fake, monkeypatch):
    monkeypatch.setattr("gso_archive.http.time.sleep", lambda s: None)
    fake.add(GEN, httpx.ConnectError("boom"), 503, 503)
    r = collect_one(engine, client, settings, get_adapter("generation_mix"), DAY)
    assert r.status == "failed" and r.error_type == "http_error"
    assert len(fake.posts(GEN)) == 3  # 1 + max_retries
    assert runs(engine)[-1].status == "failed"


def test_transient_failure_recovers(engine, settings, client, fake, monkeypatch):
    monkeypatch.setattr("gso_archive.http.time.sleep", lambda s: None)
    fake.add(GEN, 500, "currentgen_2026-10-27.json")
    r = collect_one(engine, client, settings, get_adapter("generation_mix"), DAY)
    assert r.status == "success" and r.records_new == 288


def test_client_errors_not_retried(engine, settings, client, fake):
    fake.add(GEN, 403)
    r = collect_one(engine, client, settings, get_adapter("generation_mix"), DAY)
    assert r.status == "failed" and len(fake.posts(GEN)) == 1


def test_failure_never_erases_existing_data(engine, settings, client, fake, monkeypatch):
    monkeypatch.setattr("gso_archive.http.time.sleep", lambda s: None)
    spec = get_adapter("generation_mix")
    fake.add(GEN, "currentgen_2026-10-27.json", "not_json.html", 500)
    collect_one(engine, client, settings, spec, DAY)
    before = count(engine, db.observations)
    bad = collect_one(engine, client, settings, spec, DAY)
    assert bad.status == "failed" and bad.error_type == "parse_error"
    assert runs(engine)[-1].raw_snapshot_id  # raw kept for investigation
    down = collect_one(engine, client, settings, spec, DAY)
    assert down.status == "failed"
    assert count(engine, db.observations) == before


def test_database_failure_rolls_back_and_keeps_data(engine, settings, client, fake, monkeypatch):
    spec = get_adapter("generation_mix")
    fake.add(GEN, "currentgen_2026-10-27.json", "currentgen_revised.json")
    collect_one(engine, client, settings, spec, DAY)

    def broken(*a, **k):
        raise OperationalError("INSERT", {}, Exception("disk I/O error"))

    monkeypatch.setattr(store, "apply_readings", broken)
    r = collect_one(engine, client, settings, spec, DAY)
    assert r.status == "failed" and r.error_type == "database_error"
    assert count(engine, db.observations) == 288
    with engine.connect() as conn:
        assert conn.execute(select(func.max(db.observations.c.value))).scalar() < 9999.0  # revision not half-applied


def test_schema_change_flagged_and_new_series_created(engine, settings, client, fake):
    spec = get_adapter("generation_mix")
    fake.add(GEN, "currentgen_2026-10-27.json", "currentgen_new_field.json")
    collect_one(engine, client, settings, spec, DAY)
    r = collect_one(engine, client, settings, spec, DAY)
    assert r.schema_changed
    with engine.connect() as conn:
        s = conn.execute(select(db.series).where(db.series.c.key == "generation_mix.battery")).one()
    assert s.auto_discovered


def test_live_host_requires_opt_in(engine, settings):
    live = replace(settings, gso_base_url="https://www.gso.org.my", gso_live_enabled=False)
    transport = httpx.MockTransport(lambda req: pytest.fail("must not contact the live site"))
    with GsoClient(live, transport=transport) as c:
        r = collect_one(engine, c, live, get_adapter("generation_mix"), DAY)
        assert r.status == "disabled"
        cycle = run_cycle(engine, live, c)
    assert cycle.skipped_reason and not cycle.results


def test_plan_includes_today_recheck_and_auto_backfill(engine, settings):
    now = datetime(2026, 10, 27, 6, 0, tzinfo=timezone.utc)
    plan = plan_cycle(engine, settings, now)
    gen = [(d, t) for s, d, t in plan if s.key == "generation_mix"]
    today = date(2026, 10, 27)
    assert (today, "schedule") in gen and (today - timedelta(days=1), "recheck") in gen
    backfills = [d for d, t in gen if t == "auto_backfill"]
    assert backfills == [today - timedelta(days=2), today - timedelta(days=3)]  # budget = 2


def test_plan_skips_recently_collected(engine, settings):
    now = datetime(2026, 10, 27, 6, 0, tzinfo=timezone.utc)
    with engine.begin() as conn:
        for offset in range(0, 5):
            rid = store.start_run(conn, "generation_mix", date(2026, 10, 27) - timedelta(days=offset), "schedule")
            store.finish_run(conn, rid, status="success")
    gen = [(d, t) for s, d, t in plan_cycle(engine, settings, now) if s.key == "generation_mix"]
    assert gen == [(date(2026, 10, 27), "schedule")]


def test_daily_adapter_respects_min_interval(engine, settings):
    s = replace(settings, adapters=["power_station"])
    assert len(plan_cycle(engine, s)) == 1
    with engine.begin() as conn:
        rid = store.start_run(conn, "power_station", None, "schedule")
        store.finish_run(conn, rid, status="success")
    assert plan_cycle(engine, s) == []


def test_run_cycle_end_to_end(engine, settings, client, fake):
    fake.add(GEN, "currentgen_2026-10-27.json")
    fake.add(DEM, "demand_2026-10-27.json")
    cycle = run_cycle(engine, settings, client)
    assert cycle.ok and len(cycle.results) == 8  # 2 adapters × (today, recheck, 2 backfills)
    with engine.connect() as conn:
        assert store.get_state(conn, "collector_heartbeat")["runs"] == 8


def test_backfill_skips_existing_days(engine, settings, client, fake):
    fake.add(GEN, "currentgen_2026-10-27.json")
    fake.add(DEM, "demand_2026-10-27.json")
    first = backfill(engine, settings, date(2026, 10, 20), date(2026, 10, 22), client=client)
    assert len(first) == 6 and all(r.status == "success" for r in first)
    assert [b["Fromdate"] for b in fake.bodies(GEN)] == ["20/10/2026", "21/10/2026", "22/10/2026"]
    again = backfill(engine, settings, date(2026, 10, 20), date(2026, 10, 23), client=client)
    assert [r.target_date for r in again] == [date(2026, 10, 23)] * 2
    refetch = backfill(engine, settings, date(2026, 10, 20), date(2026, 10, 20), skip_existing=False, client=client)
    assert len(refetch) == 2


def test_backfill_rejects_inverted_range(engine, settings, client):
    with pytest.raises(ValueError):
        backfill(engine, settings, date(2026, 10, 22), date(2026, 10, 20), client=client)


def test_lock_prevents_concurrent_cycles(engine, settings, client):
    if engine.dialect.name != "sqlite":
        pytest.skip("file lock is SQLite-specific; PG advisory lock is per-session")
    with collector_lock(engine):
        cycle = run_cycle(engine, settings, client)
    assert cycle.skipped_reason and "another collector" in cycle.skipped_reason


def test_tieline_request_includes_line_param(engine, settings, client, fake):
    fake.add("SystemData/TieLine.aspx/GetChartDataSource", "tieline_pltg_2026-10-27.json")
    r = collect_one(engine, client, settings, get_adapter("tieline_pltg"), DAY)
    assert r.status == "success"
    assert fake.bodies("TieLine")[0]["Line"] == "PLTG"


def test_myt_today_is_used_for_schedule(engine, settings):
    plan = plan_cycle(engine, settings)
    assert plan[0][1] == myt_today()
