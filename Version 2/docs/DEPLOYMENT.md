# Deployment

Nothing in this document has been set up on any cloud account or GitHub setting. These are
instructions for the repository owner. Only the local runs described in [STATUS.md](STATUS.md) were tested.

## 1. Choosing how to run it

| | **GitHub only (default)** | Always-on worker (`schedule`) |
|---|---|---|
| What runs it | `.github/workflows/archive.yml` on GitHub Actions; site on GitHub Pages | Docker Compose or systemd on a small VM |
| Where the archive lives | One SQLite file: Actions cache → published with the site → daily GitHub Release copy | PostgreSQL |
| Interval accuracy | Every 5 min requested; GitHub often runs scheduled jobs late or skips some | ±30 s |
| Completeness | Complete while GSO still serves the day (whole-day requests + automatic back-fill) | Complete |
| Network origin | GitHub's (US) addresses. GSO may block them | You choose (Malaysia/Singapore is lowest risk) |
| Raw response files | Not kept (runner disks are thrown away) | Kept and synced off-site |
| Cost | Free for a public repository | Small VM ≈ US$4–6/month |

**Recommendation:** start with **GitHub only**, matching the owner's other projects. Move to the worker only if
GSO turns out to block GitHub's addresses (the Status page will show repeated HTTP errors) or you need exact
5-minute timing. The worker's interval is set in one place, `COLLECT_INTERVAL_SECONDS`. The workflow's cron line is
GitHub's own setting and cannot read environment variables.

### GitHub-only limits to keep in mind

* Actions cache: 10 GB per repository. The workflow keeps only the newest 3 saved archives (the `tidy` job).
* GitHub Pages: sites up to 1 GB. The archive file grows by an estimated 20–40 MB a year, so many years fit.
* Release files: up to 2 GB each. The daily backup keeps 14 recent copies plus one a month.
* Scheduled workflows run only from the default branch. GitHub pauses them after 60 days without a push; the
  `keepalive` job switches the workflow back on every day.

## 2. Database

Only needed for Option B, or if you set the `DATABASE_URL` secret. The GitHub-only mode needs no database service.

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

## 3. Option B: VM with Docker Compose

```bash
git clone https://github.com/Darren38/gso-data-archive.git && cd "gso-data-archive/Version 2"
cp .env.example .env && chmod 600 .env       # set POSTGRES_PASSWORD, GSO_USER_AGENT, …
docker compose up -d --build
docker compose logs -f collector
```

* Put a TLS reverse proxy in front of `127.0.0.1:8000`. Caddy example: `archive.example.com { reverse_proxy 127.0.0.1:8000 }`.
* After reviewing GSO's terms: set `GSO_LIVE_ENABLED=true` in `.env`, then run `docker compose up -d`.
* Sync raw snapshots and backups off-site daily, e.g. `rclone sync ./backups r2:gso-archive/backups`.
* Without Docker, use `deploy/gso-archive-collector.service` (systemd) plus `python -m gso_archive serve`.

## 4. Option A: GitHub only (default)

1. Merge into `main`. **Settings → Pages → Source: GitHub Actions.**
2. **Actions → "Collect and publish" → Run workflow.** The site appears with watermarked demonstration data.
3. After reviewing GSO's terms, add the repository variable `GSO_LIVE_ENABLED` = `true`. Real collection starts on the next run.

Repository → **Settings → Secrets and variables → Actions** (all optional except the first variable):

| Kind | Name | Value |
|---|---|---|
| Variable | `GSO_LIVE_ENABLED` | `true` to collect (only after the terms review) |
| Variable | `GSO_ADAPTERS` | override the list of datasets |
| Variable | `PAGES_ALLOW_DEMO` | `false` to publish nothing until real data exists |
| Variable | `SITE_URL` | only if the site moves to a custom domain |
| Secret | `DATABASE_URL` | use your own PostgreSQL instead of the GitHub-only archive |
| Secret | `BACKUP_S3_URI`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` | an extra daily backup copy to S3 / R2 / B2 |
| Variable | `BACKUP_S3_ENDPOINT` | for Cloudflare R2 / Backblaze B2 |

Workflows:

| Workflow | Trigger | Does |
|---|---|---|
| `archive.yml` | every 5 min, push to `main`, manual | carry archive over → collect → save → build → publish → check-up; daily: Release backup + keepalive |
| `ci.yml` | push / PR | pytest on SQLite and PostgreSQL 16, plus browser checks |

## 5. Website hosting

* **GitHub Pages:** published by `archive.yml` after every collection run. URL: `https://darren38.github.io/gso-data-archive/`.
  CSV downloads and the whole-archive download work. Excel export and the revision viewer need the API.
* **Live API + dashboard:** the `api` service (Option B), or any container host (Fly.io, Render, Railway, Cloud Run) running the
  `Dockerfile` with `API_DATABASE_URL` set to the read-only role. To serve the Pages front end from the API instead of snapshots, set
  `web/config.js` to `{mode: "api", apiBase: "https://archive.example.com"}` and add your Pages origin to `API_CORS_ORIGINS`.

## 6. Security checklist

* Secrets only in `.env` (git-ignored), the GitHub secret store, or the platform's secret manager. `.env.example` holds placeholders only.
* The public API is GET-only and uses a read-only DB role. Inputs are validated (series-key regex, date parsing, range caps). All SQL is parameterised by SQLAlchemy. Database errors return a generic 503 and never echo connection strings.
* Security headers: `nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy`. Add HSTS at the TLS proxy.
* The container runs as a non-root user. The systemd unit uses `ProtectSystem=strict`.
* The browser never receives database credentials or write access.
