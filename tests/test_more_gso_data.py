"""More of GSO's published data kept: the other renewables split and every power station's details (real answers saved
by the probe on 30 October 2026, tests/fixtures/real)."""

import json
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from gso_archive import analytics, db, store
from gso_archive.adapters import get_adapter, parse
from gso_archive.collector import collect_one
from gso_archive.timeutil import MYT

from .conftest import fixture_bytes

UTC = timezone.utc
T = datetime(2026, 10, 30, 12, 20, tzinfo=MYT).astimezone(UTC)  # the home page's newest reading at the time


def _other_re(shared):
    return parse(get_adapter("other_re"), fixture_bytes("real/landing_other_re.json"), T.date(), {"shared": shared})


def test_other_re_split_is_filed_at_the_home_page_time():
    p = _other_re({"genmix_other_re": (T, 175.0)})
    assert {r.series: r.value for r in p.readings} == {"biogas": 101, "biomass": 24, "mini_hydro": 50}
    assert {r.obs_time for r in p.readings} == {T} and not p.rejected


def test_other_re_split_from_another_moment_is_not_kept():
    p = _other_re({"genmix_other_re": (T, 171.0)})  # the home page had already moved on: no guessing
    assert not p.readings and "different moments" in p.rejected[0]
    p = _other_re({})  # no home page reading in this run
    assert not p.readings and p.rejected


def test_home_page_shares_its_newest_other_re():
    shared = {}
    parse(get_adapter("genmix_live"), fixture_bytes("real/landing_genmix.json"), T.date(), {"shared": shared})
    t, value = shared["genmix_other_re"]
    raw = json.loads(fixture_bytes("real/landing_genmix.json"))["d"].split("$")
    assert value == float(raw[7].split(",")[-1])
    assert t == datetime(2026, 10, 28, 13, 20, tzinfo=MYT).astimezone(UTC)  # r[14]: "... 28 October 2026 1:20 PM"


def test_other_re_collected_after_the_home_page(engine, settings, client, fake, monkeypatch):
    monkeypatch.setattr("gso_archive.collector.utcnow", lambda: datetime(2026, 10, 28, 13, 31, tzinfo=MYT).astimezone(UTC))
    raw = json.loads(fixture_bytes("real/landing_genmix.json"))["d"].split("$")
    newest = float(raw[7].split(",")[-1])
    other = json.dumps({"d": json.dumps([{"y": newest, "drilldown": {"name": "Other RE", "categories": [
        "Biogas", "Biomass", "Mini Hydro"], "data": [newest - 74, 24, 50]}}])})
    fake.add("LandingPage.aspx/GetGenMixData", "real/landing_genmix.json")
    fake.add("LandingPage.aspx/GetOtherREData", other.encode())
    collect_one(engine, client, settings, get_adapter("genmix_live"), T.date())
    r = collect_one(engine, client, settings, get_adapter("other_re"), T.date())
    assert r.status == "success" and r.records_new == 3
    with engine.connect() as c:
        rows = c.execute(select(db.series.c.key, db.series.c.name)).all()
    assert ("other_re.mini_hydro", "Other renewables — Mini Hydro") in rows


def test_power_stations_are_kept_one_by_one():
    p = parse(get_adapter("power_station"), fixture_bytes("real/power_station_partial.json"), T.date())
    first = p.table[0]
    assert first == {"id": "4", "name": "TNB Pasir Gudang Energy Sdn Bhd", "fuel": "Gas", "type": "CCGT",
                     "capacity_mw": 275.0, "ppa_expiry": "2022-08-01", "ppa_expiry_label": "2022 Aug"}
    assert len(p.table) == 6
    assert sum(r.value for r in p.readings if r.series == "capacity_total") == sum(s["capacity_mw"] for s in p.table)


