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
