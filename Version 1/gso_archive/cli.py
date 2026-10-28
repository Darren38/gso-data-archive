"""Command-line interface: `python -m gso_archive <command>` (or `gso-archive`)."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import date, timedelta
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

    _print(export_site(_engine(settings), settings, Path(args.out), months=args.months))


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


def cmd_restore_portable(args, settings):
    from .backup import portable_restore

    _print(portable_restore(make_engine(settings.database_url), Path(args.path)))


def main(argv: list[str] | None = None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    p = argparse.ArgumentParser(prog="gso-archive", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("migrate", help="create/upgrade the database schema").set_defaults(fn=cmd_migrate)
    sub.add_parser("collect", help="run one collection cycle (for cron / GitHub Actions)").set_defaults(fn=cmd_collect)

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

    pr = sub.add_parser("probe", help="inspect GSO pages and save raw responses (needs GSO_LIVE_ENABLED)")
    pr.add_argument("--out", default=str(PROJECT_ROOT / "data" / "probe"))
    pr.add_argument("--no-methods", action="store_true", help="only GET the HTML pages")
    pr.set_defaults(fn=cmd_probe)

    e = sub.add_parser("export-static", help="build a static site (dashboard + JSON) for GitHub Pages")
    e.add_argument("--out", default=str(PROJECT_ROOT / "site"))
    e.add_argument("--months", type=int, help="only export the most recent N months of raw points")
    e.set_defaults(fn=cmd_export_static)

    d = sub.add_parser("seed-demo", help="create a SEPARATE demonstration database with synthetic data")
    d.add_argument("--database-url")
    d.add_argument("--days", type=int, default=60)
    d.add_argument("--force", action="store_true")
    d.set_defaults(fn=cmd_seed_demo)

    bk = sub.add_parser("backup", help="write native and/or portable backups")
    bk.add_argument("--out", default=str(PROJECT_ROOT / "backups"))
    bk.add_argument("--format", choices=["native", "portable", "both"], default="both")
    bk.set_defaults(fn=cmd_backup)

    rp = sub.add_parser("restore-portable", help="restore a portable backup into an EMPTY database")
    rp.add_argument("path")
    rp.set_defaults(fn=cmd_restore_portable)

    args = p.parse_args(argv)
    args.fn(args, load_settings())


if __name__ == "__main__":
    main()
