"""Command-line interface: `python -m gso_archive <command>` (or `gso-archive`)."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

from .config import PROJECT_ROOT, load_settings
from .db import make_engine
from .migrations import current_version, migrate
from .timeutil import myt_today


def _engine(settings):
    engine = make_engine(settings.database_url)
    migrate(engine)
    return engine


def _print(obj) -> None:
    print(json.dumps(obj, indent=2, default=str))


def cmd_migrate(args, settings):
    engine = make_engine(settings.database_url)
    applied = migrate(engine)
    _print({"applied": applied, "schema_version": current_version(engine)})


def cmd_collect(args, settings):
    from .collector import run_cycle

    cycle = run_cycle(_engine(settings), settings)
    _print({"skipped": cycle.skipped_reason, "runs": [r.__dict__ for r in cycle.results]})
    # Exit non-zero only if every attempted run failed (so CI shows red on outages).
    if cycle.results and all(r.status == "failed" for r in cycle.results):
        sys.exit(2)


def cmd_trial(args, settings):
    from dataclasses import replace

    from .trial import run_trial

    keys = None if args.all or not args.adapters else args.adapters.split(",")
    results = run_trial(replace(settings, gso_live_enabled=True), keys)
    _print({"trial": results, "writes": "none"})
    if any(r["result"].startswith("COLLECTOR BUG") for r in results):
        sys.exit(3)  # GitHub shows the step red: a collector would have failed live


def cmd_weather_trial(args, settings):
    """Fetch and read one Open-Meteo forecast for the LSS regions, write nothing (run by the probe job on GitHub)."""
    import httpx

    from . import weather
    from .db import make_engine

    try:  # the probe job has no archive: then the built-in region locations
        with make_engine(settings.database_url).connect() as conn:
            points = weather.region_points(conn)
    except Exception:  # noqa: BLE001
        points = dict(weather.FALLBACK)
    params = {"latitude": ",".join(str(p[0]) for p in points.values()), "longitude": ",".join(str(p[1]) for p in points.values()),
              "hourly": "shortwave_radiation,cloud_cover", "timezone": "UTC", "past_days": 1, "forecast_days": 3}
    try:
        with httpx.Client(timeout=weather.TIMEOUT, headers={"User-Agent": settings.user_agent}) as c:
            res = c.get(weather.URL, params=params)
            res.raise_for_status()
            readings = weather.parse(res.json(), points)
        peak = {r: max((x.value for x in readings if x.series == f"{r}_ghi"), default=None) for r in weather.REGIONS}
        _print({"weather_trial": "ok", "points": points, "readings": len(readings), "peak_ghi": peak, "writes": "none"})
    except Exception as exc:  # noqa: BLE001
        _print({"weather_trial": "failed", "error": f"{type(exc).__name__}: {exc}"})
        sys.exit(3)


def cmd_irradiance_trial(args, settings):
    """Try two sources of measured (satellite-based) hourly sunshine for the LSS regions and report how recent their
    newest hour is, writing nothing. Run by the probe job on GitHub before any such data is collected: it is added only
    if it is hourly and recent enough to set beside GSO's readings."""
    from datetime import timedelta

    import httpx

    from . import weather
    from .timeutil import utcnow

    try:
        with make_engine_ro(settings) as conn:
            points = weather.region_points(conn)
    except Exception:  # noqa: BLE001
        points = dict(weather.FALLBACK)
    now = utcnow()
    out: dict = {"irradiance_trial": now.isoformat(), "points": points, "writes": "none"}
    with httpx.Client(timeout=30, headers={"User-Agent": settings.user_agent}) as c:
        # 1. Open-Meteo satellite radiation (JMA Himawari), hourly averages of the preceding hour, UTC.
        try:
            res = c.get("https://satellite-api.open-meteo.com/v1/archive", params={
                "latitude": ",".join(str(p[0]) for p in points.values()), "longitude": ",".join(str(p[1]) for p in points.values()),
                "hourly": "shortwave_radiation", "models": "jma_jaxa_himawari", "past_days": 3, "timezone": "UTC"})
            body = res.json() if res.headers.get("content-type", "").startswith("application/json") else res.text[:300]
            items = body if isinstance(body, list) else [body]
            regions = {}
            for name, item in zip(points, items):
                h = (item or {}).get("hourly", {}) if isinstance(item, dict) else {}
                pairs = [(t, v) for t, v in zip(h.get("time", []), h.get("shortwave_radiation", [])) if v is not None]
                newest = pairs[-1][0] if pairs else None
                regions[name] = {"hours_with_values": len(pairs), "newest": newest,
                                 "behind_hours": round((now - datetime.fromisoformat(newest).replace(tzinfo=now.tzinfo)).total_seconds() / 3600, 1) if newest else None,
                                 "last_values": pairs[-8:], "units": (item or {}).get("hourly_units") if isinstance(item, dict) else None}
            out["open_meteo_satellite"] = {"status": res.status_code, "regions": regions,
                                           **({"answer": body} if res.status_code != 200 or not regions else {})}
        except Exception as exc:  # noqa: BLE001
            out["open_meteo_satellite"] = {"error": f"{type(exc).__name__}: {exc}"}
        # 2. NASA POWER hourly all-sky surface shortwave (one region: its delay is the same everywhere).
        try:
            lat, lon = points["central"]
            res = c.get("https://power.larc.nasa.gov/api/temporal/hourly/point", params={
                "parameters": "ALLSKY_SFC_SW_DWN", "community": "RE", "latitude": lat, "longitude": lon,
                "start": (now - timedelta(days=14)).strftime("%Y%m%d"), "end": now.strftime("%Y%m%d"),
                "format": "JSON", "time-standard": "UTC"})
            data = res.json()
            series = data.get("properties", {}).get("parameter", {}).get("ALLSKY_SFC_SW_DWN", {})
            good = sorted(k for k, v in series.items() if v is not None and v > -900)
            newest = good[-1] if good else None
            behind = None
            if newest:
                t = datetime.strptime(newest, "%Y%m%d%H").replace(tzinfo=now.tzinfo)
                behind = round((now - t).total_seconds() / 3600, 1)
            out["nasa_power"] = {"status": res.status_code, "hours_with_values": len(good), "newest": newest, "behind_hours": behind,
                                 "units": data.get("parameters", {}).get("ALLSKY_SFC_SW_DWN", {}).get("units"),
                                 "last_values": [(k, series[k]) for k in good[-6:]]}
        except Exception as exc:  # noqa: BLE001
            out["nasa_power"] = {"error": f"{type(exc).__name__}: {exc}"}
    _print(out)


