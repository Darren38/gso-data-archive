"""Adapter specification and the shared GSO PageMethod response parser.

GSO pages are ASP.NET WebForms. Chart data is loaded by POSTing JSON to a
"PageMethod" such as `/SystemData/CurrentGen.aspx/GetChartDataSource`; the
response is `{"d": "<JSON string>"}` whose inner value is a list of records.
(Documented by the open-source Electricity Maps GSO parser — see
docs/SOURCE_INVESTIGATION.md. Not yet observed first-hand from this project.)
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime

from ..timeutil import MYT, parse_source_timestamp


class SourceError(Exception):
    """Base class for problems with a source response."""

    error_type = "source_error"


class ParseError(SourceError):
    error_type = "parse_error"


class SchemaError(SourceError):
    error_type = "schema_error"


@dataclass(frozen=True)
class FieldSpec:
    series: str  # suffix; full key is "<adapter>.<series>"
    name: str
    unit: str = "MW"
    kind: str = "actual"  # actual | forecast | capacity | record (a record value at its own date, never "stale")
    min_value: float | None = None  # below this → quality "suspect_negative"/"out_of_range"
    max_value: float | None = None
    daylight_only: bool = False  # solar: flag significant output at night


@dataclass
class Reading:
    series: str
    source_field: str
    obs_time: datetime  # UTC
    value: float
    kind: str = "actual"
    quality: str = "ok"
    # Optional series description for series created on the fly (e.g. one per solar farm).
    name: str | None = None
    unit: str | None = None
    # Where it is measured, if the source says (the solar farms on GSO's solar map).
    latitude: float | None = None
    longitude: float | None = None


@dataclass
class ParsedPayload:
    readings: list[Reading] = field(default_factory=list)
    missing: int = 0  # null/blank values in source (never stored as zero)
    rejected: list[str] = field(default_factory=list)
    signature: str = ""
    unknown_fields: list[str] = field(default_factory=list)
    # A list GSO publishes as rows with text (e.g. the power stations), kept with its changes (store.keep_table).
    table: list[dict] | None = None


@dataclass(frozen=True)
class AdapterSpec:
    key: str
    name: str
    category: str
    page: str  # path relative to base URL, e.g. "SystemData/CurrentGen.aspx"
    method: str  # PageMethod name
    verification: str  # verified | third_party_documented | unverified
    description: str
    fields: dict[str, FieldSpec] = field(default_factory=dict)
    time_fields: tuple[str, ...] = ("DT", "Tarikhmasa", "DateTime", "Date", "Time")
    ignore_fields: tuple[str, ...] = ()
    extra_params: dict[str, str] = field(default_factory=dict)
    takes_date: bool = True
    min_interval_seconds: int = 0  # 0 → every scheduler tick
    default_unit: str = "MW"
    default_min: float | None = None
    default_max: float | None = None
    # Custom record → readings transform (for non time-series pages).
    transform: Callable[["AdapterSpec", list[dict], date], ParsedPayload] | None = None
    # For answers whose "d" is not a JSON list (e.g. GSO's "$"-joined text): gets the raw "d" value and a context
    # dict (see `time_source`). Takes precedence over `transform`.
    raw_transform: Callable[["AdapterSpec", object, dict], ParsedPayload] | None = None
    # Name of a companion request made first to learn the exact time of the data (see collector.TIME_SOURCES).
    time_source: str | None = None

    def url(self, base_url: str) -> str:
        return f"{base_url}/{self.page}/{self.method}"

    def page_url(self, base_url: str) -> str:
        return f"{base_url}/{self.page}"

    def request_body(self, day: date) -> dict | None:
        if not self.takes_date and not self.extra_params:
            return {}
        body: dict[str, str] = {}
        if self.takes_date:
            from ..timeutil import gso_date_param

            body = {"Fromdate": gso_date_param(day), "Todate": gso_date_param(day)}
        body.update(self.extra_params)
        return body

    def series_key(self, suffix: str) -> str:
        return f"{self.key}.{suffix}"

    def field_spec(self, source_field: str) -> FieldSpec:
        spec = self.fields.get(source_field)
        if spec is not None:
            return spec
        kind = "forecast" if re.search(r"forecast|ramalan|predict", source_field, re.I) else "actual"
        return FieldSpec(
            series=slugify(source_field),
            name=f"{source_field} (auto-discovered)",
            unit=self.default_unit,
            kind=kind,
            min_value=self.default_min,
            max_value=self.default_max,
        )


def slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", text.strip().lower()).strip("_")
    return slug or "field"


def decode_pagemethod(body: bytes | str) -> list[dict]:
    """Decode an ASP.NET PageMethod response into a list of record dicts."""
    try:
        outer = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ParseError(f"response is not JSON: {exc}") from exc
    if not isinstance(outer, dict) or "d" not in outer:
        raise SchemaError("expected an object with key 'd'")
    inner = outer["d"]
    if isinstance(inner, str):
        if inner.strip() == "":
            return []
        try:
            inner = json.loads(inner)
        except json.JSONDecodeError as exc:
            raise ParseError(f"'d' is not a JSON document: {exc}") from exc
    if inner is None:
        return []
    if isinstance(inner, dict):
        # Some PageMethods wrap the rows, e.g. {"Table": [...]}
        lists = [v for v in inner.values() if isinstance(v, list)]
        if len(lists) != 1:
            raise SchemaError("'d' object does not contain exactly one list of records")
        inner = lists[0]
    if not isinstance(inner, list):
        raise SchemaError(f"'d' decoded to {type(inner).__name__}, expected list")
    if not all(isinstance(rec, dict) for rec in inner):
        raise SchemaError("records are not all objects")
    return inner


def schema_signature(records: list[dict]) -> str:
    keys: set[str] = set()
    for rec in records:
        keys.update(rec.keys())
    return ",".join(sorted(keys))


def to_number(value: object) -> float | None:
    """Convert a source value to float. Returns None for 'missing'.

    Raises ValueError for present-but-invalid values.
    """
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError("boolean is not a measurement")
    if isinstance(value, (int, float)):
        number = float(value)
    elif isinstance(value, str):
        text = value.strip().replace(",", "")
        if text in {"", "-", "--", "N/A", "n/a", "NA", "null", "NULL"}:
            return None
        number = float(text)
    else:
        raise ValueError(f"unsupported value type {type(value).__name__}")
    if math.isnan(number) or math.isinf(number):
        return None
    return number


def assess_quality(spec: FieldSpec, value: float, obs_time: datetime) -> str:
    if spec.min_value is not None and value < spec.min_value:
        return "suspect_negative" if spec.min_value == 0 else "out_of_range"
    if spec.max_value is not None and value > spec.max_value:
        return "out_of_range"
    if spec.daylight_only:
        local = obs_time.astimezone(MYT)
        minutes = local.hour * 60 + local.minute
        # Peninsular Malaysia: no meaningful PV output before ~06:45 or after ~19:45.
        if (minutes < 6 * 60 + 15 or minutes > 20 * 60 + 15) and value > 50:
            return "suspect_night"
    return "ok"


def parse_timeseries(spec: AdapterSpec, records: list[dict], day: date) -> ParsedPayload:
    """Default transform: each record = one timestamp with one or more numeric fields."""
    out = ParsedPayload(signature=schema_signature(records))
    if not records:
        return out
    time_field = next((f for f in spec.time_fields if f in records[0]), None)
    if time_field is None:
        raise SchemaError(
            f"no timestamp field found; expected one of {spec.time_fields}, got {sorted(records[0])}"
        )
    known = set(spec.fields) | {time_field} | set(spec.ignore_fields)
    unknown: set[str] = set()

    for index, rec in enumerate(records):
        try:
            obs_time = parse_source_timestamp(rec.get(time_field))
        except ValueError as exc:
            out.rejected.append(f"record {index}: {exc}")
            continue
        for source_field, raw in rec.items():
            if source_field == time_field or source_field in spec.ignore_fields:
                continue
            if source_field not in known:
                unknown.add(source_field)
            try:
                value = to_number(raw)
            except ValueError:
                # Non-numeric text in an unknown field is probably a label, not data.
                if source_field in spec.fields:
                    out.rejected.append(f"record {index} field {source_field}: invalid {raw!r}")
                continue
            if value is None:
                out.missing += 1
                continue
            fspec = spec.field_spec(source_field)
            out.readings.append(
                Reading(
                    series=fspec.series,
                    source_field=source_field,
                    obs_time=obs_time,
                    value=value,
                    kind=fspec.kind,
                    quality=assess_quality(fspec, value, obs_time),
                )
            )
    out.unknown_fields = sorted(unknown)
    return out


def decode_d(body: bytes | str) -> object:
    """The raw "d" value of a PageMethod answer, without interpreting it."""
    try:
        outer = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ParseError(f"response is not JSON: {exc}") from exc
    if not isinstance(outer, dict) or "d" not in outer:
        raise SchemaError("expected an object with key 'd'")
    return outer["d"]


def parse(spec: AdapterSpec, body: bytes | str, day: date, context: dict | None = None) -> ParsedPayload:
    if spec.raw_transform:
        return spec.raw_transform(spec, decode_d(body), context or {})
    records = decode_pagemethod(body)
    transform = spec.transform or parse_timeseries
    return transform(spec, records, day)
