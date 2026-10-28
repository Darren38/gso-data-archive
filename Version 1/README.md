# GSO Data Archive — Version 1

**Website:** https://darren38.github.io/gso-data-archive/ (after the [Pages setup](#publishing-the-website))

Version 1 collects public electricity-grid data from Malaysia's Grid System Operator (GSO)
on a schedule, keeps it permanently with full revision history, and serves a solar-first
analytics dashboard.

> **Read before enabling live collection.** A third-party project reports that GSO's terms
> of use require TNB's written consent to download or store GSO data. That wording could not
> be checked first-hand from the development environment, so live access is **off by default**
> (`GSO_LIVE_ENABLED=false`). Review the terms on gso.org.my, get consent if needed, then
> enable it. Details: [docs/SOURCE_INVESTIGATION.md](docs/SOURCE_INVESTIGATION.md).

## What's in this version

| Area | Status |
|---|---|
| Collector framework (adapters, retries, rate limiting, raw snapshots, run log) | ✅ Working and tested |
| Solar collection: `Solar` field of the GSO generation-mix feed | ✅ Implemented. Endpoint is **third-party documented**, not yet observed first-hand |
| Solar Profile page (`Solar.aspx`) adapter | ⚠️ Implemented but **unverified**. Off until confirmed with `probe` |
| Demand, generation mix, tie-lines (EGAT/HVDC/PLTG), installed capacity | ✅ Implemented. Third-party documented |
| BESS, system constraints | ❌ No source identified yet. Dashboard pages say so |
| Archive: deduplication, revision history, forecasts, gap handling, quality flags | ✅ Tested on SQLite and PostgreSQL 16 |
| Automatic collection: always-on worker (`schedule`) or GitHub Actions cron | ✅ Both included. Worker tested locally |
| Automatic recovery: re-check yesterday hourly + back-fill missed days | ✅ Tested |
| Dashboard: 10 pages, MYT time, light/dark, mobile, CSV/Excel export | ✅ Tested in headless Chromium |
| Backups: native (`pg_dump` / SQLite) + portable checksummed CSV, restore | ✅ Round-trip tested (incl. PostgreSQL) |

**Not yet done:** no live GSO response has been collected. The container used for development
could not reach `www.gso.org.my`. Every test uses synthetic fixtures in the documented response format.

## Quick start (local)

```bash
cd "Version 1"
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
python -m pytest
```

Preview the dashboard with **demonstration data** (separate database, watermarked everywhere):

```bash
python -m gso_archive seed-demo
DATABASE_URL="sqlite:///$PWD/data/demo.sqlite3" python -m gso_archive serve
```

Then open http://127.0.0.1:8000.

Run the real archive locally (SQLite by default, `data/archive.sqlite3`):

```bash
cp .env.example .env    # edit it, then load it into your shell, e.g. `set -a; . ./.env; set +a`
python -m gso_archive migrate
python -m gso_archive collect          # one cycle (does nothing until GSO_LIVE_ENABLED=true)
python -m gso_archive schedule         # runs forever: every COLLECT_INTERVAL_SECONDS (default 300)
python -m gso_archive serve            # API + dashboard on http://127.0.0.1:8000
```

Exercise the whole pipeline without touching GSO, using a local stand-in server that serves the synthetic fixtures:

```bash
python scripts/fixture_server.py 8901 &
GSO_BASE_URL=http://127.0.0.1:8901 python -m gso_archive collect
```

## Commands

| Command | Purpose |
|---|---|
| `migrate` | Create or upgrade the schema (safe to repeat) |
| `collect` | One collection cycle: today, yesterday re-check, missed-day back-fill |
| `schedule` | Run cycles forever, aligned to `COLLECT_INTERVAL_SECONDS` |
| `backfill --start YYYY-MM-DD [--end …] [--adapters …] [--refetch]` | Fetch past days the source still serves |
| `serve [--host --port]` | Read-only API + dashboard |
| `status` | Monitoring summary as JSON |
| `probe` | Save GSO pages and discovered endpoints for verification (needs live access) |
| `export-static --out DIR` | Static dashboard + JSON snapshot for GitHub Pages |
| `seed-demo` | Build a separate demonstration database |
| `backup [--format native\|portable\|both]` / `restore-portable PATH` | Backups and restore |

All commands are run as `python -m gso_archive <command>`.

## Automatic collection

Collection runs on its own once it is deployed and enabled. Pick one:

1. **Always-on worker (recommended):** `docker compose up -d` starts PostgreSQL, the collector
   (`schedule`, every 5 minutes), the API and daily backups. Run it on a small VM, ideally in
   Malaysia or Singapore.
2. **GitHub Actions (no server):** `.github/workflows/collect.yml` runs `collect` every 5 minutes
   against an external PostgreSQL database. GitHub may delay or skip scheduled runs. That costs
   freshness but not data, because every request returns the whole day and missed days are back-filled automatically.

Both stay idle until `GSO_LIVE_ENABLED=true`. Full comparison: [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md).

## Publishing the website

1. Merge this branch into `main`.
2. In GitHub go to **Settings → Pages → Build and deployment → Source** and choose **GitHub Actions**.
3. Go to **Actions → "Publish dashboard to Pages" → Run workflow**. It also runs hourly and on every push to `main`.

Without a database secret, the site shows the watermarked **demo** dataset. Add the
`API_DATABASE_URL` (or `DATABASE_URL`) secret and it publishes the real archive instead.
For a live (non-snapshot) site with Excel export and revision history, deploy the API:
see [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md).

## Documentation

* [docs/SOURCE_INVESTIGATION.md](docs/SOURCE_INVESTIGATION.md): what is known about GSO's data access, how each fact was established, and what is still unknown
* [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md): design, data model, integrity rules
* [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md): GitHub, cloud hosting, database, secrets, scheduler trade-offs
* [docs/BACKUP_RESTORE.md](docs/BACKUP_RESTORE.md): backup strategy and restore procedures
* [docs/STATUS.md](docs/STATUS.md): verified facts, assumptions, limitations, test results, next steps

## Project structure

```
Version 1/
├── gso_archive/            Python package
│   ├── adapters/           source adapters (base parser + registry of GSO datasets)
│   ├── api/app.py          read-only FastAPI app (also serves web/)
│   ├── migrations/         numbered schema migrations
│   ├── collector.py        run pipeline, cycle planning, back-fill, scheduler loop
│   ├── store.py            dedup + revision-preserving writes, run bookkeeping
│   ├── analytics.py        gap-aware series, daily stats, rollups, monitoring
│   ├── http.py             polite client (retries, backoff, live-access gate)
│   ├── backup.py, export.py, export_static.py, probe.py, demo.py, cli.py, …
├── web/                    dashboard (vanilla ES modules + vendored ECharts 5.5.1)
├── tests/                  pytest suite, synthetic fixtures, browser state checks
├── scripts/fixture_server.py
├── deploy/                 PostgreSQL roles, systemd unit
├── docs/
├── Dockerfile, docker-compose.yml, .env.example, requirements.txt, pyproject.toml
```

## Known limitations

* No first-hand GSO response yet. Endpoints come from the Electricity Maps open-source parser (see investigation doc).
* GSO's terms of use may forbid automated storage without consent. This is unresolved.
* GSO may block non-Malaysian IP addresses (Electricity Maps routes its requests through a Malaysian proxy). This is untested.
* Time resolution and how far back the source keeps history are unknown until live data arrives. The collector infers the interval and back-fills only what the source still serves.
* Static (Pages) mode has no Excel export or revision viewer. Those need the API deployment.
* Energy (MWh), shares, ramps and totals are derived from archived readings and are labelled as derived.
