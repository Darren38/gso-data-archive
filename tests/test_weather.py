"""Sunshine forecasts for the LSS regions (gso_archive/weather.py), with a stand-in Open-Meteo answer shaped as its
documented multi-location reply: one object per location, hourly lists in UTC."""

from dataclasses import replace
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import select

from gso_archive import db
from gso_archive.weather import KEY, REGIONS, collect_weather, parse

UTC = timezone.utc
NOW = datetime(2026, 11, 15, 4, 0, tzinfo=UTC)  # 12:00 MYT


def _answer(n=4, hours=6):
    times = [(NOW - timedelta(hours=2) + timedelta(hours=h)).strftime("%Y-%m-%dT%H:%M") for h in range(hours)]
    return [{"latitude": 4.0 + i, "longitude": 101.0 + i, "hourly_units": {"shortwave_radiation": "W/m²", "cloud_cover": "%"},
             "hourly": {"time": times, "shortwave_radiation": [100.0 * (h + 1) + i for h in range(hours)],
                        "cloud_cover": [10.0 * h for h in range(hours)]}} for i in range(n)]


def test_parse_reads_every_region_and_hour():
    points = {r: (4.0, 101.0) for r in REGIONS}
    readings = parse(_answer(), points)
    assert len(readings) == 4 * 2 * 6 and all(r.kind == "forecast" for r in readings)
    north = sorted((r.obs_time, r.value) for r in readings if r.series == "north_ghi")
    assert north[0] == (NOW - timedelta(hours=2), 100.0)


def test_collect_stores_forecasts_then_waits_three_hours(engine, settings):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, json=_answer())

    client = httpx.Client(transport=httpx.MockTransport(handler))
    s = replace(settings, weather_enabled=True)
    assert collect_weather(engine, s, NOW, client=client).status == "success"
    assert set(calls[0].url.params["hourly"].split(",")) == {"shortwave_radiation", "cloud_cover"}
    with engine.connect() as c:
        keys = {k for (k,) in c.execute(select(db.series.c.key).where(db.series.c.key.like("weather.%")))}
        assert keys == {f"weather.{r}_{v}" for r in REGIONS for v in ("ghi", "cloud")}
        assert c.execute(select(db.forecasts)).first() is not None
    assert collect_weather(engine, s, NOW + timedelta(hours=1), client=client).status == "skipped"
    assert collect_weather(engine, s, NOW + timedelta(hours=3), client=client).status == "success"


def test_a_failure_is_recorded_not_raised(engine, settings):
    client = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json={"error": True, "reason": "x"})))
    s = replace(settings, weather_enabled=True)
    r = collect_weather(engine, s, NOW, client=client)
    assert r.status == "failed" and "parse_error" in r.error
    # one failure: not tried again for 20 minutes, so a slow outside service can't slow every collection cycle
    assert collect_weather(engine, s, NOW + timedelta(minutes=5), client=client).status == "skipped"
    assert collect_weather(engine, s, NOW + timedelta(minutes=21), client=client).status == "failed"
    with engine.connect() as c:
        run = c.execute(select(db.collection_runs).where(db.collection_runs.c.adapter == KEY)).first()
        assert run.status == "failed"
