"""Collectors for GSO's Solar page and home page data (verified first-hand on 28 October 2026).

These answers are not JSON tables: "d" is text joined with "$", each part a comma-separated list of values every
10 minutes from 00:00 Malaysia time for *today only*. The meaning of each part comes from GSO's own scripts
(Scripts/Solar.v19.js and Scripts/SolarLandingPage.v5.js), quoted next to each mapping below. Because only today
is published, these collectors must run continuously; there is nothing to back-fill.
"""

from __future__ import annotations

import json
import re
from datetime import date, datetime, timedelta

from ..timeutil import MYT, UTC
from .base import AdapterSpec, ParsedPayload, Reading, SchemaError, assess_quality, FieldSpec

SLOT_MINUTES = 10


def _values(text: str) -> list[float | None]:
    out: list[float | None] = []
    for item in text.split(","):
        item = item.strip()
        if item == "":
            out.append(None)  # GSO leaves gaps empty; never treated as zero
            continue
        try:
            out.append(float(item))
        except ValueError:
            raise SchemaError(f"not a number in a value list: {item!r}") from None
    return out


def _pick_day(count: int, ref: datetime) -> date:
    """The day a list of `count` 10-minute values belongs to. Just after midnight GSO can still be serving
    yesterday's full list, so a list longer than today could have produced belongs to the day before."""
    local = ref.astimezone(MYT)
    slot = (local.hour * 60 + local.minute) // SLOT_MINUTES
    return local.date() - timedelta(days=1) if count > slot + 2 else local.date()


def _reading_time(ctx: dict) -> datetime:
    """When the newest solar reading was taken: GSO's "last available", but never later than the real clock
    (rounded down to GSO's 10-minute steps), because before sunrise GSO's answer is 07:00 of the coming morning."""
    t = ctx["last_available"]
    now = ctx.get("now")
    if now is not None:
        now = now.astimezone(MYT)
        step = now.replace(minute=now.minute - now.minute % SLOT_MINUTES, second=0, microsecond=0)
        t = min(t, step)
    return t


def _slot(day: date, index: int) -> datetime:
    return (datetime(day.year, day.month, day.day, tzinfo=MYT) + timedelta(minutes=SLOT_MINUTES * index)).astimezone(UTC)


def parse_last_available(d: object) -> datetime:
    """Solar.aspx/GetLastAvailableData: "2026-10-28 13:30|28/10/2026 13:30" (time of the newest solar reading).

    Before sunrise GSO answers 07:00 of the day, a time still in the future (seen at 00:32 on 29 Oct 2026:
    "2026-10-29 07:00"; GSO's Solar.v19.js compares it with 07:00 too). Use `_reading_time` to date readings."""
    if not isinstance(d, str) or "|" not in d:
        raise SchemaError(f"unexpected last-available answer: {d!r}")
    return datetime.strptime(d.split("|")[0].strip(), "%Y-%m-%d %H:%M").replace(tzinfo=MYT)


def _series(spec: AdapterSpec, out: ParsedPayload, values: list[float | None], day: date, series: str,
            source: str, quality: str | None = None) -> None:
    fspec = spec.fields[series]
    for i, v in enumerate(values):
        if v is None:
            out.missing += 1
            continue
        t = _slot(day, i)
        out.readings.append(Reading(series, source, t, v, kind=fspec.kind,
                                    quality=quality or assess_quality(fspec, v, t)))


# --- Solar.aspx/GetSolarActualData ------------------------------------------------------------------------------
# Solar.v19.js, DrawSolarChart:  r = response.split('$')
#   r[0] ActualToday -> chart series 'Grid'          r[1] ActualDistToday -> 'Distribution'
#   r[2] NEM   r[3] FIT ('FiT')   r[4] SELCO   ("NEM, FiT and SELCO values are estimates based on registered data")
#   r[5] currentMW (= sum of the five latest values)   r[6] pastChange
SOLAR_PARTS = [("grid", "Grid"), ("distribution", "Distribution"), ("nem", "NEM"), ("fit", "FiT"), ("selco", "SELCO")]


# r[7] is the one labelled part: GSO's Distribution Solar split as its pie draws it, e.g.
#   [{"y": 2324, "drilldown": {"name": "Distribution Solar", "categories": ["LSS", "NEM", "FiT", "SELCO"],
#                              "data": [324, 1511, 153, 336]}}]
# Its four figures equal lists r[1]-r[4] at the newest reading (seen 28 and 30 October 2026), so they name the lists.
LABELS = {"LSS": 1, "NEM": 2, "FiT": 3, "SELCO": 4}


