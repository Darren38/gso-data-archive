"""Registry of GSO dataset adapters.

`verification` records how much we actually know about each source:

* ``verified`` – request/response observed first-hand by this project (from GitHub's servers, 28 Oct 2026).
* ``third_party_documented`` – endpoint, parameters and field names taken from
  the maintained open-source Electricity Maps parser (electricitymap/contrib/
  parsers/GSO.py and capacity_parsers/MY_WM.py). Not yet observed first-hand.
* ``unverified`` – endpoint inferred by analogy with the other GSO pages; must be
  confirmed with ``gso-archive probe`` before enabling.

Nothing here is invented beyond what those labels state. See
docs/SOURCE_INVESTIGATION.md.
"""

from __future__ import annotations

from datetime import date, datetime

from ..timeutil import MYT, UTC
from .base import (
    AdapterSpec,
    FieldSpec,
    ParsedPayload,
    Reading,
    SchemaError,
    schema_signature,
    slugify,
    to_number,
)

MAX_GEN = 30000.0  # MW — generous sanity ceiling for Peninsular Malaysia


def _gen(series: str, name: str, *, daylight: bool = False) -> FieldSpec:
    return FieldSpec(series, name, "MW", "actual", 0.0, MAX_GEN, daylight_only=daylight)


GENERATION_MIX = AdapterSpec(
    key="generation_mix",
    name="Current generation by fuel",
    category="generation",
    page="SystemData/CurrentGen.aspx",
    method="GetChartDataSource",
    verification="verified",
    description=(
        "Generation by fuel type for Peninsular Malaysia, one record per timestamp. "
        "Includes a 'Solar' field, which is this archive's primary solar series."
    ),
    fields={
        "Coal": _gen("coal", "Coal"),
        "Gas": _gen("gas", "Gas"),
        "CoGen": _gen("cogen", "Co-generation"),
        "Oil": _gen("oil", "Oil"),
        "Hydro": _gen("hydro", "Hydro"),
        "Solar": _gen("solar", "Solar (as published in generation mix)", daylight=True),
    },
    time_fields=("DT",),
    default_min=0.0,
    default_max=MAX_GEN,
)

SYSTEM_DEMAND = AdapterSpec(
    key="system_demand",
    name="System demand",
    category="demand",
    page="SystemData/SystemDemand.aspx",
    method="GetChartDataSource",
    verification="verified",
    description="Peninsular Malaysia system demand profile.",
    fields={"MW": FieldSpec("demand", "System demand", "MW", "actual", 0.0, MAX_GEN)},  # every 10 minutes
    time_fields=("DT",),
    default_min=0.0,
    default_max=MAX_GEN,
)


def _tieline(line: str, label: str) -> AdapterSpec:
    return AdapterSpec(
        key=f"tieline_{line.lower()}",
        name=f"Tie-line {line} ({label})",
        category="tieline",
        page="SystemData/TieLine.aspx",
        method="GetChartDataSource",
        verification="verified",
        description=(
            f"Power flow on the {line} interconnection ({label}), stored exactly as published. "
            "GSO's sign convention is not documented on any page we could verify; "
            "Electricity Maps treats positive values as flow out of Peninsular Malaysia."
        ),
        fields={"MW": FieldSpec("flow", f"{line} flow (as published)", "MW", "actual", -5000.0, 5000.0)},
        time_fields=("Tarikhmasa", "DT"),
        ignore_fields=("Line",),  # e.g. "TIE-HVDC" (observed 28 Oct 2026)
        extra_params={"Line": line},
        default_min=-5000.0,
        default_max=5000.0,
    )


TIELINE_EGAT = _tieline("EGAT", "Thailand, HVAC")
TIELINE_HVDC = _tieline("HVDC", "Thailand, HVDC")
TIELINE_PLTG = _tieline("PLTG", "Singapore")


