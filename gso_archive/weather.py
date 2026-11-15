"""Sunshine and cloud forecasts for the LSS solar farm regions, from Open-Meteo (open-meteo.com, free, no key;
data CC BY 4.0, credited on the Weather page). Not GSO data: kept as forecasts ("weather" dataset) so the Weather page
can set the next days' sunshine beside what the farms produced.

For each region (North, Central, South, East) the location is the capacity-weighted middle of its LSS farms, from the
solar map's coordinates. Open-Meteo answers one list per location with hourly values in UTC:
  shortwave_radiation  W/m², global horizontal irradiance, the mean over the hour that ENDS at the time given
  cloud_cover          %, at the time given
Each fetch covers yesterday, today and the next two days. After a failure it waits RETRY_AFTER before trying again. Every value is stored as a forecast with the time it was
fetched, so later fetches that change a value keep the earlier one (store._apply_forecast). Fetched every 3 hours.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime, timedelta

import httpx
from sqlalchemy import and_, desc, func, select
from sqlalchemy.engine import Connection, Engine

from . import db, store
from .adapters.base import AdapterSpec, FieldSpec, Reading
from .config import Settings
from .timeutil import UTC, ensure_utc, utcnow

log = logging.getLogger(__name__)

KEY = "weather"
URL = "https://api.open-meteo.com/v1/forecast"
EVERY = timedelta(hours=3)
RETRY_AFTER = timedelta(minutes=20)  # after a failure: one slow outside service must not slow every cycle (lesson 41)
TIMEOUT = 20.0
REGIONS = ("north", "central", "south", "east")
# Used only until the archive has the farms' coordinates: roughly the middle of each region's LSS farms (Nov 2026).
FALLBACK = {"north": (5.1, 100.6), "central": (3.1, 101.6), "south": (2.0, 103.1), "east": (4.4, 103.3)}

SPEC = AdapterSpec(
    key=KEY, name="Weather forecast at the LSS farm regions (Open-Meteo)", category="weather",
    page="https://open-meteo.com/", method="forecast", verification="third_party_documented",
    description="Hourly sunshine (global horizontal irradiance, W/m²) and cloud cover (%) forecast by Open-Meteo for "
                "the capacity-weighted middle of each region's LSS solar farms. Not GSO data. Weather data by "
                "Open-Meteo.com, CC BY 4.0.",
    fields={
        **{f"{r}_ghi": FieldSpec(f"{r}_ghi", f"Sunshine forecast — {r.title()} (W/m²)", "W/m²", "forecast", 0.0, 1500.0) for r in REGIONS},
        **{f"{r}_cloud": FieldSpec(f"{r}_cloud", f"Cloud cover forecast — {r.title()} (%)", "%", "forecast", 0.0, 100.0) for r in REGIONS},
    },
    takes_date=False,
)


@dataclass
class WeatherResult:
    status: str
    readings: int = 0
    error: str | None = None


def region_points(conn: Connection) -> dict[str, tuple[float, float]]:
    """Capacity-weighted middle of each region's LSS farms (from the solar map), or FALLBACK."""
    s, o = db.series.c, db.observations.c
    acc: dict[str, list[float]] = {r: [0.0, 0.0, 0.0] for r in REGIONS}
    for sid, key, name, lat, lon in conn.execute(
            select(s.id, s.key, s.name, s.latitude, s.longitude).where(and_(s.key.like("solar_farms.%_capacity")))):
        if lat is None or lon is None:
            continue
        region = next((r for r in REGIONS if f", {r.title()}," in (name or "")), None)
        cap = conn.execute(select(o.value).where(o.series_id == sid).order_by(desc(o.obs_time)).limit(1)).scalar()
        if region and cap:
            a = acc[region]
            a[0] += lat * cap; a[1] += lon * cap; a[2] += cap
    return {r: (round(a[0] / a[2], 3), round(a[1] / a[2], 3)) if a[2] else FALLBACK[r] for r, a in acc.items()}


