"""Cross-checks between GSO's pages (gso_archive/crosscheck.py): they pass when the pages agree, as they did in the
real archive, and fail when one list is filed under the wrong name or time."""

from datetime import datetime, timedelta, timezone

from gso_archive import db
from gso_archive.crosscheck import cross_checks

NOW = datetime(2026, 10, 28, 8, 0, tzinfo=timezone.utc)  # 16:00 MYT
SOLAR = [0, 0, 0, 0] + [100 + 37 * i for i in range(30)]  # night, then a sunny day every 10 minutes


def _add(conn, values: dict[str, list[float]], start=NOW - timedelta(hours=6)):
    ds = conn.execute(db.datasets.insert().values(key="t", name="t", category="solar", source_url="x",
                                                  verification="verified", created_at=NOW)).inserted_primary_key[0]
    for key, vals in values.items():
        sid = conn.execute(db.series.insert().values(dataset_id=ds, key=key, name=key, unit="MW", kind="actual",
                                                     source_field=key, created_at=NOW)).inserted_primary_key[0]
        for i, v in enumerate(vals):
            t = start + timedelta(minutes=10 * i)
            conn.execute(db.observations.insert().values(series_id=sid, obs_time=t, value=v, first_collected_at=t,
                                                         last_changed_at=t))


def _parts(total):
    # Distribution, NEM, FiT and SELCO in GSO's rough proportions, adding up to `total`.
    d, n, f = round(total * 0.15), round(total * 0.65), round(total * 0.06)
    return d, n, f, total - d - n - f


def _by_key(engine):
    with engine.connect() as c:
        return {x["key"]: x for x in cross_checks(c, NOW)}


def _solar_page(dist):
    return {f"solar_profile.{k}": [p[i] for p in map(_parts, dist)] for i, k in enumerate(("distribution", "nem", "fit", "selco"))}


def test_pages_that_agree_pass_and_night_is_left_out(engine):
    dist = [v * 0.6 for v in SOLAR]
    with engine.begin() as c:
        _add(c, {"solar_profile.grid": SOLAR, "generation_mix.solar": [v + (1 if v == 0 else 0) for v in SOLAR],
                 "genmix_live.distribution_solar": dist, **_solar_page(dist)})
    checks = _by_key(engine)
    assert checks["grid_solar"]["state"] == "passed"
    assert checks["grid_solar"]["compared"] == 30  # the four night readings (0 vs 1 MW) are left out
    assert checks["distribution_solar"]["state"] == "passed"


def test_a_list_on_the_wrong_time_fails(engine):
    with engine.begin() as c:  # the Solar page's list shifted by 10 minutes against the Generation page
        _add(c, {"solar_profile.grid": SOLAR[1:], "generation_mix.solar": SOLAR})
    check = _by_key(engine)["grid_solar"]
    assert check["state"] == "failed" and check["agreeing"] == 0 and check["worst"]


def test_a_list_under_the_wrong_name_fails(engine):
    dist = [v * 0.6 for v in SOLAR]
    page = _solar_page(dist)
    page["solar_profile.nem"], page["solar_profile.selco"] = page["solar_profile.selco"], [v * 2 for v in page["solar_profile.nem"]]
    with engine.begin() as c:
        _add(c, {"genmix_live.distribution_solar": dist, **page})
    assert _by_key(engine)["distribution_solar"]["state"] == "failed"


def test_too_little_daylight_waits(engine):
    with engine.begin() as c:
        _add(c, {"solar_profile.grid": [0, 0, 50, 60], "generation_mix.solar": [1, 1, 50, 60]})
    checks = _by_key(engine)
    assert checks["grid_solar"]["state"] == "waiting" and checks["grid_solar"]["compared"] == 2
    assert checks["distribution_solar"]["state"] == "waiting" and checks["distribution_solar"]["compared"] == 0
