"""Collection pipeline.

One *run* = one request to one adapter for one MYT calendar day:

    start run (committed) → fetch → archive raw response (committed)
    → parse/validate → single transaction: series + observations + run result

A failure at any step marks only that run as failed; previously archived
observations are never touched, because nothing is ever deleted and the
observation write is a single transaction that either fully commits or
fully rolls back.
"""

from __future__ import annotations

import json
import logging
import random
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from sqlalchemy import and_, desc, select
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

from . import db, store
from .adapters import ADAPTERS, AdapterSpec, SourceError, get_adapter, parse
from .config import Settings
from .http import FetchError, GsoClient
from .locks import LockBusy, collector_lock
from .rawstore import RawStore, sha256
from .timeutil import myt_today, utcnow

log = logging.getLogger(__name__)


@dataclass
class RunResult:
    adapter: str
    target_date: date | None
    trigger: str
    status: str
    run_id: int | None = None
    records_new: int = 0
    records_revised: int = 0
    records_unchanged: int = 0
    records_missing: int = 0
    error_type: str | None = None
    error: str | None = None
    schema_changed: bool = False


@dataclass
class CycleResult:
    started_at: datetime
    results: list[RunResult] = field(default_factory=list)
    skipped_reason: str | None = None

    @property
    def ok(self) -> bool:
        return self.skipped_reason is None and all(r.status == "success" for r in self.results)


def _archive_raw(engine: Engine, settings: Settings, spec: AdapterSpec, url: str, body_json: str | None,
                 fetched_at: datetime, status: int, content_type: str | None, content: bytes) -> int | None:
    if settings.raw_retention == "none":
        return None
    digest = sha256(content)
    rs = db.raw_snapshots.c
    with engine.begin() as conn:
        previous = conn.execute(
            select(rs.sha256, rs.storage_path)
            .where(and_(rs.adapter == spec.key, rs.request_body == body_json))
            .order_by(desc(rs.fetched_at))
            .limit(1)
        ).first()
        if settings.raw_retention == "changed" and previous and previous.sha256 == digest and previous.storage_path:
            path = previous.storage_path  # identical bytes already archived
        else:
            path = RawStore(settings.raw_store_dir).write(spec.key, fetched_at, content, digest)
        return conn.execute(
            db.raw_snapshots.insert().values(
                adapter=spec.key, url=url, request_body=body_json, fetched_at=fetched_at, http_status=status,
                content_type=content_type, sha256=digest, size_bytes=len(content), storage_path=path,
            )
        ).inserted_primary_key[0]


