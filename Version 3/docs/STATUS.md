# Version 3 status: facts, assumptions, limitations, next steps

Status as of 28 October 2026.

## What changed from Version 2

* **More frequent collection.** Five GitHub schedules staggered one minute apart, with build and publish each run
  one at a time, keep runs going back to back: about every 2–3 minutes when GitHub keeps up (was 5+). The
  self-hosted worker defaults to every 2 minutes. The Auto label shows the interval measured from the run log.
* **Self-refreshing page.** An open page checks a small metadata file every minute. When any series has new
  readings, it builds the new page invisibly and swaps it in: no loading flash, same scroll position, settings kept.
  It waits while a control is in use and pauses while the tab is hidden.
* **View kept in the address** (`#/solar?range=30d&period=month` …).
* **Check-up once an hour** instead of after every run, so a broken source sends one email an hour, not one per run.

## Bugs found and fixed in this round

| Bug | Where | How it was found |
|---|---|---|
| Time labels ran together ("27 Oct12:0028 Oct") on narrow charts | Overview, every time chart at 320 px | Screenshots at 320 px |
| Pie slice labels cut off on phones | Generation | Screenshots at 320 px |
| A link naming an unknown series crashed the Explorer | Explorer | Code review, then a browser test |
| Choosing another primary solar series hid the generation-mix line | Solar | Code review |
| A future end date could be typed into the date box | All date pickers | Browser test |
| "All" on Demand started on the UTC day, not the Malaysian day | Demand | Code review |
| Phone menu stayed open after choosing a page | Navigation | Browser test |
| Theme switch and live refresh would have reset the chosen range | All pages | Fixed by keeping the view in the address |

## Test results

| Run | Result |
|---|---|
| Full suite on SQLite, incl. browser checks in Chromium | **88 passed** |
| Suite on PostgreSQL 16 (browser checks excluded; 8 SQLite-only tests skipped) | **76 passed, 8 skipped** |

The browser checks press every date button on five pages, type custom dates (including a future one), change the
solar series, overlay and comparison period, reload, switch theme, page through a table, download the CSV and the
Excel file, select series up to the limit of 12, open a link with an unknown series, click quickly between pages,
and use the phone menu (open, choose a page, Escape). A refresh scenario simulates new readings arriving: no loading
flash, notice shown, range and scroll position kept, the same number of charts, and no leftover hidden buffer.
Every main page is checked at 320–1920 px for sideways scrolling and for `NaN`/`undefined`/`Infinity`.
To prove the checks work, two features were broken on purpose (refresh scroll position, saving settings in the
address). The tests caught both, and the code was restored.

## Verified facts

* The development container cannot reach `www.gso.org.my`, so no GSO response has been observed first-hand.
* The Electricity Maps GSO parser documents the endpoints used here (see SOURCE_INVESTIGATION.md).
* A third-party project states that GSO's terms require TNB's written consent to download or store GSO data.

## Assumptions and limitations

* Everything about the GSO endpoints is still third-party documented. See SOURCE_INVESTIGATION.md §6 to verify with `probe`.
* GitHub's runners are in the US. If GSO blocks them, collection fails visibly (Status page, failed check-up) and the
  always-on worker in Malaysia/Singapore becomes the way to run it (DEPLOYMENT.md, Option B).
* GitHub runs schedules late or skips some under load, so the real interval varies (the Auto label shows it). This
  affects freshness, not completeness. GSO's own publishing interval is unknown; collecting more often than GSO
  publishes just finds nothing new.
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
