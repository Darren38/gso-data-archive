# Deployment

Nothing in this document has been set up on any cloud account or GitHub setting. These are
instructions for the repository owner. Only the local runs described in [STATUS.md](STATUS.md) were tested.

## 1. Choosing a scheduler

| | Always-on worker (`schedule`) | GitHub Actions cron (`collect.yml`) |
|---|---|---|
| Interval accuracy | ±30 s, aligned to the clock | Often delayed 5–30 min; runs can be skipped under load |
| Data completeness | Complete | Complete while the source keeps the day (whole-day requests + auto back-fill) |
| Network origin | You choose (a Malaysian/Singaporean VM lowers geo-block risk) | GitHub/Azure US IPs. GSO may block them |
| Raw response retention | Persistent volume → sync to object storage | Ephemeral runner, so raw retention is off |
| Cost | Small VM ≈ US$4–6/month | Free for public repos. Private: ~8,600 runs/month far exceeds the 2,000 free minutes |
| Maintenance | OS updates, monitoring | Schedules pause after 60 days of repo inactivity; default branch only |

**Recommendation:** run the **always-on worker** on a small VM in Malaysia or Singapore with
Docker Compose, which gives accurate 5-minute cadence, raw retention and the lowest geo-block
risk. Use GitHub Actions for CI, Pages publishing and off-site backups. If you don't want a server,
the Actions collector is acceptable for *archival completeness* but not for *freshness*.

The worker's interval is set in one place: `COLLECT_INTERVAL_SECONDS`. The Actions cron
string (`*/5 * * * *`) is a GitHub setting that cannot read environment variables. It is the only
other place a schedule appears, and it only matters if you use that workflow.

## 2. Database

Any PostgreSQL ≥ 14. Options:

* **Same VM via Docker Compose** (bundled `db` service). Cheapest. Back up off-site (see BACKUP_RESTORE.md).
* **Managed:** Neon, Supabase, Railway, DigitalOcean, AWS RDS, Google Cloud SQL. Choose a provider with point-in-time recovery.

Setup:

```bash
# 1. Create the database and a writer role (managed providers do this in their UI).
# 2. Apply the schema:
DATABASE_URL=postgresql://gso_writer:…@host:5432/gso_archive python -m gso_archive migrate
# 3. Create the read-only role for the public API / Pages export:
psql "$DATABASE_URL" -f deploy/postgres-roles.sql     # edit the password first
```

Migrations are numbered and forward-only (`gso_archive/migrations/__init__.py`). Running `migrate` again does nothing.
Every command runs `migrate` automatically before it starts.

Storage estimate: about 6 adapters × 48–288 readings/day ≈ 0.3–2 million rows/year, well under 1 GB/year in PostgreSQL.
Raw snapshots at `RAW_RETENTION=changed` are roughly 1–3 GB/year of gzip files.

## 3. Option A: VM with Docker Compose (recommended)

```bash
git clone https://github.com/Darren38/gso-data-archive.git && cd "gso-data-archive/Version 1"
cp .env.example .env && chmod 600 .env       # set POSTGRES_PASSWORD, GSO_USER_AGENT, …
docker compose up -d --build
docker compose logs -f collector
```

* Put a TLS reverse proxy in front of `127.0.0.1:8000`. Caddy example: `archive.example.com { reverse_proxy 127.0.0.1:8000 }`.
* After reviewing GSO's terms: set `GSO_LIVE_ENABLED=true` in `.env`, then run `docker compose up -d`.
* Sync raw snapshots and backups off-site daily, e.g. `rclone sync ./backups r2:gso-archive/backups`.
* Without Docker, use `deploy/gso-archive-collector.service` (systemd) plus `python -m gso_archive serve`.

## 4. Option B: no server (GitHub Actions + managed PostgreSQL)

Repository → **Settings → Secrets and variables → Actions**:

| Kind | Name | Value |
|---|---|---|
| Secret | `DATABASE_URL` | Writer connection string (managed PostgreSQL, SSL) |
| Secret | `API_DATABASE_URL` | Read-only connection string (used by Pages export) |
| Variable | `GSO_LIVE_ENABLED` | `true` (only after the terms review) |
| Variable | `GSO_ADAPTERS` | optional override |
| Variable | `GSO_USER_AGENT` | `gso-data-archive/1.0 (contact: you@example.com)` |
| Secret | `BACKUP_S3_URI`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` | optional off-site backup target |
| Variable | `BACKUP_S3_ENDPOINT` | for Cloudflare R2 / Backblaze B2 |
| Variable | `PAGES_ALLOW_DEMO` | `false` to stop publishing the demo when no DB secret exists |

Workflows (all in `.github/workflows/`):

| Workflow | Trigger | Does |
|---|---|---|
| `ci.yml` | push / PR | pytest on SQLite and PostgreSQL 16, plus browser state tests |
| `collect.yml` | every 5 min | one collection cycle. Skips cleanly until configured |
| `pages.yml` | hourly, push to `main`, manual | static dashboard + JSON snapshot → GitHub Pages |
| `backup.yml` | daily 03:43 MYT | portable backup → S3-compatible storage + 90-day artifact |

Scheduled workflows run only from the **default branch**, so merge to `main` first.

## 5. Website hosting

* **GitHub Pages (static snapshot):** enable **Settings → Pages → Source: GitHub Actions**, then run "Publish dashboard to Pages".
  URL: `https://darren38.github.io/gso-data-archive/`. It refreshes hourly. CSV export works; Excel export and revision history need the API.
* **Live API + dashboard:** the `api` service (Option A), or any container host (Fly.io, Render, Railway, Cloud Run) running the
  `Dockerfile` with `API_DATABASE_URL` set to the read-only role. To serve the Pages front end from the API instead of snapshots, set
  `web/config.js` to `{mode: "api", apiBase: "https://archive.example.com"}` and add your Pages origin to `API_CORS_ORIGINS`.

## 6. Security checklist

* Secrets only in `.env` (git-ignored), the GitHub secret store, or the platform's secret manager. `.env.example` holds placeholders only.
* The public API is GET-only and uses a read-only DB role. Inputs are validated (series-key regex, date parsing, range caps). All SQL is parameterised by SQLAlchemy. Database errors return a generic 503 and never echo connection strings.
* Security headers: `nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy`. Add HSTS at the TLS proxy.
* The container runs as a non-root user. The systemd unit uses `ProtectSystem=strict`.
* The browser never receives database credentials or write access.
