# Changelog

## 28 October 2026 (third update) — Version 3

New readings more often, and a page that keeps itself up to date.

- Collection now runs about every 2–3 minutes instead of every 5 or more: five GitHub schedules a minute apart keep runs going back to back. On your own server the default is every 2 minutes. The **Auto** label shows the interval measured from recent runs.
- An open page checks for new readings every minute and redraws in place, with a short "New readings loaded" notice. It never flashes or jumps, keeps your dates and settings, and waits while you're using a control.
- The view you choose (dates, solar series, demand overlay, comparison period, Explorer series) is kept in the page address, so it survives a reload or a theme switch and can be shared as a link.
- The site check-up runs once an hour, so a broken source means one email an hour, not one per run.
- Fixed: chart time labels running together on phones; the energy-share chart's labels cut off on phones; the Explorer crashing on a link with an unknown series; the generation-mix solar line disappearing when another solar series was chosen; future end dates being accepted; Demand's "All" range starting on the wrong day for Malaysian time; the phone menu staying open after choosing a page.
- The browser tests now click through everything a visitor can do. 88 tests pass.

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
