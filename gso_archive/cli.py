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


def cmd_trial(args, settings):
    from dataclasses import replace

    from .trial import run_trial

    keys = None if args.all or not args.adapters else args.adapters.split(",")
    results = run_trial(replace(settings, gso_live_enabled=True), keys)
    _print({"trial": results, "writes": "none"})
    if any(r["result"].startswith("COLLECTOR BUG") for r in results):
        sys.exit(3)  # GitHub shows the step red: a collector would have failed live


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
    from .health import check_site

    result = check_site(args.base, args.max_age_minutes, args.max_failures)
    _print(result)
    if not result["ok"]:
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

    rp = sub.add_parser("restore-portable", help="restore a portable backup into an EMPTY database")
    rp.add_argument("path")
    rp.set_defaults(fn=cmd_restore_portable)

    args = p.parse_args(argv)
    args.fn(args, load_settings())


if __name__ == "__main__":
    main()