def test_power_station_changes_are_recorded(engine):
    p = parse(get_adapter("power_station"), fixture_bytes("real/power_station_partial.json"), T.date())
    day1, day2 = T, T + timedelta(days=1)
    with engine.begin() as c:
        assert store.keep_table(c, "power_station", p.table, day1) == {"added": 0, "changed": 0, "removed": 0}
        changed = [dict(r) for r in p.table[1:]]  # the first station drops off GSO's list
        changed[0]["capacity_mw"] = 400.0  # another is uprated
        changed.append({"id": "99", "name": "New Plant Sdn Bhd", "fuel": "Solar", "type": "LSS", "capacity_mw": 50.0,
                        "ppa_expiry": None, "ppa_expiry_label": None})
        assert store.keep_table(c, "power_station", changed, day2) == {"added": 1, "changed": 1, "removed": 1}
    with engine.connect() as c:
        t = analytics.table(c, "power_station")
    rows = {r["id"]: r for r in t["rows"]}
    assert len(rows) == 7 and rows["4"]["listed"] is False and rows["4"]["last_seen"] == day1.isoformat()
    assert rows["6"]["capacity_mw"] == 400.0 and rows["6"]["first_seen"] == day1.isoformat()
    assert {(x["id"], x["change"]) for x in t["changes"]} == {("4", "no longer listed"), ("6", "capacity_mw"), ("99", "added")}
    assert next(x for x in t["changes"] if x["change"] == "capacity_mw")["old"] == 375.0
    assert t["rows"][-1]["id"] == "4"  # stations GSO no longer lists come last


def test_headline_figures_are_kept_under_gso_labels():
    # Real answer saved by the probe at 13:14 MYT on 30 October 2026; the labels are from GSO's own page code.
    p = parse(get_adapter("headlines"), fixture_bytes("real/landing_headlines.json"), T.date())
    got = {r.series: (r.value, r.obs_time.astimezone(MYT).strftime("%d %b %H:%M")) for r in p.readings}
    assert got == {
        "current_grid_demand": (17672, "30 Oct 13:00"),
        "current_system_demand": (20308, "30 Oct 13:00"),
        "highest_grid_demand_recorded": (22014, "06 Aug 20:30"),
        "current_solar_generation": (4199, "30 Oct 13:00"),
        "current_bess": (0, "30 Oct 13:00"),
        "cross_border_exchange": (0, "30 Oct 13:00"),
    }
    assert "highest_energy_recorded" not in got  # its unit isn't confirmed yet, so it isn't kept


def test_full_power_station_list_matches_the_archived_total():
    # GSO's complete Power Station Info (probe, 30 Oct 2026): 55 stations adding up to the archive's capacity total.
    p = parse(get_adapter("power_station"), fixture_bytes("real/power_station.json"), T.date())
    assert len(p.table) == 55 and len({s["id"] for s in p.table}) == 55
    assert round(sum(s["capacity_mw"] for s in p.table), 2) == 29472.31
    assert {s["fuel"] for s in p.table} == {"Coal", "Gas", "Solar", "Water"}
    assert "Solar" in {s["type"] for s in p.table} and not any("\r" in (s["type"] or "") for s in p.table)


def test_cross_border_exchange_keeps_gso_labels_and_gaps():
    for name, first_day, points in (("cbpe_forecastchart", "2026-10-30", 28), ("cbpe_forecastchart_lastday", "2026-10-28", 124)):
        p = parse(get_adapter("cbpe"), fixture_bytes(f"real/{name}.json"), T.date())
        by = {}
        for r in p.readings:
            by.setdefault(r.series, []).append(r)
        assert set(by) == {"cbesre", "msbi"}  # LTMS is all empty at the moment: kept as gaps, not zeros
        assert all(len(v) == points for v in by.values()) and p.missing == points
        assert min(r.obs_time for r in p.readings).astimezone(MYT).strftime("%Y-%m-%d %H:%M") == f"{first_day} 00:00"


def test_record_values_are_never_stale(engine, settings):
    p = parse(get_adapter("headlines"), fixture_bytes("real/landing_headlines.json"), T.date())
    spec = get_adapter("headlines")
    with engine.begin() as c:
        ds = store.ensure_dataset(c, spec)
        ids = store.resolve_series(c, spec, ds, p.readings)
        store.apply_readings(c, p.readings, ids, run_id=None, snapshot_id=None, collected_at=T)
    with engine.connect() as c:
        st = {f["series"]: f for f in analytics.status(c, ["headlines"], True)["freshness"]}
    rec = st["headlines.highest_grid_demand_recorded"]
    assert rec["kind"] == "record" and rec["stale"] is False and rec["missing_24h"] is None


