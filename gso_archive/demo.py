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
import dataclasses

from .adapters.base import Reading
from .adapters.gso_live import AVAILABILITY, GENMIX_LIVE, SOLAR_FARMS, SOLAR_FORECAST, SOLAR_PROFILE
from .adapters.registry import GENERATION_MIX, SYSTEM_DEMAND, TIELINE_EGAT, TIELINE_HVDC, TIELINE_PLTG
from .timeutil import MYT, UTC, utcnow

DEMO_NOTE = " DEMONSTRATION copy of the real layout: values are invented."
DEMO_SPECS = {key: dataclasses.replace(spec, verification="demo", description=spec.description + DEMO_NOTE)
              for key, spec in {"solar": SOLAR_PROFILE, "forecast": SOLAR_FORECAST, "genmix": GENMIX_LIVE,
                                "avail": AVAILABILITY, "farms": SOLAR_FARMS}.items()}
# Demo farms placed roughly in their state (made up, like every demo value) so the solar map has something to show.
DEMO_FARMS = [("DMOA", "KDAH", "North", "GRID", 50, 5.95, 100.55), ("DMOB", "PRAK", "North", "GRID", 30, 4.35, 101.05),
              ("DMOC", "SGOR", "Central", "DN", 13, 3.15, 101.45), ("DMOD", "NSLN", "Central", "GRID", 50, 2.75, 102.15),
              ("DMOE", "KLTN", "East", "GRID", 30, 5.70, 102.10), ("DMOF", "JHOR", "South", "DN", 20, 1.75, 103.50)]


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
    readings: dict[str, list[Reading]] = {k: [] for k in ("gen", "demand", "egat", "hvdc", "pltg", "solar", "forecast", "genmix",
                                                          "avail", "farms")}
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
        shape = _solar_shape(t, cloud)
        rooftop = {"nem": 0.75 * solar_tx, "fit": 0.08 * solar_tx, "selco": 0.17 * solar_tx}
        readings["solar"].append(Reading("grid", "Grid", utc_t, round(solar_tx, 1)))
        readings["solar"].append(Reading("distribution", "Distribution", utc_t, round(solar_dx * 0.3, 1)))
        for k, v in rooftop.items():
            readings["solar"].append(Reading(k, k.upper(), utc_t, round(v, 1), quality="estimate"))
        fc = (1900 * 2.3) * growth * _solar_shape(t, day_cloud * 0.95 + 0.05)
        readings["forecast"].append(Reading("total", "Forecast", utc_t, round(fc, 1), kind="forecast"))
        evening = 1 if 19 <= t.hour < 23 else 0
        midday = 1 if 11 <= t.hour < 15 else 0
        readings["genmix"].append(Reading("bess_discharge", "r[11]", utc_t, round(evening * rng.uniform(60, 100), 1)))
        readings["genmix"].append(Reading("bess_charge", "r[12]", utc_t, round(-midday * rng.uniform(20, 60), 1)))
        readings["genmix"].append(Reading("other_re", "r[7]", utc_t, round(170 + rng.gauss(0, 3), 1)))
        readings["genmix"].append(Reading("distribution_solar", "r[9]", utc_t, round(solar_dx * 0.3 + sum(rooftop.values()), 1)))
        for code, state, region, conn, cap, lat, lon in DEMO_FARMS:
            label = f"{code} ({state}, {region}, {'grid' if conn == 'GRID' else 'distribution'})"
            readings["farms"].append(Reading(code.lower(), code, utc_t, round(cap * shape * rng.uniform(0.8, 1.0), 1),
                                             name=f"Solar farm {label} — live output", unit="MW", latitude=lat, longitude=lon))
            if t.hour == 0 and t.minute == 0:
                readings["farms"].append(Reading(f"{code.lower()}_capacity", code, utc_t, float(cap), kind="capacity",
                                                 name=f"Solar farm {label} — capacity", unit="MW", latitude=lat, longitude=lon))
        if t.minute == 0:
            for k, v in (("coal", 11250), ("gas", 10700), ("cogen", 0), ("hydro", 2090), ("transmission_solar", round(solar_tx)),
                         ("distribution_solar", round(solar_dx * 0.3 + sum(rooftop.values()))), ("bess", 100)):
                readings["avail"].append(Reading(k, k, utc_t, float(v)))
        t += timedelta(minutes=interval_minutes)

    # Punch a deliberate gap so the dashboard's gap handling is visible in the demo.
    gap_start = (now - timedelta(days=3)).replace(hour=10, minute=0).astimezone(UTC)
    gap_end = gap_start + timedelta(hours=3)
    for key in readings:
        readings[key] = [r for r in readings[key] if not (gap_start <= r.obs_time < gap_end)]

    specs = {"gen": GENERATION_MIX, "demand": SYSTEM_DEMAND, "egat": TIELINE_EGAT, "hvdc": TIELINE_HVDC,
             "pltg": TIELINE_PLTG, "solar": DEMO_SPECS["solar"], "forecast": DEMO_SPECS["forecast"],
             "genmix": DEMO_SPECS["genmix"], "avail": DEMO_SPECS["avail"], "farms": DEMO_SPECS["farms"]}
    total = 0
    with engine.begin() as conn:
        for key, spec in specs.items():
            dataset_id = store.ensure_dataset(conn, spec, is_demo=True)
            ids = store.resolve_series(conn, spec, dataset_id, readings[key], is_demo=True)
            stats = store.apply_readings(conn, readings[key], ids, run_id=None, snapshot_id=None, collected_at=utcnow())
            total += stats.new
    return {"days": days, "interval_minutes": interval_minutes, "records": total}
