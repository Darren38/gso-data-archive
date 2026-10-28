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
