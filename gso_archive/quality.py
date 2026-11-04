"""Readings GSO published from a stalled feed ("frozen"): kept in the archive, left out of charts and statistics.

Seen 3-4 Nov 2026: GSO's home page and System Demand page stopped updating at 21:10 MYT. At midnight the home page
started a new day with one value per list, dated 00:00, that only repeated its stalled figures (Grid Demand 20,858 MW;
tie-line -7 and Other RE 153 as at 21:10), and stopped again until 01:10. GSO's System Demand page never had a 00:00
reading. Such a moment is marked "frozen" when it stands alone (no other home page reading within an hour either side)
and the System Demand page has no reading for it. Normal readings come every 10 minutes and the nightly 23:40/23:50
gap is 30 minutes, so they never stand alone. The pass is repeated every cycle over recent days, so a mark is lifted if
a later reading or the System Demand page confirms the moment.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import and_, select, update
from sqlalchemy.engine import Connection

from . import db
from .timeutil import ensure_utc, utcnow

FROZEN = "frozen"
HOME_PREFIX = "genmix_live."
ANCHOR = "genmix_live.total_generation"  # the home page's Grid Demand line: one reading per home page moment
CONFIRM = "system_demand.demand"
ALONE = timedelta(minutes=60)
RECHECK = timedelta(days=3)


def _times(conn: Connection, key: str, since: datetime | None) -> list[datetime]:
    s, o = db.series.c, db.observations.c
    q = select(o.obs_time).join(db.series, s.id == o.series_id).where(s.key == key)
    if since is not None:
        q = q.where(o.obs_time >= since - ALONE)
    return sorted(ensure_utc(t) for (t,) in conn.execute(q))


def frozen_moments(conn: Connection, since: datetime | None = None) -> set[datetime]:
    home = _times(conn, ANCHOR, since)
    confirmed = set(_times(conn, CONFIRM, since))
    out = set()
    for i, t in enumerate(home):
        if since is not None and t < since:
            continue
        before = home[i - 1] if i else None
        after = home[i + 1] if i + 1 < len(home) else None
        alone = (before is None or t - before > ALONE) and (after is None or after - t > ALONE)
        if alone and before is not None and t not in confirmed:
            out.add(t)
    return out


def mark_frozen(conn: Connection, now: datetime | None = None, since: datetime | None = ...) -> int:
    """Mark (and unmark) frozen home page moments since `since` (default: the last 3 days; None: all). Returns how many
    readings changed."""
    if since is ...:
        since = (now or utcnow()) - RECHECK
    frozen = frozen_moments(conn, since)
    s, o = db.series.c, db.observations.c
    ids = [i for (i,) in conn.execute(select(s.id).where(s.key.like(HOME_PREFIX + "%")))]
    if not ids:
        return 0
    q = select(o.series_id, o.obs_time, o.quality).where(o.series_id.in_(ids))
    if since is not None:
        q = q.where(o.obs_time >= since)
    changed = 0
    for sid, t, quality in conn.execute(q).all():
        want = FROZEN if ensure_utc(t) in frozen else ("ok" if quality == FROZEN else quality)
        if want != quality:
            conn.execute(update(db.observations).where(and_(o.series_id == sid, o.obs_time == t)).values(quality=want))
            changed += 1
    return changed