def _order_by_labels(parts: list[str], lists: list[list[float | None]]) -> tuple[list[int], str | None]:
    """Which list is Distribution, NEM, FiT and SELCO, by GSO's own labels in r[7]: the order to read r[0]-r[4] in,
    and a note when it isn't the usual one. The labelled figures are looked for at the newest moment first, then
    earlier ones (after sunset they may stay at an earlier reading, like GSO's "last available"). Moments that can't
    tell (empty r[7] just after midnight, night zeros, equal figures) keep the usual order. This never stops
    collection: labels that match nothing only leave a note, which marks the run as a format change."""
    usual = [0, 1, 2, 3, 4]
    try:
        pie = json.loads(parts[7]) if len(parts) > 7 and parts[7].strip() else None
        drill = (pie[0] if isinstance(pie, list) else pie)["drilldown"]
        labelled = dict(zip(drill["categories"], (float(v) for v in drill["data"])))
    except (ValueError, KeyError, TypeError, IndexError):
        return usual, None  # no labels to check against
    if set(labelled) != set(LABELS):
        return usual, f"GSO's distribution solar labels changed: {sorted(labelled)}"
    want = [labelled[name] for name in sorted(LABELS, key=LABELS.get)]  # in the usual order
    if not any(want):
        return usual, None  # night: every list is zero, nothing to tell them apart
    for j in range(len(lists[1]) - 1, -1, -1):
        at = [lists[i][j] for i in range(1, 5)]
        if at == want:
            return usual, None  # GSO's labels agree with the usual order
        if None not in at and sorted(at) == sorted(want) and len(set(want)) == 4:
            order = [0] + [1 + at.index(v) for v in want]
            return order, f"GSO's lists were not in the usual order; filed by GSO's labels: {order}"
    return usual, f"GSO's labelled distribution solar {labelled} matches no moment in the lists"


def _solar_actual(spec: AdapterSpec, d: object, ctx: dict) -> ParsedPayload:
    if not isinstance(d, str):
        raise SchemaError("solar actual answer is not text")
    parts = d.split("$")
    if len(parts) < 7:
        raise SchemaError(f"solar actual answer has {len(parts)} parts, expected at least 7")
    lists = [_values(p) for p in parts[:5]]
    if len({len(x) for x in lists}) != 1:
        raise SchemaError(f"solar series have different lengths: {[len(x) for x in lists]}")
    order, note = _order_by_labels(parts, lists)
    lists = [lists[i] for i in order]
    # The day comes from the real clock: after sunset GSO's "last available" stops moving while the list keeps
    # growing, so judged by that time every evening list looked "too long for today" and was filed under yesterday.
    day = _pick_day(len(lists[0]), ctx.get("now") or _reading_time(ctx))
    out = ParsedPayload(signature=f"solar_actual:{len(parts)} parts" + (";labels: " + note[:40] if note else ""))
    if note:
        out.rejected.append(note)
    for (series, source), values in zip(SOLAR_PARTS, lists):
        _series(spec, out, values, day, series, source, quality="estimate" if series in ("nem", "fit", "selco") else None)
    return out


# --- Solar.aspx/GetSolarForecastData ----------------------------------------------------------------------------
# Solar.v19.js: FrcsTotalToday = r[10] (the forecast list appended after the actual answer) -> series 'Forecast'.
# The forecast answer itself: list$4520$"3,616 MW <br />@ 13:20"$-518$22-Oct-2026 (only the list is archived).

def _solar_forecast(spec: AdapterSpec, d: object, ctx: dict) -> ParsedPayload:
    if not isinstance(d, str):
        raise SchemaError("solar forecast answer is not text")
    parts = d.split("$")
    values = _values(parts[0])
    out = ParsedPayload(signature=f"solar_forecast:{len(parts)} parts,{len(values)} values")
    # GSO's forecast is for today. The day comes from the real clock (GSO's "last available" reads 07:00 at night).
    ref = (ctx.get("now") or ctx["last_available"]).astimezone(MYT)
    minutes = ref.hour * 60 + ref.minute
    if len(values) != 24 * 60 // SLOT_MINUTES:
        raise SchemaError(f"forecast has {len(values)} values, expected 144")
    if minutes < 30 or minutes > 23 * 60 + 30:
        # Around midnight it is unclear whether the forecast is for the old or the new day: skip, don't guess.
        out.rejected.append("skipped near midnight: forecast day ambiguous")
        return out
    day = ref.date()
    for i, v in enumerate(values):
        if v is None:
            out.missing += 1
            continue
        out.readings.append(Reading("total", "Forecast", _slot(day, i), v, kind="forecast"))
    return out


