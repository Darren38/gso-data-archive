"""Check-up of the published site, run after every deployment (like Tech Comparison Hub's health_check.py).

It only reads the site. It fails (so GitHub marks the run red and emails the owner) when:
  * the page or its data files don't load,
  * live collection is switched on but the collector hasn't run recently,
  * an enabled source has failed many times in a row (when GSO itself is not answering, only after half a day:
    GSO's pages time out for hours at a time and the owner can't fix that, while visitors already see the delay),
  * GSO's own pages no longer agree on the figures they both publish (crosscheck.py: a sign that GSO changed its
    lists and numbers are being filed under the wrong names), or
  * the newest reading is hours old although the collector runs (GSO answering with old data), or
  * one of GSO's sources has published nothing new for 6 hours of daytime (07:00-19:00 MYT), e.g. 1 Nov 2026 when
    GSO's solar data (Solar page, forecast, solar map, other renewables split) stopped from 08:30. Night doesn't count:
    some figures keep their sunset time all night. The owner asked for one email, then one a day while it lasts: the
    check fails only in the hour the silence passes 6 daytime hours, and again each further 12 (one day's daytime);
    the other hourly checks only note it.
"""

from __future__ import annotations

import json
import os
import re
import urllib.request
from datetime import datetime, timedelta, timezone

from .archive_sync import UA


def _get(url: str, timeout: float = 30) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Cache-Control": "no-cache"})
    with urllib.request.urlopen(req, timeout=timeout) as res:
        return res.read()


def _gso_not_answering(error: str | None) -> bool:
    """Timeouts, lost connections and GSO's own server errors: GSO's side, not a fault in this archive."""
    return bool(error) and (error.startswith("network_error") or bool(re.match(r"http_error: HTTP 5\d\d", error)))


MYT = timezone(timedelta(hours=8))
DAY_START, DAY_END = 7, 19  # daytime hours, MYT


def daytime_hours(start: datetime, end: datetime) -> float:
    """Hours between start and end that fall between 07:00 and 19:00 MYT."""
    total, day = 0.0, start.astimezone(MYT).replace(hour=0, minute=0, second=0, microsecond=0)
    while day < end:
        a, b = max(start, day + timedelta(hours=DAY_START)), min(end, day + timedelta(hours=DAY_END))
        total += max(0.0, (b - a).total_seconds() / 3600)
        day += timedelta(days=1)
    return total


def silent_sources(status: dict, now: datetime, max_daytime_hours: float = 6) -> list[tuple[str, str, float]]:
    """GSO sources (collectors switched on) whose newest reading is more than max_daytime_hours of daytime old."""
    enabled = {a["adapter"] for a in status.get("adapters", []) if a.get("enabled")}
    newest: dict[str, str] = {}
    for f in status.get("freshness", []):
        source = f["series"].split(".")[0]
        if f.get("kind") == "actual" and f.get("latest_obs_time") and source in enabled:
            newest[source] = max(newest.get(source, ""), f["latest_obs_time"])
    out = []
    for source, iso in sorted(newest.items()):
        hours = daytime_hours(datetime.fromisoformat(iso.replace("Z", "+00:00")), now)
        if hours > max_daytime_hours:
            out.append((source, iso, hours))
    return out


