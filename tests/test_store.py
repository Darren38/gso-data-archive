from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select

from gso_archive import db, store
from gso_archive.adapters import Reading, get_adapter

UTC = timezone.utc
T0 = datetime(2026, 10, 27, 4, 0, tzinfo=UTC)


def _apply(engine, readings, collected_at=None):
    spec = get_adapter("generation_mix")
    with engine.begin() as conn:
        ds = store.ensure_dataset(conn, spec)
        ids = store.resolve_series(conn, spec, ds, readings)
        return store.apply_readings(conn, readings, ids, run_id=None, snapshot_id=None,
                                    collected_at=collected_at or datetime.now(UTC)), ids


def _count(engine, table, *where):
    with engine.connect() as conn:
        return conn.execute(select(func.count()).select_from(table).where(*where)).scalar()


def test_duplicates_are_not_stored_twice(engine):
    rs = [Reading("solar", "Solar", T0 + timedelta(minutes=30 * i), 100.0 + i) for i in range(5)]
    first, _ = _apply(engine, rs)
    second, _ = _apply(engine, rs)
    assert (first.new, first.unchanged) == (5, 0)
    assert (second.new, second.unchanged, second.revised) == (0, 5, 0)
    assert _count(engine, db.observations) == 5
    assert _count(engine, db.observation_revisions) == 5  # one initial revision each


def test_duplicate_within_payload_last_wins(engine):
    rs = [Reading("solar", "Solar", T0, 1.0), Reading("solar", "Solar", T0, 2.0)]
    stats, _ = _apply(engine, rs)
    assert stats.duplicates_in_payload == 1 and stats.new == 1
    with engine.connect() as conn:
        assert conn.execute(select(db.observations.c.value)).scalar() == 2.0


def test_revision_preserves_history(engine):
    _apply(engine, [Reading("solar", "Solar", T0, 500.0)], collected_at=T0 + timedelta(minutes=5))
    stats, ids = _apply(engine, [Reading("solar", "Solar", T0, 520.0)], collected_at=T0 + timedelta(hours=2))
    assert stats.revised == 1
    with engine.connect() as conn:
        obs = conn.execute(select(db.observations)).one()
        assert obs.value == 520.0 and obs.revision_count == 2
        history = conn.execute(
            select(db.observation_revisions.c.value, db.observation_revisions.c.previous_value)
            .order_by(db.observation_revisions.c.id)
        ).all()
    assert [tuple(h) for h in history] == [(500.0, None), (520.0, 500.0)]


def test_tiny_float_noise_is_not_a_revision(engine):
    _apply(engine, [Reading("solar", "Solar", T0, 0.1 + 0.2)])
    stats, _ = _apply(engine, [Reading("solar", "Solar", T0, 0.3)])
    assert stats.revised == 0


def test_expected_interval_inferred(engine):
    rs = [Reading("solar", "Solar", T0 + timedelta(minutes=30 * i), 1.0) for i in range(10)]
    _, ids = _apply(engine, rs)
    with engine.connect() as conn:
        assert conn.execute(select(db.series.c.expected_interval_s).where(db.series.c.id == ids["solar"])).scalar() == 1800


def test_forecasts_only_stored_when_changed(engine):
    spec = get_adapter("solar_profile")
    f = [Reading("solar_forecast", "Solar Forecast", T0, 900.0, kind="forecast")]
    with engine.begin() as conn:
        ds = store.ensure_dataset(conn, spec)
        ids = store.resolve_series(conn, spec, ds, f)
        a = store.apply_readings(conn, f, ids, run_id=None, snapshot_id=None, collected_at=T0 - timedelta(hours=3))
        b = store.apply_readings(conn, f, ids, run_id=None, snapshot_id=None, collected_at=T0 - timedelta(hours=2))
        f2 = [Reading("solar_forecast", "Solar Forecast", T0, 950.0, kind="forecast")]
        c = store.apply_readings(conn, f2, ids, run_id=None, snapshot_id=None, collected_at=T0 - timedelta(hours=1))
    assert (a.new, b.new, c.new) == (1, 0, 1)
    assert _count(engine, db.forecasts) == 2
    assert _count(engine, db.observations) == 0  # forecasts never mix with actuals