def test_cross_border_part_sent_as_null_is_no_data():
    # Seen live on 30 Oct 2026: a part came as a bare null; that crashed the whole collection cycle.
    d = json.loads(fixture_bytes("real/cbpe_forecastchart.json"))["d"].split("$")
    d[0] = "null"
    p = parse(get_adapter("cbpe"), json.dumps({"d": "$".join(d)}), T.date())
    assert {r.series for r in p.readings} == {"cbesre", "msbi"}


def test_one_collectors_bug_never_stops_the_others(engine, settings, client, fake, monkeypatch):
    from dataclasses import replace

    import gso_archive.collector as collector

    real_parse, real_collect = collector.parse, collector.collect_one

    def parse_with_bug(spec, *args, **kwargs):  # a bug while reading GSO's answer
        if spec.key == "headlines":
            raise TypeError("'NoneType' object is not iterable")
        return real_parse(spec, *args, **kwargs)

    monkeypatch.setattr(collector, "parse", parse_with_bug)
    s = replace(settings, adapters=["headlines", "other_re"], gso_live_enabled=True)
    fake.add("LandingPage.aspx/GetFeatureSectionData", "real/landing_headlines.json")
    fake.add("LandingPage.aspx/GetOtherREData", "real/landing_other_re.json")
    by = {r.adapter: r for r in collector.run_cycle(engine, s, client=client).results}
    assert by["headlines"].status == "failed" and by["headlines"].error_type == "parse_error"
    assert by["other_re"].status == "success"  # it still ran

    def collect_with_bug(engine, client, settings, spec, day, trigger="manual"):  # a bug anywhere else
        if spec.key == "headlines":
            raise RuntimeError("a bug outside the parser")
        return real_collect(engine, client, settings, spec, day, trigger)

    monkeypatch.setattr(collector, "collect_one", collect_with_bug)
    by = {r.adapter: r for r in collector.run_cycle(engine, s, client=client).results}
    assert by["headlines"].status == "failed" and by["headlines"].error_type == "unexpected_error"
    assert by["other_re"].status == "success"


def test_trial_reads_live_answers_and_writes_nothing(engine, settings, client, fake, monkeypatch):
    from gso_archive.trial import run_trial

    fake.add("LandingPage.aspx/GetGenMixData", "real/landing_genmix.json")
    fake.add("LandingPage.aspx/GetOtherREData", "real/landing_other_re.json")
    d = json.loads(fixture_bytes("real/cbpe_forecastchart.json"))["d"].split("$")
    d[0] = "null"  # the answer that crashed version 5.11 on its first live run
    fake.add("SystemData/CBPE.aspx/ForecastChartLastDay", json.dumps({"d": "$".join(d)}).encode())
    by = {r["adapter"]: r for r in run_trial(settings, ["genmix_live", "other_re", "cbpe"], client=client)}
    assert by["genmix_live"]["result"] == "ok" and by["genmix_live"]["readings"] > 0
    assert by["other_re"]["result"] == "ok"  # dated by the home page reading of the same trial
    assert by["cbpe"]["result"] == "ok" and set(by["cbpe"]["per_series"]) == {"cbesre", "msbi"}
    with engine.connect() as c:
        assert not c.execute(select(db.observations)).first()  # nothing written


def test_trial_reports_a_collector_bug_instead_of_crashing(settings, client, fake, monkeypatch):
    import gso_archive.trial as trial

    fake.add("LandingPage.aspx/GetOtherREData", "real/landing_other_re.json")
    monkeypatch.setattr(trial, "parse", lambda *a, **k: (_ for _ in ()).throw(TypeError("'NoneType' object is not iterable")))
    (r,) = trial.run_trial(settings, ["other_re"], client=client)
    assert r["result"].startswith("COLLECTOR BUG") and "NoneType" in r["error"]
