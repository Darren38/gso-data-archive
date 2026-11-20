"""The hourly comparison of GSO's current answers with the archive (verify.py), and the once-a-day email rule
(alerts.py). Real answers saved on 28 October 2026 (tests/fixtures/real), with the clock pinned to that moment."""

from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import and_, delete, select

from gso_archive import alerts, db
from gso_archive.adapters import get_adapter
from gso_archive.collector import collect_one
from gso_archive.timeutil import MYT
from gso_archive.verify import backup_problem, before_reset, lost_map_moments, verify

UTC = timezone.utc
NOW = datetime(2026, 10, 28, 13, 31, tzinfo=MYT).astimezone(UTC)
DAY = NOW.astimezone(MYT).date()


@pytest.fixture
def pinned(monkeypatch):
    monkeypatch.setattr("gso_archive.collector.utcnow", lambda: NOW)
    monkeypatch.setattr("gso_archive.trial.utcnow", lambda: NOW)


def _solar(fake):
    fake.add("SystemData/Solar.aspx/GetLastAvailableData", "real/solar_last_available.json")
    fake.add("SystemData/Solar.aspx/GetSolarActualData", "real/solar_actual.json")


def test_complete_archive_passes_and_a_hole_is_found(engine, settings, client, fake, pinned):
    _solar(fake)
    settings = replace(settings, adapters=["solar_profile"])
    collect_one(engine, client, settings, get_adapter("solar_profile"), DAY)
    v = verify(engine, settings, NOW, client=client)
    assert v["problems"] == [] and v["missing"] == [] and "every reading GSO shows" in v["notes"][-1]

    hole = datetime(2026, 10, 28, 10, 0, tzinfo=MYT).astimezone(UTC)
    with engine.begin() as c:
        sid = c.execute(select(db.series.c.id).where(db.series.c.key == "solar_profile.grid")).scalar()
        c.execute(delete(db.observations).where(and_(db.observations.c.series_id == sid, db.observations.c.obs_time == hole)))
    first = verify(engine, settings, NOW, client=client)
    assert first["missing"] == ["solar_profile.grid@2026-10-28T02:00:00Z"]
    assert first["problems"] == []  # seen once: GSO may have just added it; checked again next hour
    second = verify(engine, settings, NOW, set(first["missing"]), client=client)
    assert len(second["problems"]) == 1 and "solar_profile.grid 28 Oct 10:00" in second["problems"][0]


def test_last_check_before_midnight_reports_at_once():
    assert before_reset(datetime(2026, 10, 28, 23, 40, tzinfo=MYT)) and not before_reset(datetime(2026, 10, 28, 23, 0, tzinfo=MYT))


def test_solar_map_moments_not_read_are_reported(engine, settings, client, fake, pinned):
    _solar(fake)
    fake.add("LandingPage.aspx/GetSolarMap", "real/landing_solar_map.json")
    collect_one(engine, client, settings, get_adapter("solar_farms"), DAY)  # the map is read once, at 13:31
    times = [datetime(2026, 10, 28, h, m, tzinfo=MYT).astimezone(UTC) for h in (12, 13) for m in (0, 10, 20, 30, 40, 50)]
    ours, gsos = lost_map_moments(engine, times, NOW, DAY)
    assert ours == ["12:00", "12:10", "12:20", "12:30", "12:40", "12:50", "13:00"]  # not read then: lost
    with engine.begin() as c:  # a successful read at 12:45 that found another moment: GSO's map skipped 12:30/12:40
        c.execute(db.collection_runs.insert().values(adapter="solar_farms", trigger="schedule", status="success",
                                                     started_at=datetime(2026, 10, 28, 12, 45, tzinfo=MYT).astimezone(UTC),
                                                     records_seen=50))
    ours, gsos = lost_map_moments(engine, times, NOW, DAY)
    assert "12:30" in gsos and "12:40" in gsos and "12:30" not in ours and "12:00" in ours


def test_each_problem_emails_once_a_day():
    t = datetime(2026, 11, 20, 9, tzinfo=UTC)
    send, quiet, st = alerts.decide(["solar_profile has failed 13 times in a row"], {}, t)
    assert send and not quiet
    send, quiet, st = alerts.decide(["solar_profile has failed 19 times in a row"], st, t + timedelta(hours=1))
    assert not send and quiet  # the same problem with new figures: no second email
    send, quiet, st = alerts.decide(["solar_profile has failed 300 times in a row"], st, t + timedelta(hours=24))
    assert send  # a reminder a day later
    _, _, st = alerts.decide([], st, t + timedelta(hours=25))  # gone: forgotten
    send, _, _ = alerts.decide(["solar_profile has failed 13 times in a row"], st, t + timedelta(hours=26))
    assert send  # back again: emails again


def test_backup_age():
    now = datetime(2026, 11, 22, 3, tzinfo=UTC)
    assert backup_problem("gso-archive-2026-11-21.tar.gz", now) is None
    assert "2 days old" in backup_problem("gso-archive-2026-11-20.tar.gz", now)
    assert backup_problem("", now)
