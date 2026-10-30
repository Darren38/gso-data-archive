"""Cross-checks between GSO's own pages: the archive's alarm for numbers filed under the wrong name or time.

GSO's Solar page and home page answer with unlabelled lists joined by "$"; the archive knows which list is which
only by its position (gso_live.py). If GSO added or reordered a list, the numbers would quietly be filed under the
wrong names. Two figures are published twice, on different pages:

  * the home page's Distribution Solar = the Solar page's Distribution + NEM + FiT + SELCO, exactly, at every
    daylight reading (28-30 October 2026, 152 of 152, through all of GSO's revisions). This covers all five Solar
    page lists: moving any of them, or Grid with any of them, changes the sum;
  * the Solar page's Grid solar = the Generation page's Solar (which comes with GSO's own written times). At first
    publication they are equal (28 October: 78 of 78), but GSO later revises the Solar page's figures, sometimes
    several times in an afternoon, while the Generation page keeps its own (29 October: up to 77 MW, 8.5% apart).
    So this check allows 15% or 15 MW; filing NEM, Distribution or SELCO as Grid, or the list 10 minutes late, falls
    far outside that (at most 105 of 144 readings within it, against 95% needed).

Night is left out (both sides under 5 MW): any lists would agree there, and at night the Generation page shows 1-2 MW
of solar where the Solar page shows 0.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import and_, select
from sqlalchemy.engine import Connection

from . import db
from .timeutil import ensure_utc, to_utc_iso, utcnow

CHECKS = [
    {
        "key": "grid_solar",
        "name": "Solar page Grid solar ≈ Generation page Solar (within 15%: GSO revises the Solar page later)",
        "left": ["solar_profile.grid"],
        "right": ["generation_mix.solar"],
        "tolerance": (0.15, 15),  # share of the larger value, or MW, whichever is more: GSO revises the Solar page
    },
    {
        "key": "distribution_solar",
        "name": "Home page Distribution Solar = Solar page Distribution + NEM + FiT + SELCO",
        "left": ["genmix_live.distribution_solar"],
        "right": ["solar_profile.distribution", "solar_profile.nem", "solar_profile.fit", "solar_profile.selco"],
        "tolerance": (0, 0.5),
    },
]
WINDOW = timedelta(hours=48)
NIGHT_MW = 5  # both sides below this: night, no test of anything
MIN_COMPARED = 6  # daylight moments needed before a check can pass or fail
MIN_AGREEING = 0.95  # a few moments may differ while one page has updated and the other not yet


def _values(conn: Connection, key: str, since: datetime) -> dict[datetime, float]:
    s, o = db.series.c, db.observations.c
    rows = conn.execute(select(o.obs_time, o.value).join(db.series, s.id == o.series_id)
                        .where(and_(s.key == key, o.obs_time >= since, o.value.is_not(None))))
    return {ensure_utc(t): v for t, v in rows}


def cross_checks(conn: Connection, now: datetime | None = None) -> list[dict]:
    now = now or utcnow()
    since = now - WINDOW
    out = []
    for check in CHECKS:
        sides = [[_values(conn, k, since) for k in check[side]] for side in ("left", "right")]
        shared = set.intersection(*(set(m) for side in sides for m in side)) if all(sides) else set()
        compared = agreeing = 0
        worst = None
        for t in sorted(shared):
            left, right = (sum(m[t] for m in side) for side in sides)
            if left < NIGHT_MW and right < NIGHT_MW:
                continue
            compared += 1
            share, mw = check["tolerance"]
            if abs(left - right) <= max(share * max(abs(left), abs(right)), mw):
                agreeing += 1
            elif worst is None or abs(left - right) > abs(worst[1] - worst[2]):
                worst = (t, left, right)
        if compared < MIN_COMPARED:
            state = "waiting"
        else:
            state = "passed" if agreeing / compared >= MIN_AGREEING else "failed"
        out.append({
            "key": check["key"], "name": check["name"], "state": state,
            "compared": compared, "agreeing": agreeing,
            "worst": {"time": to_utc_iso(worst[0]), "left": worst[1], "right": worst[2]} if worst else None,
        })
    return out
