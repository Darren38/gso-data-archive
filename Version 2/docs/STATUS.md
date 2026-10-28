# Version 2 status: facts, assumptions, limitations, next steps

Status as of 28 October 2026.

## What changed from Version 1

The owner's other repositories (Tech Comparison Hub, EPF Goal Planner, Physics Fruit Rush) were read to settle the
questions Version 1 left open:

| Version 1 left open | Settled by the owner's style |
|---|---|
| Which server or database to use | None: GitHub Actions + Pages. The archive is carried between runs like Tech Comparison Hub's `seed_live.py` |
| Backups off-site | A daily GitHub Release copy (plus the optional S3 copy) |
| Knowing when it breaks | A health check after every deploy (a failed run emails the owner) and a keepalive job |
| README / commit style | The owner's README layout, CHANGELOG, MIT licence, `CLAUDE.md`. Commits by Darren38 only |
| Stale pages after an update | `sw.js`, the same as EPF Goal Planner |

## Test results

| Run | Result |
|---|---|
| Full suite on SQLite, incl. 4 browser checks (Chromium) | **87 passed** |
| Suite on PostgreSQL 16 (browser checks excluded; 8 SQLite-only tests skipped) | **75 passed, 8 skipped** |
| Version 1 suite, unchanged | 76 passed (browser checks excluded) |

New in Version 2: tests for merging two archive copies (union, repeatable, newer correction wins), carrying the archive
over from a published site, the snapshot file, and the site check-up. The browser checks now cover every main page
at 320–1920 px for sideways scrolling and `NaN`/`undefined`/`Infinity`. That check found a real bug: the Solar page
was 31 px too wide at 320 px. It is now fixed.

## Rehearsed end to end (in the development container)

The workflow's steps were run by hand three times against the fixture server, with a local web server standing in
for GitHub Pages:

1. **First run:** no cache and no published copy, so the archive started fresh. 6 successful runs, 1,008 readings, site published with the archive file.
2. **Normal run:** archive restored from the "cache". The live copy merge was correctly skipped (nothing new). Today was deduplicated (0 new) and back-fill continued: 1,344 readings.
3. **Cache lost:** the archive was recovered from the published site and kept growing: 1,680 readings, nothing lost.

The site check-up passed against the published copy.

Not run here: the GitHub workflow itself (it first runs once merged to `main`). The cache, Release and Pages steps use
the same official actions and `gh` commands as the owner's Tech Comparison Hub.

## Verified facts

* The development container cannot reach `www.gso.org.my`, so no GSO response has been observed first-hand.
* The Electricity Maps GSO parser documents the endpoints used here (see SOURCE_INVESTIGATION.md).
* A third-party project states that GSO's terms require TNB's written consent to download or store GSO data.

## Assumptions and limitations

* Everything about the GSO endpoints is still third-party documented. See SOURCE_INVESTIGATION.md §6 to verify with `probe`.
* GitHub's runners are in the US. If GSO blocks them, collection fails visibly (Status page, failed check-up) and the
  always-on worker in Malaysia/Singapore becomes the way to run it (DEPLOYMENT.md, Option B).
* GitHub runs 5-minute schedules late or skips some under load. This affects freshness, not completeness.
* The GitHub-only mode does not keep raw responses.
* The whole archive is published on the site as a download. If GSO's terms restrict redistribution, set
  `export-static --no-archive` in `archive.yml` and rely on the cache and Release copies.
* BESS, system constraints, the solar transmission/distribution split and solar forecasts: no verified source yet.

## Needs the owner

1. Read GSO's terms. Ask for consent if needed. Then set the `GSO_LIVE_ENABLED` variable to `true`.
2. Merge into `main` and set **Settings → Pages → Source: GitHub Actions** so the site link works.

## Recommended next phase

1. Run `probe` from a Malaysian network, mark the adapters verified, and add real fixtures.
2. Map the Solar Profile page's fields (transmission/distribution/forecast) once confirmed.
3. Once real data flows: measure how far back GSO keeps history and run one `backfill` of everything available.
4. Add weather/irradiance context and a capacity-factor view using the installed-capacity snapshots.