def test_readings_dated_in_the_future_are_refused(engine):
    collected = T0 + timedelta(minutes=5)
    rs = [Reading("solar", "Solar", T0, 1.0), Reading("solar", "Solar", T0 + timedelta(hours=7), 2.0)]
    stats, _ = _apply(engine, rs, collected_at=collected)
    assert (stats.new, stats.future) == (1, 1)
    assert _count(engine, db.observations) == 1


def test_migration_removes_readings_dated_after_collection(engine):
    from gso_archive.migrations import _m002_drop_future_readings

    _, ids = _apply(engine, [Reading("solar", "Solar", T0, 1.0)], collected_at=T0 + timedelta(minutes=5))
    sid = ids["solar"]
    with engine.begin() as conn:  # a reading stored before the check existed, dated 7 hours after it was collected
        late = T0 + timedelta(hours=7)
        conn.execute(db.observations.insert().values(series_id=sid, obs_time=late, value=9.0, quality="ok",
                                                     first_collected_at=T0, last_changed_at=T0, revision_count=1))
        conn.execute(db.observation_revisions.insert().values(series_id=sid, obs_time=late, value=9.0, quality="ok", collected_at=T0))
        _m002_drop_future_readings(conn)
    assert _count(engine, db.observations) == 1
    assert _count(engine, db.observation_revisions, db.observation_revisions.c.obs_time == T0 + timedelta(hours=7)) == 0


def test_series_location_is_kept(engine):
    r = Reading("ajns", "AJNS", T0, 24.0, name="Solar farm AJNS", unit="MW", latitude=5.738311, longitude=100.561308)
    _, ids = _apply(engine, [r])
    with engine.connect() as conn:
        row = conn.execute(select(db.series.c.latitude, db.series.c.longitude).where(db.series.c.id == ids["ajns"])).first()
    assert (row.latitude, row.longitude) == (5.738311, 100.561308)


def test_migration_puts_evening_solar_readings_back_on_their_own_day(engine):
    from gso_archive.migrations import _m004_refile_evening_solar
    from gso_archive.timeutil import MYT

    spec = get_adapter("solar_profile")

    def put(when, value, collected):
        r = [Reading("grid", "Grid", datetime(2026, 10, *when, tzinfo=MYT).astimezone(UTC), value)]
        with engine.begin() as conn:
            ds = store.ensure_dataset(conn, spec)
            ids = store.resolve_series(conn, spec, ds, r)
            store.apply_readings(conn, r, ids, run_id=None, snapshot_id=None,
                                 collected_at=datetime(2026, 10, *collected, tzinfo=MYT).astimezone(UTC))
            return ids["grid"]

    sid = put((27, 18, 0), 100.0, (27, 18, 5))   # collected on its own day
    put((28, 18, 0), 120.0, (28, 18, 5))
    put((27, 18, 0), 120.0, (28, 20, 40))        # the 28th's evening list, filed under the 27th
    put((27, 20, 30), 0.0, (28, 20, 40))
    put((28, 23, 50), 0.0, (29, 0, 5))           # just after midnight: yesterday's list, rightly yesterday's
    with engine.begin() as conn:
        _m004_refile_evening_solar(conn)
    with engine.connect() as conn:
        o = db.observations.c
        rows = {r.obs_time.replace(tzinfo=UTC) if r.obs_time.tzinfo is None else r.obs_time: (r.value, r.revision_count)
                for r in conn.execute(select(o.obs_time, o.value, o.revision_count).where(o.series_id == sid))}
    at = lambda *d: datetime(2026, 10, *d, tzinfo=MYT).astimezone(UTC)  # noqa: E731
    assert rows == {at(27, 18, 0): (100.0, 1), at(28, 18, 0): (120.0, 1), at(28, 20, 30): (0.0, 1),
                    at(28, 23, 50): (0.0, 1)}
    assert _count(engine, db.observation_revisions) == 4
