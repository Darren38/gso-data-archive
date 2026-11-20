"""Check-up of the published site, run after every deployment (like Tech Comparison Hub's health_check.py).

It only reads the site. Only CRITICAL problems fail it (GitHub then emails the owner; owner, 20 Nov 2026: "only send
me email when there is critical thing"), and alerts.py sends each at most once a day:
  * the page or its data files don't load, or live collection is on but the collector hasn't run recently,
  * a source keeps failing on this archive's side (GSO changed its answer and the collector can't read it),
  * GSO's own pages no longer agree on the figures they both publish (crosscheck.py: numbers filed under wrong names),
  * the published site is close to GitHub Pages' 1 GB limit (SITE_URGENT_BYTES),
  * and, from cli.py, an old backup or readings GSO shows that the archive lacks (verify.py).
Things on GSO's side (its site timing out, publishing nothing new for hours, e.g. 1 Nov 2026) are listed on the check's
page with a ⚠️ but never email: the owner can't fix them, collection catches up, and visitors see the delay banner.
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
# GitHub Pages publishes sites up to 1 GB. Past SITE_WARN_BYTES the check lists it; past SITE_URGENT_BYTES (about 50
# days before the limit at today's growth) it is critical and emails (docs/MAINTENANCE.md, "Storage").
SITE_WARN_BYTES, SITE_URGENT_BYTES = 700_000_000, 900_000_000


def site_size_alert(site_bytes: int | None, now: datetime) -> tuple[str, bool] | None:
    """(what to say, whether to email) about the published site's size, or None while it is small."""
    if not site_bytes or site_bytes < SITE_WARN_BYTES // 2:
        return None
    said = f"the published site is {site_bytes / 1e6:.0f} MB of GitHub Pages' 1,000 MB"
    if site_bytes >= SITE_URGENT_BYTES:
        return said + ": publish less now (docs/MAINTENANCE.md, Storage)", True
    if site_bytes >= SITE_WARN_BYTES:  # listed on the check only; the email comes at SITE_URGENT_BYTES
        return "⚠️ " + said + ": plan what to publish less of (docs/MAINTENANCE.md, Storage)", False
    return said, False


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


def check_site(base_url: str, max_age_minutes: int = 120, max_failures: int = 12,
               max_reading_age_minutes: int = 180, max_outage_hours: float = 12, write_summary: bool = True) -> dict:
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
                    # GSO's own site is down or slow: nothing the owner can fix, and collection catches up when GSO
                    # answers again, so never an email (owner, 20 Nov 2026: "only critical"); listed on the check.
                    ok_at = a.get("last_success_at")
                    hours = (now - datetime.fromisoformat(ok_at.replace("Z", "+00:00"))).total_seconds() / 3600 if ok_at else None
                    notes.append(f"⚠️ {said} (GSO not answering for {hours:.1f} h)" if hours is not None
                                 else f"⚠️ {said} (GSO never answered)")
                    continue
                problems.append(said)
            for c in status.get("cross_checks", []):
                notes.append(f"cross-check {c['key']}: {c['state']} ({c['agreeing']} of {c['compared']} readings agree)")
                if c.get("state") == "failed":
                    w = c.get("worst") or {}
                    problems.append(f"GSO's pages disagree: {c['name']} held for only {c['agreeing']} of {c['compared']} "
                                    f"readings (e.g. {w.get('left')} vs {w.get('right')} at {w.get('time')})")
            # GSO's own readings only: hourly satellite sunshine (not GSO) must never hide a GSO outage.
            gso = {a["adapter"] for a in status.get("adapters", []) if a.get("enabled")}
            newest = max((f["latest_obs_time"] for f in status.get("freshness", [])
                          if f.get("latest_obs_time") and f.get("kind") == "actual" and f["series"].split(".")[0] in gso),
                          default=None)
            if newest:
                age = (now - datetime.fromisoformat(newest.replace("Z", "+00:00"))).total_seconds() / 60
                if age > max_reading_age_minutes:  # GSO publishing nothing new: GSO's side, visitors see a banner
                    notes.append(f"⚠️ the newest GSO reading is {age:.0f} min old although the collector runs")
            for source, iso, hours in silent_sources(status, now):
                newest_at = datetime.fromisoformat(iso.replace("Z", "+00:00"))
                when = newest_at.astimezone(MYT).strftime("%d %b %H:%M")
                said = (f"GSO has published nothing new for {source} for {hours:.0f} daytime hours "
                        f"(newest reading {when} MYT): check GSO's own page")
                notes.append("⚠️ " + said)  # GSO's side: listed, never emailed (owner, 20 Nov 2026)
            stale = [f["series"] for f in status.get("freshness", []) if f.get("stale")]
            if stale:
                notes.append(f"{len(stale)} series without a new reading lately: {', '.join(stale[:6])}")
        else:
            notes.append("live collection is off (GSO_LIVE_ENABLED); the site shows the archive as it is")
    if meta:
        size = site_size_alert(meta.get("site_bytes"), datetime.now(timezone.utc))
        if size:
            (problems if size[1] else notes).append(size[0])
        elif meta.get("site_bytes"):
            notes.append(f"published site {meta['site_bytes'] / 1e6:.0f} MB (GitHub Pages allows 1,000 MB)")
        notes.append(f"{len(meta.get('series', []))} series published" + (" (demonstration data)" if meta.get("is_demo") else ""))
    result = {"ok": not problems, "problems": problems, "notes": notes, "site": base}
    if write_summary:
        write_step_summary(problems, [], notes)
    return result


def write_step_summary(emailed: list[str], quiet: list[str], notes: list[str]) -> None:
    """The check's page on GitHub: what failed (and was emailed), what is still wrong (emailed before), the notes."""
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if not summary:
        return
    with open(summary, "a", encoding="utf-8") as fh:
        state = "FAILED" if emailed else "problems already reported" if quiet else "passed"
        fh.write(f"## Site check-up: {state}\n\n")
        for p in emailed:
            fh.write(f"- ❌ {p}\n")
        for p in quiet:
            fh.write(f"- ⚠️ {p} (still; emailed earlier, a reminder after a day)\n")
        for n in notes:
            fh.write(f"- {n}\n")