# --- LandingPage.aspx/GetGenMixData -----------------------------------------------------------------------------
# SolarLandingPage.v5.js, DrawGenMixChart(r): r[0] Coal r[1] Gas r[2] CoGen r[3] Oil r[4] TieLine r[5] Hydro
#   r[6] Solar r[7] NonSolar (plotted as 'Other RE') r[8] TotGen (plotted as 'Grid Demand') r[9] DistSolar
#   r[10] nullexist r[11] BessDischarge r[12] BessCharge (negative); r[14] = "Wednesday, 28 October 2026 1:20 PM"
GENMIX_PARTS = {4: "tie_line_total", 7: "other_re", 8: "total_generation", 9: "distribution_solar",
                11: "bess_discharge", 12: "bess_charge"}


def _genmix(spec: AdapterSpec, d: object, ctx: dict) -> ParsedPayload:
    if not isinstance(d, str):
        raise SchemaError("generation mix answer is not text")
    parts = d.split("$")
    if len(parts) < 15:
        raise SchemaError(f"generation mix answer has {len(parts)} parts, expected at least 15")
    try:
        latest = datetime.strptime(parts[14].strip(), "%A, %d %B %Y %I:%M %p").replace(tzinfo=MYT)
    except ValueError:
        raise SchemaError(f"unexpected time stamp {parts[14]!r}") from None
    lists = {i: _values(parts[i]) for i in GENMIX_PARTS}
    count = len(lists[8])
    day = _pick_day(count, latest)
    out = ParsedPayload(signature=f"genmix:{len(parts)} parts")
    for i, series in GENMIX_PARTS.items():
        _series(spec, out, lists[i], day, series, f"r[{i}]")
    # The newest "Other RE" reading and its time, for the split of other renewables collected next (_other_re).
    newest = next(((i, v) for i, v in reversed(list(enumerate(lists[7]))) if v is not None), None)
    if newest and "shared" in ctx:
        ctx["shared"]["genmix_other_re"] = (_slot(day, newest[0]), newest[1])
    return out


# --- LandingPage.aspx/GetOtherREData ----------------------------------------------------------------------------
# The home page's "Other RE" split, labelled by GSO and without a time (seen 30 Oct 2026):
#   [{"y":175,"drilldown":{"name":"Other RE","categories":["Biogas", "Biomass", "Mini Hydro"],"data":[101, 24, 50]}}]
# "y" is the same figure as the newest value of GetGenMixData's r[7] ("Other RE"), so the split is filed at that
# reading's time, and only when the two agree: otherwise they are from different moments and nothing is guessed.

def _other_re(spec: AdapterSpec, d: object, ctx: dict) -> ParsedPayload:
    try:
        pie = json.loads(d) if isinstance(d, str) else d
        item = pie[0] if isinstance(pie, list) else pie
        total, drill = float(item["y"]), item["drilldown"]
        split = dict(zip(drill["categories"], (float(v) for v in drill["data"])))
    except (ValueError, KeyError, TypeError, IndexError):
        raise SchemaError(f"unexpected other renewables answer: {str(d)[:200]!r}") from None
    out = ParsedPayload(signature="other_re:" + ",".join(split))
    if abs(sum(split.values()) - total) > 0.5:
        out.rejected.append(f"the split {split} doesn't add up to its total {total}")
        return out
    newest = ctx.get("shared", {}).get("genmix_other_re")
    if newest is None:
        out.rejected.append("no home page reading in this run to date it by; not kept")
        return out
    t, value = newest
    if abs(value - total) > 0.5:
        out.rejected.append(f"total {total} is not the home page's newest Other RE ({value}): different moments, not kept")
        return out
    for name, v in split.items():
        slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
        fspec = spec.fields.get(slug)
        out.readings.append(Reading(slug, name, t, v, quality=assess_quality(fspec, v, t) if fspec else "ok",
                                    name=None if fspec else f"Other renewables — {name}", unit="MW"))
    return out


