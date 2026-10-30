"""Check-up of the published site, run after every deployment (like Tech Comparison Hub's health_check.py).

It only reads the site. It fails (so GitHub marks the run red and emails the owner) when:
  * the page or its data files don't load,
  * live collection is switched on but the collector hasn't run recently,
  * an enabled source has failed many times in a row (when GSO itself is not answering, only after half a day:
    GSO's pages time out for hours at a time and the owner can't fix that, while visitors already see the delay),
  * GSO's own pages no longer agree on the figures they both publish (crosscheck.py: a sign that GSO changed its
    lists and numbers are being filed under the wrong names), or
  * the newest reading is hours old although the collector runs (GSO answering with old data).
"""

from __future__ import annotations

import json
import os
import re
import urllib.request
from datetime import datetime, timezone

from .archive_sync import UA


def _get(url: str, timeout: float = 30) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Cache-Control": "no-cache"})
    with urllib.request.urlopen(req, timeout=timeout) as res:
        return res.read()


def _gso_not_answering(error: str | None) -> bool:
    """Timeouts, lost connections and GSO's own server errors: GSO's side, not a fault in this archive."""
    return bool(error) and (error.startswith("network_error") or bool(re.match(r"http_error: HTTP 5\d\d", error)))


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
