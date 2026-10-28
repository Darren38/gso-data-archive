# Backup and restore

Permanent retention must not depend on one database or one copy. Version 1 provides three
independent layers:

| Layer | What | Where it should live |
|---|---|---|
| 1. Primary database | PostgreSQL (managed with point-in-time recovery, or the Compose volume) | Provider / VM disk |
| 2. Native backup | `pg_dump --format=custom` (or a SQLite online backup) + `.sha256` | Off-site object storage |
| 3. Portable backup | One gzip CSV per table + `manifest.json` (row counts, SHA-256). Restorable into PostgreSQL **or** SQLite | Off-site object storage, a second provider or region |

Raw source responses (`RAW_STORE_DIR`) are a fourth, independent record. Sync them off-site too.

## Taking backups

```bash
python -m gso_archive backup --format both --out ./backups     # native + portable
python -m gso_archive backup --format portable --out ./backups
```

* Docker Compose: the `backup` service runs daily into `./backups`.
* GitHub Actions: `backup.yml` runs daily and copies to `BACKUP_S3_URI` when that secret is configured.
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

### SQLite native backup

Copy the `.sqlite3` backup file into place and point `DATABASE_URL` at it.

## Verified

These were run in the development environment (see STATUS.md):

* portable backup → restore into new SQLite: all table counts and revised values match (automated test);
* portable backup on PostgreSQL 16 → restore into a fresh PostgreSQL DB: counts match, and new inserts continue at the correct id;
* `pg_dump` → `pg_restore` on PostgreSQL 16: 288 observations and 289 revision rows restored;
* tampered manifest checksum → restore refused (automated test).

**Test a restore regularly** (e.g. monthly) into a scratch database. A backup that has never been restored has not been verified.
