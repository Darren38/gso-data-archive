"""Trial run: fetch and read GSO's live answers with every collector, report what would be kept, write nothing.

Run on GitHub (where gso.org.my is reachable) by the probe job after every push and once a day, so a new collector
meets GSO's real answers before it is switched on (lesson 40: a live answer had `null` where the saved ones had a
list, and the new collector stopped that round of collection). `python -m gso_archive trial --all` tries every
collector in the registry, including ones not yet listed in GSO_ADAPTERS.
"""

from __future__ import annotations

from collections import Counter
from datetime import date

from .adapters import ADAPTERS, AdapterSpec, parse
from .adapters.base import SourceError, decode_d
from .config import Settings
from .http import FetchError, GsoClient
from .timeutil import myt_today, to_utc_iso, utcnow


def _try(client: GsoClient, settings: Settings, spec: AdapterSpec, day: date, shared: dict) -> dict:
    out: dict = {"adapter": spec.key, "listed_in_GSO_ADAPTERS": spec.key in settings.adapters}
    ctx: dict = {"shared": shared}
    try:
        if spec.time_source:
            from .adapters.gso_live import TIME_SOURCES

            page, method, read_time = TIME_SOURCES[spec.time_source]
            if spec.time_source not in client.time_cache:
                res = client.post_pagemethod(f"{settings.gso_base_url}/{page}/{method}", {},
                                             referer=f"{settings.gso_base_url}/{page}", retries=0)
                client.time_cache[spec.time_source] = read_time(decode_d(res.content))
            ctx["last_available"] = client.time_cache[spec.time_source]
        fetched = client.post_pagemethod(spec.url(settings.gso_base_url), spec.request_body(day),
                                         referer=spec.page_url(settings.gso_base_url), retries=0)  # one try: fits the job's time
    except (FetchError, SourceError) as exc:
        return {**out, "result": "could not fetch", "error": f"{type(exc).__name__}: {exc}"}
    ctx["now"] = utcnow()
    try:
        payload = parse(spec, fetched.content, day, ctx)
    except SourceError as exc:
        return {**out, "result": "refused (GSO's answer is not what the collector expects)", "error": str(exc),
                "answer_start": fetched.content[:300].decode("utf-8", errors="replace")}
    except Exception as exc:  # noqa: BLE001 - exactly what this trial is for
        return {**out, "result": "COLLECTOR BUG (would have failed live)", "error": f"{type(exc).__name__}: {exc}",
                "answer_start": fetched.content[:300].decode("utf-8", errors="replace")}
    times = sorted(r.obs_time for r in payload.readings)
    return {
        **out, "result": "ok",
        "readings": len(payload.readings),
        "per_series": dict(Counter(r.series for r in payload.readings)),
        "first": to_utc_iso(times[0]) if times else None,
        "last": to_utc_iso(times[-1]) if times else None,
        "missing": payload.missing,
        "notes": payload.rejected[:10],
        "table_rows": None if payload.table is None else len(payload.table),
        "signature": payload.signature,
    }


def run_trial(settings: Settings, keys: list[str] | None = None, day: date | None = None,
              client: GsoClient | None = None) -> list[dict]:
    """Try the named collectors (all of them when keys is None), in the order collection runs them."""
    day = day or myt_today()
    order = list(settings.adapters) + [k for k in ADAPTERS if k not in settings.adapters]
    wanted = [k for k in order if k in ADAPTERS and (keys is None or k in keys)]
    shared: dict = {}  # as in a collection cycle: other_re is dated by genmix_live's reading
    if client is not None:
        return [_try(client, settings, ADAPTERS[k], day, shared) for k in wanted]
    with GsoClient(settings) as own:
        return [_try(own, settings, ADAPTERS[k], day, shared) for k in wanted]