def collect_one(engine: Engine, client: GsoClient, settings: Settings, spec: AdapterSpec,
                day: date, trigger: str = "manual") -> RunResult:
    started = time.monotonic()
    target = day if spec.takes_date else None
    result = RunResult(spec.key, target, trigger, "running")
    try:
        with engine.begin() as conn:
            result.run_id = store.start_run(conn, spec.key, target, trigger)
    except SQLAlchemyError as exc:
        result.status, result.error_type, result.error = "failed", "database_error", str(exc)
        log.error("cannot record run start for %s: %s", spec.key, exc)
        return result

    def fail(error_type: str, message: str, http_status: int | None = None, snapshot_id: int | None = None):
        result.status, result.error_type, result.error = "failed", error_type, message
        log.warning("%s %s failed: %s: %s", spec.key, day, error_type, message)
        try:
            with engine.begin() as conn:
                store.finish_run(conn, result.run_id, status="failed", error_type=error_type,
                                 error_message=message[:4000], http_status=http_status,
                                 raw_snapshot_id=snapshot_id,
                                 duration_ms=int((time.monotonic() - started) * 1000))
        except SQLAlchemyError as exc:  # DB down: nothing else we can do but log
            log.error("cannot record failure for run %s: %s", result.run_id, exc)
        return result

    url = spec.url(settings.gso_base_url)
    body = spec.request_body(day)
    body_json = json.dumps(body, sort_keys=True) if body else None

    context: dict = {}
    try:
        if settings.warm_up:
            client.warm_up(spec.page_url(settings.gso_base_url))
        if spec.time_source and spec.time_source in client.time_cache:
            context["last_available"] = client.time_cache[spec.time_source]  # asked once per run, shared
        elif spec.time_source:
            # A small companion request first: the exact time of GSO's newest reading, used to date the data.
            from .adapters.gso_live import TIME_SOURCES

            t_page, t_method, t_parse = TIME_SOURCES[spec.time_source]
            t_url = f"{settings.gso_base_url}/{t_page}/{t_method}"
            t_res = client.post_pagemethod(t_url, {}, referer=f"{settings.gso_base_url}/{t_page}")
            try:
                from .adapters.base import decode_d

                context["last_available"] = client.time_cache[spec.time_source] = t_parse(decode_d(t_res.content))
            except SourceError as exc:
                return fail(exc.error_type, f"time of latest reading: {exc}", t_res.status)
        fetched = client.post_pagemethod(url, body, referer=spec.page_url(settings.gso_base_url))
    except FetchError as exc:
        if exc.error_type == "live_disabled":
            result.status = "disabled"
            result.error_type, result.error = exc.error_type, str(exc)
            with engine.begin() as conn:
                store.finish_run(conn, result.run_id, status="disabled", error_type=exc.error_type,
                                 error_message=str(exc), duration_ms=0)
            return result
        return fail(exc.error_type, str(exc), exc.http_status)

    fetched_at = utcnow()
    try:
        snapshot_id = _archive_raw(engine, settings, spec, url, body_json, fetched_at, fetched.status,
                                   fetched.content_type, fetched.content)
    except (OSError, SQLAlchemyError) as exc:
        log.error("raw archive failed for %s: %s (continuing)", spec.key, exc)
        snapshot_id = None

    try:
        payload = parse(spec, fetched.content, day, context)
    except SourceError as exc:
        return fail(exc.error_type, str(exc), fetched.status, snapshot_id)

    try:
        with engine.begin() as conn:
            dataset_id = store.ensure_dataset(conn, spec)
            series_ids = store.resolve_series(conn, spec, dataset_id, payload.readings)
            stats = store.apply_readings(conn, payload.readings, series_ids, run_id=result.run_id,
                                         snapshot_id=snapshot_id, collected_at=fetched_at)
            previous_sig = store.last_signature(conn, spec.key)
            schema_changed = bool(previous_sig and payload.signature and previous_sig != payload.signature)
            store.finish_run(
                conn, result.run_id, status="success", http_status=fetched.status,
                records_seen=len(payload.readings), records_new=stats.new, records_revised=stats.revised,
                records_unchanged=stats.unchanged, records_missing=payload.missing,
                records_suspect=stats.suspect, records_rejected=len(payload.rejected),
                schema_signature=payload.signature[:500], schema_changed=schema_changed,
                latest_obs_time=stats.latest_obs_time, raw_snapshot_id=snapshot_id,
                error_message=("; ".join(payload.rejected[:20]) or None),
                duration_ms=int((time.monotonic() - started) * 1000),
            )
    except SQLAlchemyError as exc:
        return fail("database_error", str(exc), fetched.status, snapshot_id)

    if schema_changed:
        log.warning("%s: source schema changed: %s → %s", spec.key, previous_sig, payload.signature)
    if payload.unknown_fields:
        log.info("%s: auto-discovered fields %s", spec.key, payload.unknown_fields)
    result.status = "success"
    result.records_new, result.records_revised = stats.new, stats.revised
    result.records_unchanged, result.records_missing = stats.unchanged, payload.missing
    result.schema_changed = schema_changed
    return result


def plan_cycle(engine: Engine, settings: Settings, now: datetime | None = None) -> list[tuple[AdapterSpec, date, str]]:
    """Decide which (adapter, day) requests this cycle should make."""
    now = now or utcnow()
    today = myt_today(now)
    plan: list[tuple[AdapterSpec, date, str]] = []
    with engine.connect() as conn:
        for key in settings.adapters:
            spec = get_adapter(key)
            if spec.min_interval_seconds:
                last = store.last_success(conn, spec.key)
                if last and (now - last).total_seconds() < spec.min_interval_seconds:
                    continue
            plan.append((spec, today, "schedule"))
            if not spec.takes_date:
                continue
            # Late-arriving / revised readings for the previous day.
            yesterday = today - timedelta(days=1)
            last_y = store.last_success(conn, spec.key, yesterday)
            if last_y is None or (now - last_y) >= timedelta(minutes=settings.revision_recheck_minutes):
                plan.append((spec, yesterday, "recheck"))
            # Automatic recovery of missed days (collector downtime, failures).
            budget = settings.auto_backfill_per_cycle
            for offset in range(2, settings.auto_backfill_days + 1):
                if budget <= 0:
                    break
                day = today - timedelta(days=offset)
                if store.last_success(conn, spec.key, day) is None:
                    plan.append((spec, day, "auto_backfill"))
                    budget -= 1
    return plan