def make_engine_ro(settings):
    from .db import make_engine

    return make_engine(settings.database_url).connect()


def cmd_backfill(args, settings):
    from .collector import backfill

    start, end = date.fromisoformat(args.start), date.fromisoformat(args.end or myt_today().isoformat())
    adapters = args.adapters.split(",") if args.adapters else None
    results = backfill(_engine(settings), settings, start, end, adapters, skip_existing=not args.refetch)
    _print({"runs": len(results), "failed": sum(r.status == "failed" for r in results),
            "new_records": sum(r.records_new for r in results),
            "revised_records": sum(r.records_revised for r in results)})


def cmd_schedule(args, settings):
    from .collector import run_scheduler

    run_scheduler(_engine(settings), settings, max_cycles=args.cycles)


def cmd_serve(args, settings):
    import uvicorn

    from .api.app import create_app

    engine = _engine(settings)
    uvicorn.run(create_app(settings, engine), host=args.host, port=args.port, log_level="info")


def cmd_status(args, settings):
    from . import analytics

    with _engine(settings).connect() as conn:
        _print(analytics.status(conn, settings.adapters, settings.gso_live_enabled))


def cmd_probe(args, settings):
    from .probe import run_probe

    _print(run_probe(settings, Path(args.out), try_methods=not args.no_methods))


def cmd_export_static(args, settings):
    from .export_static import export_site

    engine = _engine(settings)
    if args.demo_if_empty and not _has_real_data(engine):
        # Nothing collected yet: publish the watermarked demonstration data so the site is never blank.
        # It is built in a separate throwaway database and never touches the archive.
        import tempfile
        from dataclasses import replace

        from .demo import seed_demo

        tmp = Path(tempfile.mkdtemp()) / "demo.sqlite3"
        demo_url = f"sqlite:///{tmp}"
        demo_engine = make_engine(demo_url)
        migrate(demo_engine)
        seed_demo(demo_engine, days=90)
        _print({"demo": True, **export_site(demo_engine, replace(settings, database_url=demo_url), Path(args.out),
                                            include_archive=False)})
        return
    _print(export_site(engine, settings, Path(args.out), months=args.months, include_archive=not args.no_archive))


