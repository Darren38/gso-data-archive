# Architecture

```
               ┌──────────── privileged side ────────────┐      ┌──────── public side ────────┐
 gso.org.my ──▶│ collector (schedule | Actions cron)      │      │ API (read-only FastAPI)     │──▶ browser
  PageMethods  │  http.py → adapters → store.py           │─────▶│  + dashboard (web/)         │
               │  raw snapshots → RAW_STORE_DIR (gzip)    │  DB  │ or static export → Pages    │
               └──────────────────────────────────────────┘      └─────────────────────────────┘
                              │ backups (native + portable) → object storage
```

## GitHub-only mode (Version 2 default)

```
 every ~5 min (archive.yml)
 ┌───────────────────────────────────────────────────────────────────────────────────────┐
 │ Actions cache ──┐                                                                      │
 │ (newest archive)├─▶ merge ─▶ collect ─▶ save to cache ─▶ export site ─▶ Pages ─▶ check-up │
 │ live site copy ─┘   (union)                              (+ archive.sqlite3.gz)         │
 └───────────────────────────────────────────────────────────────────────────────────────┘
 daily: portable backup ─▶ "archive-backups" GitHub Release · keepalive
```

The archive is a single SQLite file. A run starts from the newest copy in the Actions cache and merges in the
copy published on the site (`gso_archive/archive_sync.py`, modelled on Tech Comparison Hub's `seed_live.py`).
The merge is a union, so an older copy can never roll a newer one back. The concurrency group runs the jobs one at
a time. Raw responses are not kept in this mode.

## Key decisions

| Decision | Why |
|---|---|
| **Python + SQLAlchemy Core** | Same code runs on PostgreSQL (production) and SQLite (zero-setup local/tests). Core keeps SQL explicit and parameterised. |
| **One adapter = declarative `AdapterSpec`** | Most GSO pages share one PageMethod format, so a new dataset is ~10 lines. Non-time-series pages plug in a `transform`. |
| **Whole-day requests** | The source answers per calendar day, so a delayed or missed run loses nothing while the source still serves that day. That makes a cheap, imperfect scheduler acceptable. |
| **Auto-discovery of unknown fields** | A schema change (new fuel, renamed field) creates a new flagged series instead of dropping data. The run is marked `schema_changed`. |
| **Read-only public API, no admin endpoints** | Collection and administration happen only through the CLI with write credentials. The API can run with a read-only DB role. |
| **Static export mode** | GitHub Pages can host the full dashboard and a JSON snapshot with no server. The API is optional. |
| **Vanilla JS + vendored ECharts** | No build step, no runtime CDN dependency, handles long time series. All times are rendered in MYT via `useUTC` + an 8 h shift, whatever the viewer's timezone. |

## Data model

| Table | Purpose |
|---|---|
| `datasets` | One row per adapter: category, source page, **verification level**, demo flag |
| `series` | One measurable series (`generation_mix.solar`): unit, kind (`actual`/`forecast`/`capacity`), source field, inferred interval, `auto_discovered` |
| `observations` | Current best value per `(series_id, obs_time)`, the primary key that prevents duplicates. Has `first_collected_at`, `last_changed_at` (record revision time), `revision_count`, `quality` |
| `observation_revisions` | **Append-only** history. One row for each distinct value ever seen, with `previous_value`, `collected_at`, `run_id`, `raw_snapshot_id` |
| `forecasts` | `(series, target_time, issue_time)`. When the source gives no issue time, collection time is used and `issue_time_inferred=true`. A new row is stored only when the value changes |
| `collection_runs` | One row per request: trigger, target day, status, HTTP status, counts (new/revised/unchanged/missing/suspect/rejected), duration, error type, schema signature, latest observation time |
| `raw_snapshots` | Metadata for each fetched response (SHA-256, size, path). Identical bytes are stored once (`RAW_RETENTION=changed`) |
| `system_state` | Collector heartbeat, last backup |
| `schema_migrations` | Applied migration versions |

The five time concepts are kept separate:

| Concept | Column |
|---|---|
| Observation time | `observations.obs_time` |
| Collection time | `observation_revisions.collected_at`, `raw_snapshots.fetched_at` |
| Forecast issue time | `forecasts.issue_time` |
| Forecast target time | `forecasts.target_time` |
| Record revision time | `observations.last_changed_at` |

All are UTC. Display is MYT.

## Integrity rules (enforced in `store.py` / `collector.py`)

1. **Never delete, never silently overwrite.** A changed value updates `observations` and appends to `observation_revisions` in the same transaction.
2. **Missing ≠ zero.** Null, blank, `-` and `N/A` values are counted (`records_missing`) and never stored. The API emits explicit gap markers, and exports omit those rows.
3. **Quality flags, not corrections.** `suspect_negative`, `out_of_range` and `suspect_night` (solar > 50 MW at night) are stored next to the published value.
4. **Failure isolation.** Run start, raw snapshot and run result are committed separately, so a crash or parse error leaves an audit trail. The observation write is one transaction: all or nothing.
5. **Single writer.** A PostgreSQL advisory lock (or a file lock on SQLite) stops overlapping cycles.
6. **Collection health ≠ data freshness.** A run is `success` when the request and storage worked, even if GSO published nothing new. Freshness comes from the newest `obs_time`.

## Cycle planning (`collector.plan_cycle`)

For each enabled adapter, each cycle:

* requests **today** (MYT);
* re-requests **yesterday** if it hasn't been fetched successfully in the last `GSO_REVISION_RECHECK_MINUTES` (catches late or revised readings);
* back-fills up to `GSO_AUTO_BACKFILL_PER_CYCLE` days within `GSO_AUTO_BACKFILL_DAYS` that have never been fetched successfully (catches collector downtime);
* skips adapters with a `min_interval_seconds` that ran recently (capacity: daily).

Longer gaps: `python -m gso_archive backfill --start … --end …`.

## Monitoring (`/api/v1/status`, dashboard "Collection Status")

Covers: last run and last success per adapter, consecutive failures, runs/failures/new/revised in the last 24 h, median duration,
parse/schema errors, schema-change detection, per-series freshness and missing readings in the last 24 h, database
connectivity, collector heartbeat, last backup, archive totals. `python -m gso_archive status` prints the same
JSON for external alerting (e.g. a cron job that alerts when `consecutive_failures > 6`).
