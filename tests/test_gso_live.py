"""GSO Solar page and home page collectors, tested on real answers saved on 28 October 2026 (tests/fixtures/real)."""

import json
from datetime import date, datetime, timezone

import pytest
from sqlalchemy import func, select

from gso_archive import db
from gso_archive.adapters import SchemaError, get_adapter, parse
from gso_archive.adapters.gso_live import _pick_day, parse_last_available
from gso_archive.collector import collect_one
from gso_archive.timeutil import MYT

from .conftest import fixture_bytes

UTC = timezone.utc
REF = datetime(2026, 10, 28, 13, 30, tzinfo=MYT)  # GSO's "last available" at the time the fixtures were saved
DAY = date(2026, 10, 28)


def by_series(payload):
    out = {}
    for r in payload.readings:
        out.setdefault(r.series, []).append(r)
    return out


def test_last_available():
    d = json.loads(fixture_bytes("real/solar_last_available.json"))["d"]
    assert parse_last_available(d) == REF
    with pytest.raises(SchemaError):
        parse_last_available("nonsense")


def test_solar_actual_matches_gso_page():
    p = parse(get_adapter("solar_profile"), fixture_bytes("real/solar_actual.json"), DAY, {"last_available": REF})
    s = by_series(p)
    assert set(s) == {"grid", "distribution", "nem", "fit", "selco"}
    assert all(len(v) == 81 for v in s.values())  # 00:00 … 13:20, every 10 minutes
    last = {k: v[-1] for k, v in s.items()}
    assert last["grid"].obs_time == datetime(2026, 10, 28, 13, 20, tzinfo=MYT).astimezone(UTC)
    assert last["grid"].value == 1615
    # GSO's own "current MW" (part 5 of the answer) is the sum of the five latest values.
    raw = json.loads(fixture_bytes("real/solar_actual.json"))["d"].split("$")
    assert sum(r.value for r in last.values()) == float(raw[5]) == 3939
    assert {r.quality for r in s["nem"]} == {"estimate"}  # GSO: "estimates based on registered data"
    assert s["grid"][0].value == 0 and s["grid"][0].quality == "ok"  # a real 0 at night stays 0


def test_solar_forecast():
    p = parse(get_adapter("solar_forecast"), fixture_bytes("real/solar_forecast.json"), DAY, {"last_available": REF})
    assert len(p.readings) == 144 and {r.kind for r in p.readings} == {"forecast"}
    peak = max(p.readings, key=lambda r: r.value)
    assert peak.value == 3616 and peak.obs_time.astimezone(MYT).strftime("%H:%M") == "13:20"  # GSO: "3,616 MW @ 13:20"
    near_midnight = parse(get_adapter("solar_forecast"), fixture_bytes("real/solar_forecast.json"), DAY,
                          {"last_available": datetime(2026, 10, 29, 0, 10, tzinfo=MYT)})
    assert not near_midnight.readings and near_midnight.rejected  # day is ambiguous: skipped, not guessed


def test_genmix_extras_and_bess():
    p = parse(get_adapter("genmix_live"), fixture_bytes("real/landing_genmix.json"), DAY, {})
    s = by_series(p)
    assert set(s) == {"tie_line_total", "other_re", "total_generation", "distribution_solar", "bess_discharge", "bess_charge"}
    assert s["total_generation"][-1].value == 18356
    assert s["total_generation"][-1].obs_time == datetime(2026, 10, 28, 13, 20, tzinfo=MYT).astimezone(UTC)
    assert min(r.value for r in s["bess_charge"]) < 0 <= max(r.value for r in s["bess_discharge"])
    assert all(r.quality == "ok" for r in s["bess_charge"])  # negative is normal for charging
    assert s["distribution_solar"][-1].value == 2324


def test_availability():
    p = parse(get_adapter("availability"), fixture_bytes("real/landing_sysav.json"), DAY, {})
    v = {r.series: r for r in p.readings}
    assert v["coal"].value == 11252 and v["bess"].value == 100
    assert v["coal"].obs_time == datetime(2026, 10, 28, 13, 20, tzinfo=MYT).astimezone(UTC)