# --- LandingPage.aspx/GetSysAVData ------------------------------------------------------------------------------
# SolarLandingPage.v5.js, DrawSysAvPieChart: "28 October 2026 1:20 PM$Coal$Gas$CoGen$Hydro$Solar$DNSolar$Bess"
AV_PARTS = ["coal", "gas", "cogen", "hydro", "transmission_solar", "distribution_solar", "bess"]


def _availability(spec: AdapterSpec, d: object, ctx: dict) -> ParsedPayload:
    if not isinstance(d, str):
        raise SchemaError("availability answer is not text")
    parts = d.split("$")
    if len(parts) < 8:
        raise SchemaError(f"availability answer has {len(parts)} parts, expected 8")
    try:
        t = datetime.strptime(parts[0].strip(), "%d %B %Y %I:%M %p").replace(tzinfo=MYT).astimezone(UTC)
    except ValueError:
        raise SchemaError(f"unexpected time stamp {parts[0]!r}") from None
    out = ParsedPayload(signature=f"availability:{len(parts)} parts")
    for series, text in zip(AV_PARTS, parts[1:8]):
        vals = _values(text)
        if vals[0] is None:
            out.missing += 1
            continue
        fspec = spec.fields[series]
        out.readings.append(Reading(series, series, t, vals[0], quality=assess_quality(fspec, vals[0], t)))
    return out


# --- LandingPage.aspx/GetSolarMap -------------------------------------------------------------------------------
# SolarLandingPage.v5.js / Solar.v19.js getData(point): point[0] state, [1] lat, [2] lon, [3] station code,
#   [4] MWPercentage, [5] region, [6] livegen (MW), [7] capacity (MW), [8] state average %, [9] kvlevel (GRID/DN).
# Rows with fewer fields are state summaries and are skipped.

def _solar_farms(spec: AdapterSpec, d: object, ctx: dict) -> ParsedPayload:
    if not isinstance(d, str):
        raise SchemaError("solar map answer is not text")
    rows = [r.strip() for r in d.split("$") if r.strip()]
    t = _reading_time(ctx).astimezone(UTC)
    day_start = datetime(t.astimezone(MYT).year, t.astimezone(MYT).month, t.astimezone(MYT).day, tzinfo=MYT).astimezone(UTC)
    out = ParsedPayload(signature="solar_map:10 fields")
    stations = 0
    for row in rows:
        f = [x.strip() for x in row.split(",")]
        if len(f) < 10 or not re.fullmatch(r"[A-Z0-9]{2,8}", f[3] or ""):
            continue
        code, state, region, conn = f[3], f[0], f[5], f[9]
        try:
            live, cap = float(f[6]), float(f[7])
        except ValueError:
            out.rejected.append(f"{code}: bad numbers {f[6]!r}/{f[7]!r}")
            continue
        try:  # [1], [2]: latitude and longitude (every farm lands in its own state; SOURCE_INVESTIGATION §3)
            lat, lon = float(f[1]), float(f[2])
            if not (0.5 < lat < 8 and 99 < lon < 106):  # Peninsular Malaysia
                lat = lon = None
        except ValueError:
            lat = lon = None
        stations += 1
        label = f"{code} ({state}, {region}, {'grid' if conn == 'GRID' else 'distribution' if conn == 'DN' else conn})"
        slug = code.lower()
        quality = "out_of_range" if live > cap * 1.2 or live < 0 else "ok"
        out.readings.append(Reading(slug, code, t, live, quality=quality, name=f"Solar farm {label} — live output", unit="MW",
                                    latitude=lat, longitude=lon))
        out.readings.append(Reading(f"{slug}_capacity", code, day_start, cap, kind="capacity",
                                    name=f"Solar farm {label} — capacity", unit="MW", latitude=lat, longitude=lon))
    if not stations:
        raise SchemaError("no solar farm rows found")
    return out


MAX = 30000.0

SOLAR_PROFILE = AdapterSpec(
    key="solar_profile",
    name="Solar profile (GSO Solar page)",
    category="solar",
    page="SystemData/Solar.aspx",
    method="GetSolarActualData",
    verification="verified",
    description=(
        "GSO's Solar page: grid (transmission) solar, distribution solar, and NEM, FiT and SELCO rooftop solar, every "
        "10 minutes, today only. GSO describes the NEM, FiT and SELCO values as estimates based on registered data; they "
        "are flagged 'estimate' here."
    ),
    fields={
        "grid": FieldSpec("grid", "Grid (transmission) solar", "MW", "actual", 0.0, MAX, daylight_only=True),
        "distribution": FieldSpec("distribution", "Distribution solar", "MW", "actual", 0.0, MAX, daylight_only=True),
        "nem": FieldSpec("nem", "NEM rooftop solar (GSO estimate)", "MW", "actual", 0.0, MAX),
        "fit": FieldSpec("fit", "FiT solar (GSO estimate)", "MW", "actual", 0.0, MAX),
        "selco": FieldSpec("selco", "SELCO solar (GSO estimate)", "MW", "actual", 0.0, MAX),
    },
    takes_date=False,
    time_source="solar_last_available",
    raw_transform=_solar_actual,
)

