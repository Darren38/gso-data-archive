# Version 1 status: facts, assumptions, limitations, next steps

Status as of 28 October 2026.

## Test results

| Run | Result |
|---|---|
| Full suite on SQLite (incl. 4 browser tests in headless Chromium) | **80 passed** |
| Suite on PostgreSQL 16 (browser tests excluded; 2 SQLite-only tests skipped) | **74 passed, 2 skipped** |

The suite covers: parsing valid responses; missing and malformed fields; timestamp/timezone
conversion; duplicate prevention; revised readings; historical back-fill; failed network requests
(retry, no retry on 4xx, recovery); database failures (rollback, data preserved); schema changes;
the live-access gate; cycle planning; the concurrency lock; API validation; CSV/Excel export;
backup/restore; static export; demo isolation; and dashboard loading, empty, error, demo and static states.

## Validated end to end (manually, in the development container)

* Real HTTP via `scripts/fixture_server.py` (synthetic fixtures) → `python -m gso_archive collect` / `backfill` /
  `schedule --cycles 1` → PostgreSQL 16 → `status` → API → dashboard. Cycle 1: 13 runs, all successful
  (today, yesterday re-check, 2 back-filled days per adapter, capacity snapshot). Cycle 2: today deduplicated
  (0 new / 288 unchanged), re-check correctly skipped, back-fill continued, daily capacity correctly skipped.
* Every dashboard page rendered at 1440 px (light) and 390 px (dark) with no console errors and no horizontal scroll.
* PostgreSQL `pg_dump` → `pg_restore`, and portable backup → restore into PostgreSQL.
* GitHub Pages build reproduced locally (demo mode): 114 files, 8.6 MB.

## Verified facts

* The development container cannot reach `www.gso.org.my` (egress policy), so no GSO response was observed.
* The maintained Electricity Maps parser uses the PageMethod endpoints, parameters and fields listed in
  SOURCE_INVESTIGATION.md §2, and routes requests through a Malaysian proxy.
* A third-party project states that GSO's terms require TNB's written consent to download or store GSO data.

## Assumptions (unverified)

* The Electricity Maps endpoint descriptions are current and accurate.
* Naive GSO timestamps are MYT (consistent with Electricity Maps).
* Values are MW.
* `Solar.aspx` follows the same PageMethod pattern (`GetChartDataSource`). This is unverified, so that adapter is off by default.
* Tie-line sign: positive = export from Peninsular Malaysia (Electricity Maps' reading). Values are stored as published either way.

## Limitations

* No live data collected. Production collection depends on (a) the terms/consent decision, (b) network
  reachability from the chosen host, and (c) the documented endpoints still working.
* The time resolution and how far back GSO keeps history are unknown.
* No transmission/distribution split, solar forecast, BESS or constraints data until a source is identified.
  The UI shows "not available" states and never shows estimates.
* Static Pages mode: no Excel export or revision viewer, and data is up to one hour old.
* The API computes daily statistics on request (fine for decades of 30-minute data; add materialised daily
  tables if the resolution turns out to be very fine).
* No alerting integration (email/Slack). Monitoring is exposed via `/api/v1/status` and `python -m gso_archive status`.
* Docker images and Compose were written but not built here (no Docker daemon in the container).
  GitHub workflows were syntax-checked but not run (they run once pushed or merged).

## Unresolved issues (need the owner)

1. **Terms of use / consent.** Read GSO's terms. If consent is required, request it before setting `GSO_LIVE_ENABLED=true`.
2. **Hosting location.** Choose the VM region (Malaysia/Singapore recommended) or accept GitHub Actions' limits.
3. **Database provider** and the off-site backup target (S3/R2/B2 credentials).
4. Enable GitHub Pages (Settings → Pages → Source: GitHub Actions) after merging to `main`.

## Recommended next phase (Version 2)

1. Run `probe` from an allowed network. Mark the adapters verified, replace the synthetic fixtures with real
   ones, and confirm `Solar.aspx` and the landing-page metrics (BESS, headline values).
2. Map the confirmed Solar Profile fields (transmission/distribution/forecast) to named series. Enable the forecast-vs-actual analysis with real issue times if they are published.
3. Add materialised daily/monthly aggregates and an alert hook (e.g. email or a webhook when an adapter has 6 consecutive failures or data goes stale).
4. Measure the source's history window, then run a one-off `backfill` of everything still available.
5. Add a weather/irradiance context layer (e.g. MET Malaysia or open reanalysis data) to explain solar variability, and a capacity-factor view using the installed-capacity snapshots.

## Files created in Version 1

```
README.md (repository root: rewritten; website link + version index)
.gitignore (appended archive-specific entries)
.github/workflows/{ci,collect,pages,backup}.yml
Version 1/
  README.md  .env.example  Dockerfile  docker-compose.yml  pyproject.toml  requirements.txt
  gso_archive/{__init__,__main__,config,timeutil,db,http,rawstore,store,locks,collector,analytics,export,
               export_static,probe,demo,backup,cli}.py
  gso_archive/adapters/{__init__,base,registry}.py
  gso_archive/api/{__init__,app}.py
  gso_archive/migrations/__init__.py
  web/{index.html,config.js,css/app.css}
  web/js/{app,data,ui,charts,analysis}.js
  web/js/pages/{overview,solar,demand,generation,tieline,unavailable,explorer,status,about}.js
  web/vendor/{echarts-5.5.1.min.js,ECHARTS-LICENSE.txt}
  tests/{__init__,conftest,test_timeutil,test_parsing,test_store,test_collector,test_api,
         test_backup_and_export,test_frontend}.py
  tests/frontend/check_states.cjs
  tests/fixtures/*.json, not_json.html, README.md (synthetic)
  scripts/fixture_server.py
  deploy/{postgres-roles.sql,gso-archive-collector.service}
  docs/{SOURCE_INVESTIGATION,ARCHITECTURE,DEPLOYMENT,BACKUP_RESTORE,STATUS}.md
```