def _power_station_transform(spec: AdapterSpec, records: list[dict], day: date) -> ParsedPayload:
    """Installed capacity snapshot, aggregated by fuel. Stamped at 00:00 MYT of the collection day."""
    out = ParsedPayload(signature=schema_signature(records))
    if not records:
        return out
    fuel_key = next((k for k in ("Fuel", "FuelType", "Fuel Type") if k in records[0]), None)
    cap_key = next((k for k in records[0] if "capacity" in k.lower()), None)
    if fuel_key is None or cap_key is None:
        raise SchemaError(f"power station records missing fuel/capacity fields: {sorted(records[0])}")
    totals: dict[str, float] = {}
    for index, rec in enumerate(records):
        try:
            value = to_number(rec.get(cap_key))
        except ValueError:
            out.rejected.append(f"record {index}: invalid capacity {rec.get(cap_key)!r}")
            continue
        if value is None:
            out.missing += 1
            continue
        fuel = str(rec.get(fuel_key) or "unknown").strip()
        totals[fuel] = totals.get(fuel, 0.0) + value
    stamp = datetime(day.year, day.month, day.day, tzinfo=MYT).astimezone(UTC)
    for fuel, total in sorted(totals.items()):
        out.readings.append(
            Reading(f"capacity_{slugify(fuel)}", fuel, stamp, total, kind="capacity")
        )
    if totals:
        out.readings.append(Reading("capacity_total", "*", stamp, sum(totals.values()), kind="capacity"))
    out.table = [_station(rec, cap_key, fuel_key) for rec in records]
    return out


def _station(rec: dict, cap_key: str, fuel_key: str) -> dict:
    """One row of GSO's Power Station Info, as GSO gives it (seen 30 Oct 2026: ID, Name, Fuel (padded), Type,
    "Capacity (MW)", PPAExpiry "2037-02-01T00:00:00" and "PPA/SLA Expiry Year" "2037 Feb")."""
    def text(key):
        value = rec.get(key)
        return str(value).strip() or None if value is not None else None

    try:
        capacity = to_number(rec.get(cap_key))
    except ValueError:
        capacity = None
    ident = rec.get("ID")
    expiry = text("PPAExpiry")
    return {
        "id": str(int(ident)) if isinstance(ident, (int, float)) else text("Name") or text("Station"),
        "name": text("Name") or text("Station"),
        "fuel": text(fuel_key),
        "type": text("Type"),
        "capacity_mw": capacity,
        "ppa_expiry": expiry[:10] if expiry else None,
        "ppa_expiry_label": text("PPA/SLA Expiry Year"),
    }


POWER_STATION = AdapterSpec(
    key="power_station",
    name="Power stations and installed capacity",
    category="capacity",
    page="SystemData/PowerStation.aspx",
    method="GetDataSource",
    verification="verified",
    description="GSO's Power Station Info, once a day: every station (name, fuel, type, capacity, PPA/SLA expiry), "
                "kept with every change GSO makes, and the capacity summed by fuel.",
    takes_date=False,
    min_interval_seconds=24 * 3600,
    default_unit="MW",
    transform=_power_station_transform,
)

from .gso_live import AVAILABILITY, GENMIX_LIVE, OTHER_RE, SOLAR_FARMS, SOLAR_FORECAST, SOLAR_PROFILE  # noqa: E402

# System constraints: no public data address was found on gso.org.my (checked 28 Oct 2026).
NOT_IMPLEMENTED = {
    "constraints": "No public GSO system-constraints data was found on gso.org.my (pages checked 28 October 2026).",
}

ADAPTERS: dict[str, AdapterSpec] = {
    spec.key: spec
    for spec in (
        GENERATION_MIX,
        SYSTEM_DEMAND,
        TIELINE_EGAT,
        TIELINE_HVDC,
        TIELINE_PLTG,
        POWER_STATION,
        SOLAR_PROFILE,
        SOLAR_FORECAST,
        GENMIX_LIVE,
        OTHER_RE,
        AVAILABILITY,
        SOLAR_FARMS,
    )
}


def get_adapter(key: str) -> AdapterSpec:
    try:
        return ADAPTERS[key]
    except KeyError:
        raise KeyError(f"unknown adapter {key!r}; known: {', '.join(sorted(ADAPTERS))}") from None