def test_solar_farms():
    p = parse(get_adapter("solar_farms"), fixture_bytes("real/landing_solar_map.json"), DAY, {"last_available": REF})
    live = [r for r in p.readings if r.kind == "actual"]
    caps = [r for r in p.readings if r.kind == "capacity"]
    assert len(live) == len(caps) > 40
    ajns = next(r for r in live if r.series == "ajns")
    assert ajns.value == 24 and "KDAH" in ajns.name and "grid" in ajns.name
    assert next(r for r in caps if r.series == "ajns_capacity").value == 30


def test_pick_day_around_midnight():
    assert _pick_day(81, REF) == DAY
    assert _pick_day(144, datetime(2026, 10, 29, 0, 5, tzinfo=MYT)) == DAY  # yesterday's full list just after midnight
    assert _pick_day(1, datetime(2026, 10, 29, 0, 5, tzinfo=MYT)) == date(2026, 10, 29)


def test_gaps_are_missing_not_zero():
    raw = json.loads(fixture_bytes("real/solar_actual.json"))
    parts = raw["d"].split("$")
    grid = parts[0].split(",")
    grid[60] = ""  # GSO leaves gaps empty
    parts[0] = ",".join(grid)
    p = parse(get_adapter("solar_profile"), json.dumps({"d": "$".join(parts)}), DAY, {"last_available": REF})
    assert p.missing == 1 and len(by_series(p)["grid"]) == 80


def test_wrong_shapes_rejected():
    with pytest.raises(SchemaError):
        parse(get_adapter("solar_profile"), json.dumps({"d": "1,2$3"}), DAY, {"last_available": REF})
    with pytest.raises(SchemaError):
        parse(get_adapter("genmix_live"), json.dumps({"d": [1, 2]}), DAY, {})


def test_collect_solar_end_to_end(engine, settings, client, fake):
    fake.add("SystemData/Solar.aspx/GetLastAvailableData", "real/solar_last_available.json")
    fake.add("SystemData/Solar.aspx/GetSolarActualData", "real/solar_actual.json")
    r = collect_one(engine, client, settings, get_adapter("solar_profile"), DAY)
    assert r.status == "success" and r.records_new == 5 * 81
    assert [c.url.path for c in fake.calls if c.method == "POST"] == [
        "/SystemData/Solar.aspx/GetLastAvailableData", "/SystemData/Solar.aspx/GetSolarActualData"]
    again = collect_one(engine, client, settings, get_adapter("solar_profile"), DAY)
    assert again.records_new == 0 and again.records_unchanged == 5 * 81
    with engine.connect() as c:
        assert c.execute(select(func.count()).select_from(db.observations)).scalar() == 405


def test_series_are_named_and_time_asked_once(engine, settings, client, fake):
    fake.add("SystemData/Solar.aspx/GetLastAvailableData", "real/solar_last_available.json")
    fake.add("SystemData/Solar.aspx/GetSolarActualData", "real/solar_actual.json")
    fake.add("SystemData/Solar.aspx/GetSolarForecastData", "real/solar_forecast.json")
    collect_one(engine, client, settings, get_adapter("solar_profile"), DAY)
    collect_one(engine, client, settings, get_adapter("solar_forecast"), DAY)
    assert len(fake.posts("GetLastAvailableData")) == 1  # shared within a run
    assert not [c for c in fake.calls if c.method == "GET"]  # no page visits by default
    with engine.connect() as c:
        rows = {r.key: r for r in c.execute(select(db.series))}
    assert rows["solar_profile.grid"].name == "Grid (transmission) solar" and not rows["solar_profile.grid"].auto_discovered
    assert rows["solar_forecast.total"].kind == "forecast" and not rows["solar_forecast.total"].auto_discovered


