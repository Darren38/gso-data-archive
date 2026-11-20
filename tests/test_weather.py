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


def test_too_many_requests_waits_an_hour(engine, settings):
    client = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(429, json={"error": True})))
    s = replace(settings, weather_enabled=True)
    assert collect_weather(engine, s, NOW, client=client).status == "failed"
    assert collect_weather(engine, s, NOW + timedelta(minutes=30), client=client).status == "skipped"
    assert collect_weather(engine, s, NOW + timedelta(minutes=61), client=client).status == "failed"


# --- measured sunshine (satellite, irradiance.py) ------------------------------------------------------------------
from gso_archive import irradiance  # noqa: E402


def _sat(n=4):
    times = [(NOW - timedelta(hours=3) + timedelta(hours=h)).strftime("%Y-%m-%dT%H:%M") for h in range(5)]
    return [{"hourly_units": {"shortwave_radiation": "W/m²"},
             "hourly": {"time": times, "shortwave_radiation": [500.0 + i, 600.0, 700.0, None, None]}} for i in range(n)]


def test_satellite_sunshine_is_kept_as_hourly_readings_and_unprocessed_hours_skipped(engine, settings):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, json=_sat())

    s = replace(settings, weather_enabled=True)
    client = httpx.Client(transport=httpx.MockTransport(handler))
    assert irradiance.collect_irradiance(engine, s, NOW, client=client).status == "success"
    q = calls[0].url.params
    assert q["models"] == "jma_jaxa_himawari" and q["hourly"] == "shortwave_radiation" and calls[0].url.host == "satellite-api.open-meteo.com"
    with engine.connect() as c:
        rows = c.execute(select(db.series.c.key, db.series.c.kind).where(db.series.c.key.like("irradiance.%"))).all()
        assert {k for k, _ in rows} == {f"irradiance.{r}_ghi" for r in REGIONS} and {k for _, k in rows} == {"actual"}
        n = c.execute(select(db.observations.c.value).join(db.series, db.series.c.id == db.observations.c.series_id)
                      .where(db.series.c.key == "irradiance.north_ghi")).all()
        assert sorted(v for (v,) in n) == [500.0, 600.0, 700.0]  # the two null (not yet processed) hours are not kept
    # hourly, with the same back-off as the forecast
    assert irradiance.collect_irradiance(engine, s, NOW + timedelta(minutes=30), client=client).status == "skipped"
    assert irradiance.collect_irradiance(engine, s, NOW + timedelta(minutes=61), client=client).status == "success"


def test_satellite_sunshine_never_hides_a_gso_outage(monkeypatch):
    """The health check's "newest reading" counts GSO's own collectors only, not hourly satellite sunshine."""
    import json as _json

    from gso_archive import health

    now = datetime.now(timezone.utc)
    iso = lambda t: t.isoformat().replace("+00:00", "Z")  # noqa: E731
    status = {"live_enabled": True, "collector_heartbeat": {"cycle_started_at": now.isoformat()},
              "adapters": [{"adapter": "genmix_live", "enabled": True}, {"adapter": "irradiance", "enabled": False}],
              "freshness": [{"series": "genmix_live.total_generation", "kind": "actual", "latest_obs_time": iso(now - timedelta(hours=5))},
                            {"series": "irradiance.north_ghi", "kind": "actual", "latest_obs_time": iso(now - timedelta(minutes=50))}]}
    pages = {"": b"GSO Grid Archive", "data/meta.json": b"{}", "data/status.json": _json.dumps(status).encode()}
    monkeypatch.setattr(health, "_get", lambda url, timeout=30: pages[url.split("example.test/", 1)[1]])
    notes = health.check_site("https://example.test/")["notes"]  # listed (GSO's side), never emailed
    assert any("newest GSO reading is 300 min old" in n for n in notes)