SOLAR_FORECAST = AdapterSpec(
    key="solar_forecast",
    name="Solar forecast (GSO Solar page)",
    category="solar",
    page="SystemData/Solar.aspx",
    method="GetSolarForecastData",
    verification="verified",
    description="GSO's total solar forecast for today, every 10 minutes. GSO gives no issue time, so the time it was "
                "collected is used and marked as such.",
    fields={"total": FieldSpec("total", "Solar forecast — total (GSO)", "MW", "forecast", 0.0, MAX)},
    takes_date=False,
    time_source="solar_last_available",
    raw_transform=_solar_forecast,
)

GENMIX_LIVE = AdapterSpec(
    key="genmix_live",
    name="Generation mix extras (GSO home page)",
    category="generation",
    page="LandingPage.aspx",
    method="GetGenMixData",
    verification="verified",
    description="From GSO's home page chart, every 10 minutes, today only: total tie-line flow, other renewables "
                "(biogas, biomass, mini hydro), total generation (GSO's 'Grid Demand' line), distribution solar, and "
                "battery (BESS) discharge and charge.",
    fields={
        "tie_line_total": FieldSpec("tie_line_total", "Tie-line total (as published)", "MW", "actual", -5000.0, 5000.0),
        "other_re": FieldSpec("other_re", "Other renewables (biogas, biomass, mini hydro)", "MW", "actual", 0.0, MAX),
        "total_generation": FieldSpec("total_generation", "Total generation (GSO 'Grid Demand')", "MW", "actual", 0.0, MAX),
        "distribution_solar": FieldSpec("distribution_solar", "Distribution solar (home page)", "MW", "actual", 0.0, MAX,
                                        daylight_only=True),
        "bess_discharge": FieldSpec("bess_discharge", "BESS discharge", "MW", "actual", 0.0, 5000.0),
        "bess_charge": FieldSpec("bess_charge", "BESS charge (negative = charging)", "MW", "actual", -5000.0, 0.0),
    },
    takes_date=False,
    raw_transform=_genmix,
)

# --- LandingPage.aspx/GetFeatureSectionData --------------------------------------------------------------------
# The home page's headline figures: 7 records {mw, Day: "Friday,<br>30 Oct 2026", Time: "13:00"}. Their names come
# from GSO's page (seen 30 Oct 2026): LoadFeatureSectionData puts JSONData[0..6] into TotalGenData, SystemDemandData,
# HighDemandRecData, HighEnergyRecData, RenewalData, BESSData, COWData, and checkLoading shows them under
# "Current Grid Demand", "Current System Demand", "Highest Grid Demand Recorded", "Highest Energy Recorded",
# "Current Solar Generation", "Current BESS Status" (above 0 "Discharging", below 0 "Charging") and
# "Cross-Border Power Exchange", each "MW" except Highest Energy Recorded, whose unit the page doesn't show in
# the code read so far, so it is not kept yet.
HEADLINES = {0: "current_grid_demand", 1: "current_system_demand", 2: "highest_grid_demand_recorded",
             4: "current_solar_generation", 5: "current_bess", 6: "cross_border_exchange"}


def _headlines(spec: AdapterSpec, d: object, ctx: dict) -> ParsedPayload:
    try:
        records = json.loads(d) if isinstance(d, str) else d
        assert isinstance(records, list)
    except (ValueError, AssertionError):
        raise SchemaError(f"unexpected headline answer: {str(d)[:200]!r}") from None
    if len(records) != 7:
        raise SchemaError(f"headline answer has {len(records)} figures, expected 7 (GSO's page shows 7)")
    out = ParsedPayload(signature="headlines:7")
    for i, series in HEADLINES.items():
        rec = records[i]
        if not isinstance(rec, dict) or rec.get("mw") is None:
            out.missing += 1
            continue
        day = re.sub(r"<br\s*/?>", " ", str(rec.get("Day", ""))).strip()
        try:
            t = datetime.strptime(f"{day} {rec.get('Time', '')}".strip(), "%A, %d %b %Y %H:%M").replace(tzinfo=MYT)
            value = float(rec["mw"])
        except (ValueError, TypeError):
            out.rejected.append(f"figure {i}: unreadable {rec!r}")
            continue
        fspec = spec.fields[series]
        out.readings.append(Reading(series, f"[{i}]", t.astimezone(UTC), value, quality=assess_quality(fspec, value, t)))
    return out