# Real answers saved just after midnight, 00:32 MYT on 29 October 2026: before sunrise GSO's "last available" is
# 07:00 of the coming morning, a time still in the future, and the forecast is already the new day's.
NIGHT_LAST = parse_last_available(json.loads(fixture_bytes("real/solar_last_available_night.json"))["d"])
NIGHT_NOW = datetime(2026, 10, 29, 0, 32, tzinfo=MYT).astimezone(UTC)
NEW_DAY = date(2026, 10, 29)


def test_night_last_available_is_in_the_future():
    assert NIGHT_LAST == datetime(2026, 10, 29, 7, 0, tzinfo=MYT)


def test_night_solar_farm_readings_are_not_dated_in_the_future():
    p = parse(get_adapter("solar_farms"), fixture_bytes("real/landing_solar_map.json"), NEW_DAY,
              {"last_available": NIGHT_LAST, "now": NIGHT_NOW})
    live = [r for r in p.readings if r.kind == "actual"]
    # the clock rounded down to GSO's 10-minute steps, not 07:00
    assert {r.obs_time for r in live} == {datetime(2026, 10, 29, 0, 30, tzinfo=MYT).astimezone(UTC)}


def test_solar_farms_keep_their_location():
    p = parse(get_adapter("solar_farms"), fixture_bytes("real/landing_solar_map.json"), DAY, {"last_available": REF})
    ajns = next(r for r in p.readings if r.series == "ajns")
    assert (ajns.latitude, ajns.longitude) == (5.738311, 100.561308)


def test_solar_actual_just_after_midnight_belongs_to_the_new_day():
    p = parse(get_adapter("solar_profile"), fixture_bytes("real/solar_actual_after_midnight.json"), NEW_DAY,
              {"last_available": NIGHT_LAST, "now": NIGHT_NOW})
    grid = by_series(p)["grid"]
    assert [r.obs_time for r in grid] == [datetime(2026, 10, 29, 0, m, tzinfo=MYT).astimezone(UTC) for m in (0, 10)]


def test_forecast_day_comes_from_the_clock():
    spec, body = get_adapter("solar_forecast"), fixture_bytes("real/solar_forecast_after_midnight.json")
    p = parse(spec, body, NEW_DAY, {"last_available": NIGHT_LAST, "now": NIGHT_NOW})
    peak = max(p.readings, key=lambda r: r.value)
    # GSO's own label for this answer: "3,661 MW @ 12:20" — the new day's forecast, not a copy of yesterday's
    assert peak.value == 3661 and peak.obs_time == datetime(2026, 10, 29, 12, 20, tzinfo=MYT).astimezone(UTC)
    # within half an hour of midnight it is still skipped, whatever "last available" says
    early = parse(spec, body, NEW_DAY, {"last_available": NIGHT_LAST, "now": datetime(2026, 10, 29, 0, 10, tzinfo=MYT)})
    assert not early.readings and early.rejected


def test_evening_list_stays_on_its_own_day():
    # Seen on 28 October 2026: after sunset GSO's "last available" stayed at the last daylight reading while the list
    # kept growing. Judged by that time, the 20:40 list (124 readings) looked too long for the day and was filed under
    # the day before, so 27 October became a copy of the 28th. The real clock decides the day.
    parts = json.loads(fixture_bytes("real/solar_actual.json"))["d"].split("$")
    for i in range(5):
        vals = parts[i].split(",")
        parts[i] = ",".join(vals + ["0"] * (124 - len(vals)))
    sunset = datetime(2026, 10, 28, 18, 30, tzinfo=MYT)
    now = datetime(2026, 10, 28, 20, 42, tzinfo=MYT)
    p = parse(get_adapter("solar_profile"), json.dumps({"d": "$".join(parts)}), DAY,
              {"last_available": sunset, "now": now})
    grid = by_series(p)["grid"]
    assert len(grid) == 124
    assert grid[0].obs_time == datetime(2026, 10, 28, 0, 0, tzinfo=MYT).astimezone(UTC)
    assert grid[-1].obs_time == datetime(2026, 10, 28, 20, 30, tzinfo=MYT).astimezone(UTC)