def _has_real_data(engine) -> bool:
    from sqlalchemy import func, select

    from . import db

    with engine.connect() as conn:
        return bool(conn.execute(select(func.count()).select_from(db.series).where(db.series.c.is_demo.is_(False))).scalar())


def cmd_seed_live(args, settings):
    from .archive_sync import seed_from_live

    _print(seed_from_live(settings.database_url, args.base))


def cmd_merge(args, settings):
    from .archive_sync import merge_archive

    _print(merge_archive(make_engine(args.source), _engine(settings)))


def cmd_health_check(args, settings):
    """Checks the live site and, with --verify, GSO's current answers against the archive (verify.py). Fails (GitHub
    then emails the owner) only for problems not emailed in the last day (alerts.py, with --state)."""
    from datetime import datetime, timezone
    from pathlib import Path

    from . import alerts
    from .health import check_site, write_step_summary

    now = datetime.now(timezone.utc)
    result = check_site(args.base, args.max_age_minutes, args.max_failures, write_summary=False)
    if args.newest_backup is not None:
        from .verify import backup_problem

        msg = backup_problem(args.newest_backup, now)
        if msg:
            result["problems"].append(msg)
    state_path = Path(args.state) if args.state else None
    state = alerts.load(state_path)
    if args.verify:
        from dataclasses import replace

        from .verify import verify

        try:
            v = verify(_engine(settings), replace(settings, gso_live_enabled=True), now, set(state.get("missing") or []))
        except Exception as exc:  # noqa: BLE001 - the site check above must still report
            v = {"problems": [], "notes": [f"GSO comparison could not run: {type(exc).__name__}: {exc}"], "missing": []}
        result["problems"] += v["problems"]
        result["notes"] += v["notes"]
        state["missing"] = v["missing"][:2000]
        if v.get("proof"):
            state["proof"] = v["proof"]
    send, quiet, state = alerts.decide(result["problems"], state, now) if state_path else (result["problems"], [], state)
    alerts.save(state_path, state)
    result.update(ok=not result["problems"], emailed=send, already_emailed=quiet)
    write_step_summary(send, quiet, result["notes"])
    _print(result)
    for p in send:
        print(f"::error title=GSO archive needs a look::{p}")
    if send:
        sys.exit(1)


def cmd_seed_demo(args, settings):
    from .demo import seed_demo

    url = args.database_url or f"sqlite:///{(PROJECT_ROOT / 'data' / 'demo.sqlite3').as_posix()}"
    if "demo" not in url and not args.force:
        sys.exit("refusing: demo database URL must contain 'demo' (or pass --force)")
    engine = make_engine(url)
    migrate(engine)
    _print({"database": url, **seed_demo(engine, days=args.days)})


def cmd_backup(args, settings):
    from .backup import native_backup, portable_backup

    engine = _engine(settings)
    out = Path(args.out)
    result = {}
    if args.format in ("native", "both"):
        result["native"] = native_backup(engine, settings.database_url, out)
    if args.format in ("portable", "both"):
        result["portable"] = portable_backup(engine, out)
    _print(result)


def cmd_checkup(args, settings):
    from .checkup import as_text, summary

    print(as_text(summary(_engine(settings), days=args.days)))


def cmd_restore_portable(args, settings):
    from .backup import portable_restore

    _print(portable_restore(make_engine(settings.database_url), Path(args.path)))


