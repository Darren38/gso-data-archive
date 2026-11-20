"""Hourly proof that collection keeps everything GSO publishes (the owner's rule, 20 Nov 2026).

Run by the `check` job on GitHub (where gso.org.my is reachable) against the archive this very run has just saved:

* **GSO's lists against the archive.** Every collector's current answer is fetched once and read exactly as
  collection reads it (`trial.fetch_parse`, nothing written). A reading GSO shows that the archive lacks is "missing"
  when the archive already holds a later reading of that figure (a hole), or when it is over 45 minutes old. GSO's
  lists only cover today, and GSO starts a new list at midnight, so this is checked every hour while there is still
  time; the last check before midnight is made at about 23:40 MYT.
* **Solar farm map moments.** GSO's solar map shows only the present moment, so a moment not read is lost for good.
  Every time on today's Solar page list (daylight, output above zero) must have a map moment in the archive, unless
  the map collector asked GSO at that time and GSO's map showed another moment or nothing (GSO's own gap, lesson 58).

A reading can appear at GSO between this run's collection and the check (GSO refills its lists after an outage), so a
missing reading is reported as a problem only when the previous hourly check found it missing too, or when it is the
last check before midnight. Never raises: a source GSO does not answer is a note (the health check already handles
outages, lesson 42).
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

from sqlalchemy import and_, select
from sqlalchemy.engine import Engine

from . import db
from .adapters import ADAPTERS
from .config import Settings
from .timeutil import MYT, ensure_utc, myt_today, to_utc_iso

OLD_ENOUGH = timedelta(minutes=45)  # GSO's readings normally reach the archive 15-25 minutes after their time
MAP_GRACE = timedelta(minutes=25)  # a map moment is read within minutes of the Solar page reaching that time
SOLAR_LIST = "solar_profile"  # GSO's Solar page list: one time every 10 minutes from sunrise
FARMS = "solar_farms"
LOST_CRITICAL = 3  # map moments lost in a day before it is critical (half an hour: collection has really stalled)


def before_reset(now: datetime) -> bool:
    """The last check before GSO starts a new day's lists (23:35-23:59 MYT)."""
    t = now.astimezone(MYT)
    return t.hour == 23 and t.minute >= 35


def _archived(conn, key: str, lo: datetime, hi: datetime) -> tuple[dict[datetime, float], datetime | None]:
    s, o = db.series.c, db.observations.c
    sid = conn.execute(select(s.id).where(s.key == key)).scalar()
    if sid is None:
        return {}, None
    rows = conn.execute(select(o.obs_time, o.value).where(and_(o.series_id == sid, o.obs_time >= lo, o.obs_time <= hi))).all()
    newest = conn.execute(select(o.obs_time).where(o.series_id == sid).order_by(o.obs_time.desc()).limit(1)).scalar()
    return {ensure_utc(t): v for t, v in rows}, ensure_utc(newest) if newest else None


def missing_readings(engine: Engine, spec, payload, now: datetime) -> tuple[list[str], int]:
    """("series@time" GSO shows that the archive lacks, how many archived values differ from GSO's now)."""
    by_series: dict[str, dict[datetime, float]] = {}
    for r in payload.readings:
        if r.kind == "actual":
            by_series.setdefault(spec.series_key(r.series), {})[ensure_utc(r.obs_time)] = r.value
    missing, differ = [], 0
    with engine.connect() as conn:
        for key, gso in sorted(by_series.items()):
            have, newest = _archived(conn, key, min(gso), max(gso))
            for t, v in sorted(gso.items()):
                if t in have:
                    differ += abs(have[t] - v) > max(0.5, abs(v) * 0.005)
                elif (newest is not None and t < newest) or t <= now - OLD_ENOUGH:
                    missing.append(f"{key}@{to_utc_iso(t)}")
    return missing, differ


def lost_map_moments(engine: Engine, solar_times: list[datetime], now: datetime, day: date) -> tuple[list[str], list[str]]:
    """(map moments this site failed to read, moments GSO's map never showed) among today's Solar page times."""
    s, o, cr = db.series.c, db.observations.c, db.collection_runs.c
    due = [t for t in sorted(set(solar_times)) if t <= now - MAP_GRACE and t.astimezone(MYT).date() == day]
    if not due:
        return [], []
    with engine.connect() as conn:
        ids = [r.id for r in conn.execute(select(s.id).where(and_(s.key.like(f"{FARMS}.%"), s.kind == "actual")))]
        if not ids:
            return [], []
        have = {ensure_utc(t) for (t,) in conn.execute(
            select(o.obs_time).where(and_(o.series_id.in_(ids), o.obs_time >= due[0], o.obs_time <= due[-1])).distinct())}
        runs = [ensure_utc(t) for (t,) in conn.execute(
            # Any attempt counts as "GSO was asked then": an empty map (lesson 44) or no answer is GSO's gap, and
            # a collector that keeps failing is already reported by the health check.
            select(cr.started_at).where(and_(cr.adapter == FARMS, cr.status.in_(["success", "failed"]),
                                             cr.started_at >= due[0], cr.started_at <= due[-1] + MAP_GRACE)))]
    ours, gsos = [], []
    for t in due:
        if t in have:
            continue
        read_then = any(t <= r <= t + MAP_GRACE for r in runs)
        (gsos if read_then else ours).append(t.astimezone(MYT).strftime("%H:%M"))
    return ours, gsos


