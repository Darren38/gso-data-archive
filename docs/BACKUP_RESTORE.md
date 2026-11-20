# Backup and restore

Permanent retention must not depend on one database or one copy. The archive is kept in
several independent places:

| Layer | What | Where it should live |
|---|---|---|
| 1. Primary copy | GitHub-only: the SQLite archive in the Actions cache (newest 3 kept). Worker: PostgreSQL | GitHub / VM disk |
| 1b. Published copy | `data/archive.sqlite3.gz` on the live site (GitHub-only mode); `archive.sqlite3.gz.enc` when locked | GitHub Pages |
| 1c. Daily Release copy | Portable backup `gso-archive-YYYY-MM-DD.tar.gz` in the `archive-backups` release: 14 days + the 1st of every month | GitHub Releases (outside git history) |
| 2. Native backup | `pg_dump --format=custom` (or a SQLite online backup) + `.sha256` | Off-site object storage |
| 3. Portable backup | One gzip CSV per table + `manifest.json` (row counts, SHA-256). Restorable into PostgreSQL **or** SQLite | Off-site object storage, a second provider or region |

Raw source responses (`RAW_STORE_DIR`) are a fourth, independent record. Sync them off-site too.

## Locking the copies (owner only)

The repository is public, so the published copy and the release backups can be downloaded by anyone unless they are
locked. Add the repository secret `ARCHIVE_PASSPHRASE` (Settings > Secrets and variables > Actions > New repository
secret) and from the next run:

* the site publishes only `data/archive.sqlite3.gz.enc` (the About page then offers no download), and the next run
  reads it back with the same secret;
* the daily backup is `gso-archive-YYYY-MM-DD.tar.gz.enc`, and the unlocked backups are deleted from the release once
  the first locked one is uploaded (each backup holds the whole archive);
* the daily backup job's log prints the check-up figures (readings per source and day, collection stops), so a
  check-up can be done without opening the backup.

The same passphrase also limits the public website to the newest 7 days: older history is published only in
locked files (`*.json.enc`) and opens in the browser with the passphrase (🔒 Full history beside the dates).

Open a locked file with OpenSSL (it asks for the passphrase), then restore as below:

```bash
openssl enc -d -aes-256-cbc -pbkdf2 -iter 600000 -in gso-archive-YYYY-MM-DD.tar.gz.enc -out gso-archive.tar.gz
```

Keep the passphrase in a password manager: **a lost passphrase can't be recovered**, and the locked copies are then
unreadable (the Actions cache copy still works without it). Changing it later is safe: the next run publishes copies
locked with the new one, and older locked backups still need the old one.

## Taking backups

```bash
python -m gso_archive backup --format both --out ./backups     # native + portable
python -m gso_archive backup --format portable --out ./backups
```

* Docker Compose: the `backup` service runs daily into `./backups`.
* GitHub Actions: the `backup` job of `archive.yml` runs daily at 03:43 MYT, uploads to the `archive-backups` release, and also copies to `BACKUP_S3_URI` when that secret is configured.
* Each backup is recorded in `system_state.last_backup` and shown on the Collection Status page.
* Off-site sync example (Cloudflare R2 via rclone): `rclone copy ./backups r2:gso-archive/backups` and `rclone copy ./data/raw r2:gso-archive/raw`.
* Retention suggestion: daily for 30 days, monthly forever. The data is small.
* `pg_dump` must be the same major version as the server or newer. The portable format has no such constraint.

## Restoring

### Native PostgreSQL dump

```bash
sha256sum -c gso-archive-YYYYMMDDTHHMMSSZ.dump.sha256
createdb gso_archive_restored
pg_restore --no-owner -d postgresql://…/gso_archive_restored gso-archive-YYYYMMDDTHHMMSSZ.dump
DATABASE_URL=postgresql://…/gso_archive_restored python -m gso_archive migrate   # applies any newer migrations
```

### Portable backup (any database, including PostgreSQL ↔ SQLite migration)

```bash
DATABASE_URL=postgresql://…/empty_db python -m gso_archive restore-portable backups/gso-archive-portable-YYYYMMDDTHHMMSSZ
```

The restore checks every file's SHA-256 against the manifest **before** writing anything, refuses
a non-empty target, checks row counts per table, and resets PostgreSQL id sequences.

### GitHub-only archive

Any of these works:

* Download `gso-archive-YYYY-MM-DD.tar.gz` from the `archive-backups` release, unpack it, then run
  `DATABASE_URL=sqlite:///$PWD/archive.sqlite3 python -m gso_archive restore-portable gso-archive-portable-…`.
* Or download `https://darren38.github.io/gso-data-archive/data/archive.sqlite3.gz` and `gunzip` it.
* To put a restored archive back into service, publish it once: the next workflow run merges the live copy in.
  Or merge any copy into another with `python -m gso_archive merge sqlite:///path/to/other.sqlite3`.

### SQLite native backup

Copy the `.sqlite3` backup file into place and point `DATABASE_URL` at it.

## Verified

These were run in the development environment (see STATUS.md):

* portable backup → restore into new SQLite: all table counts and revised values match (automated test);
* portable backup on PostgreSQL 16 → restore into a fresh PostgreSQL DB: counts match, and new inserts continue at the correct id;
* `pg_dump` → `pg_restore` on PostgreSQL 16: 288 observations and 289 revision rows restored;
* tampered manifest checksum → restore refused (automated test).

**Test a restore regularly** (e.g. monthly) into a scratch database. A backup that has never been restored has not been verified.
