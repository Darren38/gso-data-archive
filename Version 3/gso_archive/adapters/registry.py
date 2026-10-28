"""Registry of GSO dataset adapters.

`verification` records how much we actually know about each source:

* ``verified`` – request/response observed first-hand by this project.
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
    verification="third_party_documented",
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
    verification="third_party_documented",
    description="Peninsular Malaysia system demand profile.",
    fields={"MW": FieldSpec("demand", "System demand", "MW", "actual", 0.0, MAX_GEN)},
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
        verification="third_party_documented",
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
    return out


POWER_STATION = AdapterSpec(
    key="power_station",
    name="Installed capacity by fuel",
    category="capacity",
    page="SystemData/PowerStation.aspx",
    method="GetDataSource",
    verification="third_party_documented",
    description="Power station list with installed capacity; archived as a daily snapshot summed by fuel.",
    takes_date=False,
    min_interval_seconds=24 * 3600,
    default_unit="MW",
    transform=_power_station_transform,
)

SOLAR_PROFILE = AdapterSpec(
    key="solar_profile",
    name="Solar profile",
    category="solar",
    page="SystemData/Solar.aspx",
    method="GetChartDataSource",
    verification="unverified",
    description=(
        "The GSO Solar Profile page. Endpoint name and parameters are INFERRED from the other "
        "SystemData pages and have not been observed. Field names are unknown, so every numeric "
        "field is auto-discovered (e.g. transmission/distribution solar, forecasts) and stored "
        "under its source name. Run `gso-archive probe` from an allowed network to verify."
    ),
    default_min=0.0,
    default_max=MAX_GEN,
)

# BESS and system constraints: no data-access method has been identified, so no
# adapter is registered. They are listed for the dashboard's status pages only.
NOT_IMPLEMENTED = {
    "bess": "No public GSO BESS data endpoint identified yet. Needs first-hand inspection of gso.org.my.",
    "constraints": "No public GSO system-constraints endpoint identified yet. Needs first-hand inspection.",
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
    )
}


def get_adapter(key: str) -> AdapterSpec:
    try:
        return ADAPTERS[key]
    except KeyError:
        raise KeyError(f"unknown adapter {key!r}; known: {', '.join(sorted(ADAPTERS))}") from None
