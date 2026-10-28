# Changelog

## 28 October 2026 (second update) — Version 2

Runs completely on GitHub, the same way as Tech Comparison Hub.

- No server or database service needed any more. One GitHub Actions workflow collects new readings about every 5 minutes, builds the site and publishes it to GitHub Pages. The archive is a single file that each run picks up from the previous one (Actions cache) and from the live site, in case the cache was cleared. The two copies are merged, never swapped, so nothing can be rolled back.
- A copy of the whole archive goes to the `archive-backups` GitHub Release every day (the last 14 days, plus the 1st of every month kept for good). The site also offers the whole archive as one download.
- After every update a check-up reads the live site and fails the run (GitHub then emails the owner) if the page doesn't load or collection has stopped. The daily run keeps the schedule switched on, because GitHub pauses schedules after 60 days without a push.
- Every action in the workflows is pinned to an exact commit, and the job that collects data holds no GitHub token.
- "Auto" labels say how often the data updates, and every visit loads the newest version of the site (`sw.js`).
- Requests to GSO name the project, not a person.
- Fixed: on a 320 px phone the Solar page's date buttons and series menu stuck out sideways by 31 px. Chart axis titles overlapped the legend.
- Tests now also check every main page at widths from 320 to 1920 px for sideways scrolling and for "NaN" or "undefined" on screen. 87 tests pass.

## 28 October 2026 (first update) — Version 1

First release.

- Collector for GSO's public data: generation by fuel (including solar), system demand, tie-lines to Thailand and Singapore, and installed capacity. A Solar Profile page reader is included but stays off until its address is confirmed.
- The archive keeps every reading and every later correction, never shows a missing reading as zero, and flags odd values instead of changing them.
- Dashboard with Overview, Solar, Demand, Generation, BESS, Tie-line, Constraints, Historical Explorer, Collection Status and About pages, plus CSV and Excel downloads.
- Backups that restore into SQLite or PostgreSQL. 80 tests.