HEADLINE = AdapterSpec(
    key="headlines",
    name="Headline figures (GSO home page)",
    category="headline",  # not "demand": pages pick their main series by category (demand.js uses the first)
    page="LandingPage.aspx",
    method="GetFeatureSectionData",
    verification="verified",
    description="The figures at the top of GSO's home page, under GSO's own labels and times: Current Grid Demand, "
                "Current System Demand, Highest Grid Demand Recorded, Current Solar Generation, Current BESS Status "
                "and Cross-Border Power Exchange (MW). Only the current value is published, so they build up as "
                "the archive collects.",
    fields={
        "current_grid_demand": FieldSpec("current_grid_demand", "Current Grid Demand (GSO home page)", "MW", "actual", 0.0, MAX),
        "current_system_demand": FieldSpec("current_system_demand", "Current System Demand (GSO home page)", "MW", "actual", 0.0, MAX),
        "highest_grid_demand_recorded": FieldSpec("highest_grid_demand_recorded", "Highest Grid Demand Recorded (GSO home page)", "MW", "actual", 0.0, MAX),
        "current_solar_generation": FieldSpec("current_solar_generation", "Current Solar Generation (GSO home page)", "MW", "actual", 0.0, MAX),
        "current_bess": FieldSpec("current_bess", "Current BESS Status (GSO home page; above 0 discharging, below 0 charging)", "MW", "actual", -5000.0, 5000.0),
        "cross_border_exchange": FieldSpec("cross_border_exchange", "Cross-Border Power Exchange (GSO home page)", "MW", "actual", -5000.0, 5000.0),
    },
    takes_date=False,
    raw_transform=_headlines,
)

OTHER_RE = AdapterSpec(
    key="other_re",
    name="Other renewables split (GSO home page)",
    category="generation",
    page="LandingPage.aspx",
    method="GetOtherREData",
    verification="verified",
    description="From GSO's home page: the 'Other RE' total split into biogas, biomass and mini hydro, as labelled by "
                "GSO. GSO gives no time with it, so it is filed at the time of the home page's newest 'Other RE' "
                "reading, and only when the totals agree.",
    fields={
        "biogas": FieldSpec("biogas", "Other renewables — Biogas", "MW", "actual", 0.0, 2000.0),
        "biomass": FieldSpec("biomass", "Other renewables — Biomass", "MW", "actual", 0.0, 2000.0),
        "mini_hydro": FieldSpec("mini_hydro", "Other renewables — Mini Hydro", "MW", "actual", 0.0, 2000.0),
    },
    takes_date=False,
    raw_transform=_other_re,
)

AVAILABILITY = AdapterSpec(
    key="availability",
    name="System availability (GSO home page)",
    category="generation",
    page="LandingPage.aspx",
    method="GetSysAVData",
    verification="verified",
    description="GSO's 'System Availability' chart by fuel, with its own time stamp.",
    fields={k: FieldSpec(k, f"System availability — {label}", "MW", "actual", 0.0, MAX) for k, label in [
        ("coal", "Coal"), ("gas", "Gas"), ("cogen", "Co-gen"), ("hydro", "Hydro"), ("transmission_solar", "Transmission solar"),
        ("distribution_solar", "Distribution solar"), ("bess", "BESS")]},
    takes_date=False,
    raw_transform=_availability,
)

SOLAR_FARMS = AdapterSpec(
    key="solar_farms",
    name="Solar farms (GSO solar map)",
    category="solar",
    page="LandingPage.aspx",
    method="GetSolarMap",
    verification="verified",
    description="Live output and capacity of each large solar farm on GSO's solar map, with state, region and whether "
                "it connects to the grid or the distribution network.",
    takes_date=False,
    time_source="solar_last_available",
    raw_transform=_solar_farms,
)

TIME_SOURCES = {"solar_last_available": ("SystemData/Solar.aspx", "GetLastAvailableData", parse_last_available)}