def silence_alerts(hours: float, max_daytime_hours: float = 6) -> int:
    """How many silence emails are due after `hours` of daytime: one at 6 hours, then one per 12 more (daily)."""
    return 0 if hours <= max_daytime_hours else int((hours - max_daytime_hours) // 12) + 1


def silence_email_due(newest: datetime, now: datetime) -> bool:
    """True when the silence passed 6 daytime hours (or a further day) during the previous whole clock hour. The check
    runs in the first minutes of each hour, so each such moment belongs to exactly one hourly check: one email."""
    hour = now.replace(minute=0, second=0, microsecond=0)
    return silence_alerts(daytime_hours(newest, hour)) > silence_alerts(daytime_hours(newest, hour - timedelta(hours=1)))


def check_site(base_url: str, max_age_minutes: int = 120, max_failures: int = 12,
               max_reading_age_minutes: int = 180, max_outage_hours: float = 12) -> dict:
    base = base_url.rstrip("/") + "/"
    problems: list[str] = []
    notes: list[str] = []
    try:
        if b"GSO Grid Archive" not in _get(base):
            problems.append("the home page loads but is not the dashboard")
    except Exception as exc:  # noqa: BLE001
        problems.append(f"the home page does not load ({exc})")
    meta = status = None
    for name in ("meta", "status"):
        try:
            data = json.loads(_get(f"{base}data/{name}.json"))
            meta, status = (data, status) if name == "meta" else (meta, data)
        except Exception as exc:  # noqa: BLE001
            problems.append(f"data/{name}.json does not load ({exc})")
    if status:
        now = datetime.now(timezone.utc)
        if status.get("live_enabled"):
            hb = status.get("collector_heartbeat") or {}
            started = hb.get("cycle_started_at")
            if not started:
                problems.append("live collection is on but the collector has never run")
            else:
                age = (now - datetime.fromisoformat(started)).total_seconds() / 60
                (problems if age > max_age_minutes else notes).append(f"last collection {age:.0f} min ago")
            for a in status.get("adapters", []):
                if not a.get("enabled") or (a.get("consecutive_failures") or 0) < max_failures:
                    continue
                said = f"{a['adapter']} has failed {a['consecutive_failures']} times in a row: {a.get('last_error')}"
                if _gso_not_answering(a.get("last_error")):
                    ok_at = a.get("last_success_at")
                    hours = (now - datetime.fromisoformat(ok_at.replace("Z", "+00:00"))).total_seconds() / 3600 if ok_at else None
                    if hours is not None and hours < max_outage_hours:
                        notes.append(f"{said} (GSO not answering for {hours:.1f} h; an alarm after {max_outage_hours:g} h)")
                        continue
                    said += f" (GSO not answering for {hours:.0f} h)" if hours is not None else " (never answered)"
                problems.append(said)
            for c in status.get("cross_checks", []):
                notes.append(f"cross-check {c['key']}: {c['state']} ({c['agreeing']} of {c['compared']} daylight readings agree)")
                if c.get("state") == "failed":
                    w = c.get("worst") or {}
                    problems.append(f"GSO's pages disagree: {c['name']} held for only {c['agreeing']} of {c['compared']} "
                                    f"daylight readings (e.g. {w.get('left')} vs {w.get('right')} at {w.get('time')})")
            newest = max((f["latest_obs_time"] for f in status.get("freshness", [])
                          if f.get("latest_obs_time") and f.get("kind") == "actual"), default=None)
            if newest:
                age = (now - datetime.fromisoformat(newest.replace("Z", "+00:00"))).total_seconds() / 60
                if age > max_reading_age_minutes:
                    problems.append(f"the newest GSO reading is {age:.0f} min old although the collector runs")
            for source, iso, hours in silent_sources(status, now):
                newest_at = datetime.fromisoformat(iso.replace("Z", "+00:00"))
                when = newest_at.astimezone(MYT).strftime("%d %b %H:%M")
                said = (f"GSO has published nothing new for {source} for {hours:.0f} daytime hours "
                        f"(newest reading {when} MYT): check GSO's own page")
                # Email (fail) once when it passes 6 daytime hours, then once a day; the other hours only note it.
                (problems if silence_email_due(newest_at, now) else notes).append(said)
            stale = [f["series"] for f in status.get("freshness", []) if f.get("stale")]
            if stale:
                notes.append(f"{len(stale)} series without a new reading lately: {', '.join(stale[:6])}")
        else:
            notes.append("live collection is off (GSO_LIVE_ENABLED); the site shows the archive as it is")
    if meta:
        notes.append(f"{len(meta.get('series', []))} series published" + (" (demonstration data)" if meta.get("is_demo") else ""))
    result = {"ok": not problems, "problems": problems, "notes": notes, "site": base}
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as fh:
            fh.write(f"## Site check-up: {'passed' if result['ok'] else 'FAILED'}\n\n")
            for p in problems:
                fh.write(f"- ❌ {p}\n")
            for n in notes:
                fh.write(f"- {n}\n")
    return result
