"""Measured sunshine at the LSS solar farm regions: hourly global horizontal irradiance estimated from the Himawari-9
weather satellite (JMA/JAXA), served free by Open-Meteo's satellite radiation API (data CC BY 4.0, credited on the
Weather page). Not GSO data.

Chosen on 16 Nov 2026 after a trial on GitHub (`gso-archive irradiance-trial`): for all four regions it gave hourly
values (W/m²) with the newest hour about 1 hour behind real time, so it can be set beside the same day's LSS output.
NREL's NSRDB covers Malaysia only for 2016-2020, and NASA POWER's hourly data had nothing for the last 14 days, so
neither can be compared with GSO's readings.

  https://satellite-api.open-meteo.com/v1/archive?models=jma_jaxa_himawari&hourly=shortwave_radiation&past_days=2
  shortwave_radiation  W/m², the average over the hour that ENDS at the time given (UTC); hours not yet processed are null

Fetched every hour with the last 2 days, so late hours are filled in and changed values are kept as revisions. Kept as
"actual" readings (`irradiance.<region>_ghi`). The same locations as the forecast (weather.region_points).
"""

from __future__ import annotations

from datetime import datetime, timedelta

import httpx
from sqlalchemy.engine import Engine

from .adapters.base import AdapterSpec, FieldSpec, Reading
from .config import Settings
from .timeutil import UTC
from .weather import REGIONS, WeatherResult, collect_from

KEY = "irradiance"
URL = "https://satellite-api.open-meteo.com/v1/archive"
MODEL = "jma_jaxa_himawari"
EVERY = timedelta(hours=1)

SPEC = AdapterSpec(
    key=KEY, name="Measured sunshine at the LSS farm regions (Himawari satellite, via Open-Meteo)", category="weather",
    page="https://open-meteo.com/en/docs/satellite-radiation-api", method="archive", verification="third_party_documented",
    description="Hourly sunshine reaching the ground (global horizontal irradiance, W/m²) estimated from the Himawari-9 "
                "weather satellite for the capacity-weighted middle of each region's LSS solar farms. Not GSO data. "
                "Weather data by Open-Meteo.com, CC BY 4.0.",
    fields={f"{r}_ghi": FieldSpec(f"{r}_ghi", f"Measured sunshine — {r.title()} (W/m², satellite)", "W/m²", "actual", 0.0, 1500.0)
            for r in REGIONS},
    takes_date=False,
)


def parse(answer: object, points: dict[str, tuple[float, float]]) -> list[Reading]:
    """Open-Meteo's satellite answer (one object, or one per location in the order asked) → readings; nulls skipped."""
    items = answer if isinstance(answer, list) else [answer]
    if len(items) != len(points):
        raise ValueError(f"expected {len(points)} locations, got {len(items)}")
    out: list[Reading] = []
    for (region, (lat, lon)), item in zip(points.items(), items):
        hourly = (item or {}).get("hourly") or {}
        times, values = hourly.get("time") or [], hourly.get("shortwave_radiation") or []
        if len(times) != len(values):
            raise ValueError(f"{region}: {len(values)} values for {len(times)} times")
        for t, v in zip(times, values):
            if v is None:
                continue
            out.append(Reading(f"{region}_ghi", "shortwave_radiation", datetime.fromisoformat(t).replace(tzinfo=UTC),
                               float(v), latitude=lat, longitude=lon))
    return out


def collect_irradiance(engine: Engine, settings: Settings, now: datetime | None = None, client: httpx.Client | None = None,
                       force: bool = False) -> WeatherResult:
    """Fetch and store the last 2 days of measured sunshine if due (hourly). Never raises."""
    return collect_from(engine, settings, now, client, force, key=KEY, spec=SPEC, url=URL, every=EVERY,
                        params={"hourly": "shortwave_radiation", "models": MODEL, "timezone": "UTC", "past_days": 2},
                        read=parse)
