# For developers

Visitors don't need any of this: the site runs online at https://darren38.github.io/gso-data-archive/ and updates
itself. This page is for working on the code.

## Run the dashboard on your own computer

Needs Python 3.11 or newer.

```bash
pip install -r requirements.txt
python -m gso_archive seed-demo
DATABASE_URL="sqlite:///$PWD/data/demo.sqlite3" python -m gso_archive serve
```

Open http://127.0.0.1:8000. This shows *demonstration* data, clearly marked on every page.

## Commands

All are run as `python -m gso_archive <command>`:

| Command | What it does |
|---|---|
| `collect` | One round of collection from GSO |
| `schedule` | Collect every 2 minutes on your own computer or server (`COLLECT_INTERVAL_SECONDS`, minimum 60) |
| `backfill --start YYYY-MM-DD` | Fetch past days from GSO's date-based pages |
| `status` | Collection health as JSON |
| `probe` | Look at GSO's pages and list the data addresses they use |
| `trial [names] / --all` | Fetch and read GSO's live answers with the collectors; report what would be kept, write nothing |
| `export-static --out DIR` | Build the site the way GitHub Pages serves it |
| `backup` / `restore-portable` | Backups and restore |

## Adding a collector

1. Read what GSO's numbers mean from GSO's own page code (the probe log), never by guessing.
2. Write the collector in `gso_archive/adapters/` with tests on GSO's real answers in `tests/fixtures/real/`, including
   a part that is empty or `null`.
3. Add it to the registry but **not** to `GSO_ADAPTERS` (`config.py`, `archive.yml`) yet, and push. The probe job runs
   `trial --all`: every collector reads GSO's live answers and reports what it would keep, writing nothing. The step
   turns red if a collector would crash.
4. When the trial looks right, add it to `GSO_ADAPTERS`, after any collector it is dated by.

## Tests

```bash
python -m pytest                                                                   # everything, incl. browser checks
TEST_DATABASE_URL=postgresql://… python -m pytest --ignore=tests/test_frontend.py  # on PostgreSQL
```

See also: [deployment](DEPLOYMENT.md) · [backups](BACKUP_RESTORE.md) · [architecture](ARCHITECTURE.md)

## Watchdog (restarts collection if it stalls)

Collection runs as a chain (each `archive.yml` run starts the next) with GitHub's schedules as backup. Both failed
together for up to 4 hours in November 2026, so `.github/workflows/watchdog.yml` checks every 10 minutes and starts a
collection when none has started in the last 8 minutes (it does nothing while collection is healthy, and never fails).
GitHub's own schedule runs it too, but that is the part that fails, so it is also started from outside GitHub:

1. **A token that can only run this repository's workflows.** GitHub > Settings (your profile) > Developer settings >
   Personal access tokens > Fine-grained tokens > Generate new token. Name "gso watchdog", expiration up to 1 year,
   Repository access: *Only select repositories* > `gso-data-archive`, Permissions > Repository > **Actions: Read and
   write** (nothing else). Copy the token (it is shown once).
2. **A free scheduler.** At https://cron-job.org (free account) > Create cronjob:
   - URL: `https://api.github.com/repos/Darren38/gso-data-archive/actions/workflows/watchdog.yml/dispatches`
   - Schedule: every 10 minutes
   - Advanced > Request method: **POST**; Request body: `{"ref":"main"}`
   - Headers: `Authorization` = `Bearer <the token>`, `Accept` = `application/vnd.github+json`,
     `X-GitHub-Api-Version` = `2022-11-28`
   - Save, then "Test run": the answer should be **204** (no content). The repository's Actions tab then shows a
     "Watchdog" run within a minute.
3. **Renew the token before it expires** (GitHub emails a week before): generate a new one and paste it into the
   cronjob's Authorization header.

The token can only start this repository's workflows: if it leaked, someone could start extra collections, nothing
more. Revoke it on the same GitHub page to stop the outside scheduler at once.
