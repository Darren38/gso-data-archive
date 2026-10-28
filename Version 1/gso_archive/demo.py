"""DEMONSTRATION data generator.

Writes synthetic data into a *separate* database (default data/demo.sqlite3)
so the dashboard can be developed and reviewed without GSO access. Every
dataset and series it creates has is_demo = true, verification = "demo", and
the dashboard shows a persistent "Demonstration data" banner. The generator
refuses to write into a database that already holds non-demo data.

The curves are invented shapes (solar bell curve, two-peak demand, etc.).
They are NOT GSO readings and must never be presented as such.
"""

from __future__ import annotations

import math
import random
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.engine import Engine

from . import db, store
from .adapters.base import AdapterSpec, FieldSpec, Reading
from .adapters.registry import GENERATION_MIX, SYSTEM_DEMAND, TIELINE_EGAT, TIELINE_HVDC, TIELINE_PLTG
from .timeutil import MYT, UTC, utcnow

DEMO_SOLAR = AdapterSpec(
    key="solar_profile",
    name="Solar profile (DEMO layout)",
    category="solar",
    page="SystemData/Solar.aspx",
    method="(demo)",
    verification="demo",
    description=(
        "DEMONSTRATION ONLY. Hypothetical transmission/distribution/forecast split used to exercise the "
        "dashboard. Whether GSO publishes these fields is unverified."
    ),
    fields={
        "Transmission": FieldSpec("transmission", "Transmission-connected solar (DEMO)", "MW", "actual", 0.0),
        "Distribution": FieldSpec("distribution", "Distribution-connected solar (DEMO)", "MW", "actual", 0.0),
        "Forecast": FieldSpec("forecast", "Solar forecast (DEMO)", "MW", "forecast", 0.0),
    },
)


class DemoRefused(Exception):
    pass


def _solar_shape(local: datetime, cloud: float) -> float:
    hours = local.hour + local.minute / 60
    if hours < 7 or hours > 19.25:
        return 0.0
    base = math.sin(math.pi * (hours - 7) / 12.25) ** 1.4
    return max(0.0, base * cloud)


def seed_demo(engine: Engine, days: int = 60, interval_minutes: int = 30, seed: int = 7) -> dict:
    with engine.connect() as conn:
        real = conn.execute(select(db.datasets.c.key).where(db.datasets.c.is_demo.is_(False))).first()
    if real:
        raise DemoRefused("database already contains non-demo datasets; refusing to mix demo data into it")

    rng = random.Random(seed)
    now = utcnow().astimezone(MYT).replace(second=0, microsecond=0)
    now = now - timedelta(minutes=now.minute % interval_minutes)
    start = (now - timedelta(days=days)).replace(hour=0, minute=0)
    readings: dict[str, list[Reading]] = {k: [] for k in ("gen", "demand", "egat", "hvdc", "pltg", "solar")}
    t = start
    day_cloud = 1.0
    while t <= now:
        if t.hour == 0 and t.minute == 0:
            day_cloud = rng.uniform(0.45, 1.0)
            growth = 1 + 0.15 * ((t - start).days / max(days, 1))
        cloud = day_cloud * rng.uniform(0.85, 1.0)
        hours = t.hour + t.minute / 60
        weekend = t.weekday() >= 5
        demand = (11500 + 3800 * math.exp(-((hours - 15) ** 2) / 18) + 1200 * math.exp(-((hours - 21) ** 2) / 4)
                  - 1800 * math.exp(-((hours - 5) ** 2) / 8)) * (0.9 if weekend else 1.0) + rng.gauss(0, 120)
        solar_tx = 1900 * growth * _solar_shape(t, cloud) + max(0, rng.gauss(0, 15)) * (_solar_shape(t, 1) > 0)
        solar_dx = 0.55 * solar_tx + max(0, rng.gauss(0, 10)) * (solar_tx > 0)
        hydro = 900 + 700 * math.exp(-((hours - 19.5) ** 2) / 6) + rng.gauss(0, 40)
        gas = 0.38 * demand + rng.gauss(0, 80)
        coal = max(0, demand - gas - hydro - solar_tx - 250 - rng.uniform(0, 100))
        utc_t = t.astimezone(UTC)
        for field, value in (("Coal", coal), ("Gas", gas), ("CoGen", 210 + rng.gauss(0, 10)),
                             ("Oil", 0.0), ("Hydro", hydro), ("Solar", solar_tx)):
            readings["gen"].append(Reading(GENERATION_MIX.fields[field].series, field, utc_t, round(value, 1)))
        readings["demand"].append(Reading("demand", "MW", utc_t, round(demand, 1)))
        readings["egat"].append(Reading("flow", "MW", utc_t, round(rng.gauss(-40, 25), 1)))
        readings["hvdc"].append(Reading("flow", "MW", utc_t, round(rng.gauss(120, 60), 1)))
        readings["pltg"].append(Reading("flow", "MW", utc_t, round(rng.gauss(60, 80), 1)))
        readings["solar"].append(Reading("transmission", "Transmission", utc_t, round(solar_tx, 1)))
        readings["solar"].append(Reading("distribution", "Distribution", utc_t, round(solar_dx, 1)))
        fc = 1900 * growth * _solar_shape(t, day_cloud * 0.95 + 0.05)
        readings["solar"].append(Reading("forecast", "Forecast", utc_t, round(fc, 1), kind="forecast"))
        t += timedelta(minutes=interval_minutes)

    # Punch a deliberate gap so the dashboard's gap handling is visible in the demo.
    gap_start = (now - timedelta(days=3)).replace(hour=10, minute=0).astimezone(UTC)
    gap_end = gap_start + timedelta(hours=3)
    for key in readings:
        readings[key] = [r for r in readings[key] if not (gap_start <= r.obs_time < gap_end)]

    specs = {"gen": GENERATION_MIX, "demand": SYSTEM_DEMAND, "egat": TIELINE_EGAT, "hvdc": TIELINE_HVDC,
             "pltg": TIELINE_PLTG, "solar": DEMO_SOLAR}
    total = 0
    with engine.begin() as conn:
        for key, spec in specs.items():
            dataset_id = store.ensure_dataset(conn, spec, is_demo=True)
            ids = store.resolve_series(conn, spec, dataset_id, readings[key], is_demo=True)
            stats = store.apply_readings(conn, readings[key], ids, run_id=None, snapshot_id=None, collected_at=utcnow())
            total += stats.new
    return {"days": days, "interval_minutes": interval_minutes, "records": total}