def parse(answer: object, points: dict[str, tuple[float, float]]) -> list[Reading]:
    """Open-Meteo's answer (one object, or a list of one per location in the order asked) → forecast readings."""
    items = answer if isinstance(answer, list) else [answer]
    if len(items) != len(points):
        raise ValueError(f"expected {len(points)} locations, got {len(items)}")
    out: list[Reading] = []
    for (region, (lat, lon)), item in zip(points.items(), items):
        hourly = item.get("hourly") or {}
        times = hourly.get("time") or []
        for var, suffix in (("shortwave_radiation", "ghi"), ("cloud_cover", "cloud")):
            values = hourly.get(var) or []
            if len(values) != len(times):
                raise ValueError(f"{region}: {var} has {len(values)} values for {len(times)} times")
            for t, v in zip(times, values):
                if v is None:
                    continue
                when = datetime.fromisoformat(t).replace(tzinfo=UTC)
                out.append(Reading(f"{region}_{suffix}", var, when, float(v), kind="forecast", latitude=lat, longitude=lon))
    return out


def due(conn: Connection, now: datetime) -> bool:
    last = store.last_success(conn, KEY)
    if last is not None and now - last < EVERY:
        return False
    r = db.collection_runs.c
    failed = conn.execute(select(func.max(r.started_at)).where(and_(r.adapter == KEY, r.status == "failed"))).scalar()
    return failed is None or (last is not None and last > ensure_utc(failed)) or now - ensure_utc(failed) >= RETRY_AFTER


def collect_weather(engine: Engine, settings: Settings, now: datetime | None = None, client: httpx.Client | None = None,
                    force: bool = False) -> WeatherResult:
    """Fetch and store the forecast if it is due. Never raises: a failure is recorded as this collector's run."""
    now = now or utcnow()
    with engine.connect() as conn:
        if not force and not due(conn, now):
            return WeatherResult("skipped")
        points = region_points(conn)
    started = time.monotonic()  # the run is dated `now` (the cycle's clock), which due() compares with
    with engine.begin() as conn:
        run_id = store.start_run(conn, KEY, None, "schedule")
    params = {"latitude": ",".join(str(p[0]) for p in points.values()), "longitude": ",".join(str(p[1]) for p in points.values()),
              "hourly": "shortwave_radiation,cloud_cover", "timezone": "UTC", "past_days": 1, "forecast_days": 3}
    own = client is None
    client = client or httpx.Client(timeout=TIMEOUT, headers={"User-Agent": settings.user_agent, "Accept": "application/json"})
    try:
        res = client.get(URL, params=params)
        res.raise_for_status()
        readings = parse(res.json(), points)
        with engine.begin() as conn:
            dataset_id = store.ensure_dataset(conn, SPEC)
            series_ids = store.resolve_series(conn, SPEC, dataset_id, readings)
            stats = store.apply_readings(conn, readings, series_ids, run_id=run_id, snapshot_id=None, collected_at=now)
            store.finish_run(conn, run_id, status="success", started_at=now, http_status=res.status_code, records_seen=len(readings),
                             records_new=stats.new, records_revised=stats.revised, records_unchanged=stats.unchanged,
                             duration_ms=int((time.monotonic() - started) * 1000))
        return WeatherResult("success", len(readings))
    except Exception as exc:  # noqa: BLE001 - weather must never stop GSO collection
        kind = "network_error" if isinstance(exc, httpx.TransportError) else "http_error" if isinstance(exc, httpx.HTTPStatusError) else "parse_error"
        log.warning("weather failed: %s: %s", kind, exc)
        with engine.begin() as conn:
            store.finish_run(conn, run_id, status="failed", started_at=now, error_type=kind, error_message=str(exc)[:4000],
                             duration_ms=int((time.monotonic() - started) * 1000))
        return WeatherResult("failed", error=f"{kind}: {exc}")
    finally:
        if own:
            client.close()