def verify(engine: Engine, settings: Settings, now: datetime, previous_missing: set[str] | None = None,
           client=None) -> dict:
    """{"problems", "notes", "missing"}: see the module text. `previous_missing` is the last check's "missing" list."""
    from .http import GsoClient
    from .trial import fetch_parse

    problems: list[str] = []
    notes: list[str] = []
    missing_now: list[str] = []
    day = myt_today(now)
    last_call = before_reset(now)
    shared: dict = {}
    solar_times: list[datetime] = []
    checked = unreadable = 0
    ours: list[str] = []
    gsos: list[str] = []
    own = client is None
    client = client or GsoClient(settings)
    try:
        for key in settings.adapters:
            spec = ADAPTERS.get(key)
            if spec is None:
                continue
            try:
                payload, result, details = fetch_parse(client, settings, spec, day, shared)
            except Exception as exc:  # noqa: BLE001 - a check must never stop on one source
                payload, result, details = None, "could not check", {"error": f"{type(exc).__name__}: {exc}"}
            checked += 1
            if payload is None:
                unreadable += 1
                notes.append(f"{key}: {result} ({(details or {}).get('error', '')[:120]})")
                continue
            if key == SOLAR_LIST:
                solar_times = [ensure_utc(r.obs_time) for r in payload.readings if r.kind == "actual" and r.value > 0]
            gone, differ = missing_readings(engine, spec, payload, now)
            missing_now += gone
            if differ:
                notes.append(f"{key}: {differ} readings changed at GSO since they were archived (GSO revises; "
                             "the next collection takes the new values)")
    finally:
        if own:
            client.close()
    confirmed = [m for m in missing_now if last_call or m in (previous_missing or set())]
    if confirmed:
        sample = ", ".join(_plain(m) for m in confirmed[:4])
        problems.append(f"{len(confirmed)} readings GSO publishes are not in the archive (e.g. {sample})"
                        + (": GSO starts new lists at midnight" if last_call else ""))
    if len(missing_now) > len(confirmed):
        notes.append(f"{len(missing_now) - len(confirmed)} readings GSO shows are not in the archive yet; "
                     "checked again next hour")
    if solar_times:
        ours, gsos = lost_map_moments(engine, solar_times, now, day)
        if len(ours) >= LOST_CRITICAL:
            problems.append(f"the solar farm map was not read at {len(ours)} moments today ({', '.join(ours[:6])} MYT): "
                            "GSO shows only the present moment, so these are lost")
        if 0 < len(ours) < LOST_CRITICAL:
            notes.append(f"⚠️ the solar farm map was not read at {', '.join(ours)} MYT today (lost)")
        if gsos:
            notes.append(f"GSO's solar map skipped {len(gsos)} moments today ({', '.join(gsos[:6])} MYT); "
                         "the map was asked then and showed another moment, or nothing")
    if not problems:
        notes.append("every reading GSO shows now is in the archive" + (" (last check before midnight)" if last_call else ""))
    # Shown on the site's Status page ("Proof against GSO"), through the check's saved notes (cli.py, export_static).
    proof = {"at": now.isoformat(), "sources": checked, "unreadable": unreadable, "missing": len(missing_now),
             "missing_confirmed": len(confirmed), "map_lost": ours, "map_skipped_by_gso": len(gsos),
             "before_midnight": last_call}
    return {"problems": problems, "notes": notes, "missing": missing_now, "proof": proof}


def _plain(m: str) -> str:
    key, iso = m.split("@")
    t = datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(MYT)
    return f"{key} {t:%d %b %H:%M}"


def backup_problem(newest_name: str, now: datetime) -> str | None:
    """The daily backup is made by the first run after 00:00 UTC; none for two days means it keeps failing."""
    import re

    m = re.search(r"(\d{4}-\d{2}-\d{2})", newest_name or "")
    if not m:
        return "there is no daily backup in the archive-backups release"
    age = (now.date() - date.fromisoformat(m.group(1))).days
    return f"the newest daily backup is {age} days old (archive-backups release)" if age >= 2 else None
