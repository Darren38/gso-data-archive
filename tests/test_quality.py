"""Readings GSO published from a stalled feed (gso_archive/quality.py), from the night of 3-4 November 2026."""

from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from gso_archive import analytics, db
from gso_archive.quality import mark_frozen
from gso_archive.timeutil import MYT

T0 = datetime(2026, 11, 3, 20, 0, tzinfo=MYT)


def _add(conn, key, moments):
    ds = conn.execute(db.datasets.select().where(db.datasets.c.key == "t")).first()
    ds_id = ds.id if ds else conn.execute(db.datasets.insert().values(key="t", name="t", category="demand", source_url="x",
                                                                      verification="verified", created_at=T0)).inserted_primary_key[0]
    sid = conn.execute(db.series.insert().values(dataset_id=ds_id, key=key, name=key, unit="MW", kind="actual", source_field=key,
                                                 created_at=T0)).inserted_primary_key[0]
    for t, v in moments:
        conn.execute(db.observations.insert().values(series_id=sid, obs_time=t.astimezone(timezone.utc), value=v, first_collected_at=t,
                                                     last_changed_at=t))


def _quality(conn, key):
    s, o = db.series.c, db.observations.c
    return {r.obs_time.replace(tzinfo=timezone.utc).astimezone(MYT).strftime("%d %H:%M"): r.quality
            for r in conn.execute(select(o.obs_time, o.quality).join(db.series, s.id == o.series_id).where(s.key == key))}


def test_a_lone_unconfirmed_home_page_moment_is_frozen(engine):
    step = timedelta(minutes=10)
    evening = [(T0 + i * step, 21000 - i) for i in range(8)]  # 20:00-21:10, then GSO stalls
    midnight = [(datetime(2026, 11, 4, 0, 0, tzinfo=MYT), 20858)]  # one value at 00:00 repeating the stalled figure
    night = [(datetime(2026, 11, 4, 1, 10, tzinfo=MYT) + i * step, 17742 - 60 * i) for i in range(4)]  # GSO back
    with engine.begin() as c:
        _add(c, "genmix_live.total_generation", evening + midnight + night)
        _add(c, "genmix_live.tie_line_total", [(t, -7) for t, _ in evening + midnight + night])
        _add(c, "system_demand.demand", evening + [(t, v + 1) for t, v in night])  # never had 00:00
        assert mark_frozen(c, since=None) == 2  # both home page figures at 00:00
        q = _quality(c, "genmix_live.total_generation")
        assert q["04 00:00"] == "frozen" and q["04 01:10"] == "ok" and q["03 21:10"] == "ok"
        assert _quality(c, "genmix_live.tie_line_total")["04 00:00"] == "frozen"
        assert mark_frozen(c, since=None) == 0  # the same answer again
        # Statistics and "latest" leave it out.
        info = analytics.get_series(c, "genmix_live.total_generation")
        days = {d["date"]: d for d in analytics.daily(c, info, datetime(2026, 11, 4).date(), datetime(2026, 11, 4).date())}
        assert days["2026-11-04"]["max"] == 17742
        # If GSO's System Demand page later confirms the moment, the mark is lifted.
        s = db.series.c
        sid = c.execute(select(s.id).where(s.key == "system_demand.demand")).scalar()
        c.execute(db.observations.insert().values(series_id=sid, obs_time=midnight[0][0].astimezone(timezone.utc), value=20859,
                                                  first_collected_at=T0, last_changed_at=T0))
        mark_frozen(c, since=None)
        assert _quality(c, "genmix_live.total_generation")["04 00:00"] == "ok"


def test_the_nightly_gap_is_not_frozen(engine):
    # Every night GSO's home page misses 23:40 and 23:50: 00:00 is 30 minutes after 23:30, not alone.
    times = [datetime(2026, 11, 3, 23, m, tzinfo=MYT) for m in (0, 10, 20, 30)] + [datetime(2026, 11, 4, 0, m, tzinfo=MYT) for m in (0, 10)]
    with engine.begin() as c:
        _add(c, "genmix_live.total_generation", [(t, 19000) for t in times])
        _add(c, "system_demand.demand", [(t, 19010) for t in times[:4]])  # the System Demand page not yet up to date
        assert mark_frozen(c, since=None) == 0
