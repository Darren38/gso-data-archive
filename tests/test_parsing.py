from datetime import date, datetime, timezone

import pytest

from gso_archive.adapters import ParseError, SchemaError, get_adapter, parse
from gso_archive.adapters.base import FieldSpec, assess_quality, decode_pagemethod, to_number

from .conftest import fixture_bytes

DAY = date(2026, 10, 27)


def test_generation_mix_parses_documented_format():
    p = parse(get_adapter("generation_mix"), fixture_bytes("currentgen_2026-10-27.json"), DAY)
    assert len(p.readings) == 48 * 6
    assert p.missing == 0 and not p.rejected and not p.unknown_fields
    solar = [r for r in p.readings if r.series == "solar"]
    assert len(solar) == 48
    first = solar[0]
    assert first.obs_time == datetime(2026, 10, 26, 16, 0, tzinfo=timezone.utc)  # 00:00 MYT
    assert max(r.value for r in solar) > 1000
    assert p.signature == "CoGen,Coal,DT,Gas,Hydro,Oil,Solar"


def test_missing_values_are_counted_never_zero():
    p = parse(get_adapter("generation_mix"), fixture_bytes("currentgen_missing_values.json"), DAY)
    assert p.missing == 3
    solar_times = {r.obs_time for r in p.readings if r.series == "solar"}
    assert len(solar_times) == 4  # 6 records, 2 with missing solar
    assert all(r.value is not None for r in p.readings)


def test_bad_records_rejected_individually():
    p = parse(get_adapter("generation_mix"), fixture_bytes("currentgen_bad_records.json"), DAY)
    assert any("record 1" in r for r in p.rejected)  # bad timestamp
    assert any("Gas" in r for r in p.rejected)  # bad number in known field
    assert {r.obs_time for r in p.readings}  # other records still parsed


def test_unknown_field_is_auto_discovered():
    spec = get_adapter("generation_mix")
    p = parse(spec, fixture_bytes("currentgen_new_field.json"), DAY)
    assert p.unknown_fields == ["Battery"]
    assert any(r.series == "battery" and r.value == 12.5 for r in p.readings)
    assert spec.field_spec("Solar Forecast").kind == "forecast"


def test_tieline_uses_tarikhmasa_and_keeps_sign():
    p = parse(get_adapter("tieline_pltg"), fixture_bytes("tieline_pltg_2026-10-27.json"), DAY)
    assert p.readings[0].value == -35.5 and p.readings[0].series == "flow"
    assert p.readings[0].quality == "ok"  # negative flows are legitimate


def test_power_station_sums_capacity_by_fuel():
    p = parse(get_adapter("power_station"), fixture_bytes("powerstation.json"), DAY)
    values = {r.series: r.value for r in p.readings}
    assert values["capacity_gas"] == 1500.5  # "Gas " and "Gas" merged
    assert values["capacity_total"] == 3650.5
    assert all(r.kind == "capacity" for r in p.readings)


def test_empty_payload():
    assert parse(get_adapter("system_demand"), fixture_bytes("empty_d.json"), DAY).readings == []


@pytest.mark.parametrize("name, exc", [("not_json.html", ParseError), ("wrong_shape.json", SchemaError)])
def test_malformed_responses(name, exc):
    with pytest.raises(exc):
        parse(get_adapter("generation_mix"), fixture_bytes(name), DAY)


def test_schema_change_missing_timestamp_field():
    with pytest.raises(SchemaError):
        parse(get_adapter("generation_mix"), b'{"d": "[{\\"Time\\": \\"x\\", \\"Solar\\": 1}]"}', DAY)


def test_decode_variants():
    assert decode_pagemethod(b'{"d": [{"DT": "2026-10-27T00:00:00", "MW": 1}]}')[0]["MW"] == 1
    assert decode_pagemethod(b'{"d": {"Table": [{"a": 1}]}}') == [{"a": 1}]
    assert decode_pagemethod(b'{"d": null}') == []
    with pytest.raises(ParseError):
        decode_pagemethod(b'{"d": "{not json"}')


def test_to_number():
    assert to_number("1,234.5") == 1234.5
    assert to_number(None) is None and to_number("") is None and to_number("N/A") is None
    assert to_number(float("nan")) is None
    with pytest.raises(ValueError):
        to_number("abc")
    with pytest.raises(ValueError):
        to_number(True)


def test_quality_flags():
    solar = FieldSpec("solar", "Solar", min_value=0.0, max_value=30000.0, daylight_only=True)
    noon = datetime(2026, 10, 27, 4, 0, tzinfo=timezone.utc)
    midnight = datetime(2026, 10, 26, 16, 0, tzinfo=timezone.utc)
    assert assess_quality(solar, 1200, noon) == "ok"
    assert assess_quality(solar, -5, noon) == "suspect_negative"
    assert assess_quality(solar, 40000, noon) == "out_of_range"
    assert assess_quality(solar, 800, midnight) == "suspect_night"
    assert assess_quality(solar, 3, midnight) == "ok"