def run_cycle(engine: Engine, settings: Settings, client: GsoClient | None = None) -> CycleResult:
    cycle = CycleResult(started_at=utcnow())
    if _live_blocked(settings):
        # Don't spam the run log with one "disabled" row per adapter per cycle.
        cycle.skipped_reason = "live GSO access disabled (GSO_LIVE_ENABLED is not true)"
        _heartbeat(engine, cycle)
        return cycle
    own_client = client is None
    client = client or GsoClient(settings)
    try:
        with collector_lock(engine):
            client.time_cache.clear()
            for spec, day, trigger in plan_cycle(engine, settings, cycle.started_at):
                cycle.results.append(collect_one(engine, client, settings, spec, day, trigger))
            _heartbeat(engine, cycle)
    except LockBusy as exc:
        cycle.skipped_reason = str(exc)
        log.warning("cycle skipped: %s", exc)
    finally:
        if own_client:
            client.close()
    return cycle


def _live_blocked(settings: Settings) -> bool:
    from urllib.parse import urlparse

    from .http import LIVE_HOSTS

    return (urlparse(settings.gso_base_url).hostname or "").lower() in LIVE_HOSTS and not settings.gso_live_enabled


def _heartbeat(engine: Engine, cycle: CycleResult) -> None:
    try:
        with engine.begin() as conn:
            store.set_state(conn, "collector_heartbeat", {
                "cycle_started_at": cycle.started_at.isoformat(),
                "skipped_reason": cycle.skipped_reason,
                "runs": len(cycle.results),
                "failed": sum(r.status == "failed" for r in cycle.results),
                "disabled": sum(r.status == "disabled" for r in cycle.results),
            })
    except SQLAlchemyError as exc:
        log.error("heartbeat write failed: %s", exc)


def backfill(engine: Engine, settings: Settings, start: date, end: date, adapters: list[str] | None = None,
             skip_existing: bool = True, client: GsoClient | None = None) -> list[RunResult]:
    """Fetch historical days (inclusive range), oldest first. Safe to re-run."""
    if end < start:
        raise ValueError("end date is before start date")
    keys = adapters or [k for k in settings.adapters if ADAPTERS[k].takes_date]
    own_client = client is None
    client = client or GsoClient(settings)
    results: list[RunResult] = []
    try:
        with collector_lock(engine):
            day = start
            while day <= end:
                for key in keys:
                    spec = get_adapter(key)
                    if not spec.takes_date:
                        continue
                    if skip_existing:
                        with engine.connect() as conn:
                            if store.last_success(conn, key, day):
                                continue
                    results.append(collect_one(engine, client, settings, spec, day, "backfill"))
                day += timedelta(days=1)
    finally:
        if own_client:
            client.close()
    return results


def run_scheduler(engine: Engine, settings: Settings, max_cycles: int | None = None) -> None:
    """Run forever: one cycle every COLLECT_INTERVAL_SECONDS, aligned to the wall clock."""
    interval = max(60, settings.collect_interval_seconds)
    log.info("scheduler started: interval=%ss adapters=%s live=%s", interval, settings.adapters,
             settings.gso_live_enabled)
    cycles = 0
    with GsoClient(settings) as client:
        while max_cycles is None or cycles < max_cycles:
            cycle = run_cycle(engine, settings, client)
            cycles += 1
            summary = ", ".join(f"{r.adapter}/{r.target_date}:{r.status}" for r in cycle.results)
            log.info("cycle done (%d runs): %s", len(cycle.results), summary or cycle.skipped_reason)
            if max_cycles is not None and cycles >= max_cycles:
                break
            # Sleep to the next interval boundary plus a little jitter (avoid :00 thundering herd).
            now = time.time()
            sleep_for = interval - (now % interval) + random.uniform(5, 25)
            time.sleep(sleep_for)