def main(argv: list[str] | None = None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    p = argparse.ArgumentParser(prog="gso-archive", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("migrate", help="create/upgrade the database schema").set_defaults(fn=cmd_migrate)
    sub.add_parser("collect", help="run one collection cycle (for cron / GitHub Actions)").set_defaults(fn=cmd_collect)
    sub.add_parser("irradiance-trial", help="try measured hourly sunshine sources for the LSS regions, write nothing").set_defaults(fn=cmd_irradiance_trial)
    sub.add_parser("weather-trial", help="fetch and read one Open-Meteo forecast, write nothing").set_defaults(fn=cmd_weather_trial)

    b = sub.add_parser("backfill", help="fetch historical days the source still serves")
    b.add_argument("--start", required=True, help="YYYY-MM-DD (MYT)")
    b.add_argument("--end", help="YYYY-MM-DD (MYT), default today")
    b.add_argument("--adapters", help="comma-separated adapter keys")
    b.add_argument("--refetch", action="store_true", help="also re-fetch days already collected (detect revisions)")
    b.set_defaults(fn=cmd_backfill)

    s = sub.add_parser("schedule", help="run the collector forever every COLLECT_INTERVAL_SECONDS")
    s.add_argument("--cycles", type=int, help="stop after N cycles (testing)")
    s.set_defaults(fn=cmd_schedule)

    v = sub.add_parser("serve", help="serve the read-only API and dashboard")
    v.add_argument("--host", default="127.0.0.1")
    v.add_argument("--port", type=int, default=8000)
    v.set_defaults(fn=cmd_serve)

    sub.add_parser("status", help="print monitoring status").set_defaults(fn=cmd_status)

    tr = sub.add_parser("trial", help="fetch and read GSO's live answers with the collectors; report, write nothing")
    tr.add_argument("adapters", nargs="?", help="comma-separated collector names (default: --all)")
    tr.add_argument("--all", action="store_true", help="every collector, including ones not in GSO_ADAPTERS")
    tr.set_defaults(fn=cmd_trial)

    pr = sub.add_parser("probe", help="inspect GSO pages and save raw responses (needs GSO_LIVE_ENABLED)")
    pr.add_argument("--out", default=str(PROJECT_ROOT / "data" / "probe"))
    pr.add_argument("--no-methods", action="store_true", help="only GET the HTML pages")
    pr.set_defaults(fn=cmd_probe)

    e = sub.add_parser("export-static", help="build a static site (dashboard + JSON) for GitHub Pages")
    e.add_argument("--out", default=str(PROJECT_ROOT / "site"))
    e.add_argument("--months", type=int, help="only export the most recent N months of raw points")
    e.add_argument("--no-archive", action="store_true", help="leave out data/archive.sqlite3.gz")
    e.add_argument("--demo-if-empty", action="store_true",
                   help="if nothing has been collected yet, publish the watermarked demo data instead")
    e.set_defaults(fn=cmd_export_static)

    sl = sub.add_parser("seed-live", help="carry the archive over from the published site (GitHub-only mode)")
    sl.add_argument("--base", required=True, help="site address, e.g. https://darren38.github.io/gso-data-archive/")
    sl.set_defaults(fn=cmd_seed_live)

    mg = sub.add_parser("merge", help="merge another archive database into DATABASE_URL (keeps the union)")
    mg.add_argument("source", help="database URL of the archive to merge in")
    mg.set_defaults(fn=cmd_merge)

    hc = sub.add_parser("health-check", help="check the published site (fails if collection has stopped)")
    hc.add_argument("--base", required=True)
    hc.add_argument("--max-age-minutes", type=int, default=120)
    hc.add_argument("--max-failures", type=int, default=12)
    hc.add_argument("--verify", action="store_true", help="also compare GSO's current answers with the archive (DATABASE_URL)")
    hc.add_argument("--state", help="file remembering which problems were emailed (email each once a day at most)")
    hc.add_argument("--newest-backup", help="name of the newest file in the archive-backups release ('' if none)")
    hc.set_defaults(fn=cmd_health_check)

    d = sub.add_parser("seed-demo", help="create a SEPARATE demonstration database with synthetic data")
    d.add_argument("--database-url")
    d.add_argument("--days", type=int, default=60)
    d.add_argument("--force", action="store_true")
    d.set_defaults(fn=cmd_seed_demo)

    bk = sub.add_parser("backup", help="write native and/or portable backups")
    bk.add_argument("--out", default=str(PROJECT_ROOT / "backups"))
    bk.add_argument("--format", choices=["native", "portable", "both"], default="both")
    bk.set_defaults(fn=cmd_backup)

    cu = sub.add_parser("checkup", help="print readings per source and day, and collection stops (maintenance check-up)")
    cu.add_argument("--days", type=int, default=8)
    cu.set_defaults(fn=cmd_checkup)
    rp = sub.add_parser("restore-portable", help="restore a portable backup into an EMPTY database")
    rp.add_argument("path")
    rp.set_defaults(fn=cmd_restore_portable)

    args = p.parse_args(argv)
    args.fn(args, load_settings())


if __name__ == "__main__":
    main()
