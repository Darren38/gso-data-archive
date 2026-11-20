# Maintenance check-up

The owner asks for a check-up from time to time: "is the site still showing reliable results?" Work through this
list, fix what is wrong (CLAUDE.md lessons first), and end with the improvements that need the owner's decision.

## 1. Is collection running?

- Latest runs of `archive.yml`: build, deploy and check green? Any gap of more than ~10 minutes between runs
  (the `next` job failing, GitHub skipping schedules)? List them from the backup's `collection_runs` (gaps of more than
  12 minutes between `system_demand` runs) and, for each, look at the run just before it on GitHub: "queued" for hours
  or "startup_failure" means GitHub never started it (lesson 61). Count readings per source and day too: 144 a day
  for the 10-minute sources, 48 for the tie-lines and CBPE, 142 for the home page lists (no 23:40 and 23:50).
- The hourly check's notes: last collection age, collectors failing in a row and why (GSO timeouts are notes for
  12 hours; anything else is a bug here), series without new readings.

## 2. Are the numbers right? (lesson 31: check numbers, not just pages)

Once the backups are locked (`ARCHIVE_PASSPHRASE`, docs/BACKUP_RESTORE.md) a session can't open them: read the
newest `backup` job's "Check-up figures" step instead (readings per source and MYT day, collection stops), and ask
the owner to restore a backup for anything deeper. Never ask for the passphrase in chat. While they are unlocked,
download the newest `archive-backups` asset (github.com release downloads work from a session) and restore it:
`gso-archive restore-portable <folder>` into an empty SQLite file. Then:

- **Readings per day per series** for the last few days: 144 for 10-minute series (fewer today). Missing times in a
  row, or a day with too many, point at a filing bug (lessons 11, 24, 32).
- **A day compared with the next:** identical values on two days mean a list was filed under the wrong day.
- **Cross-checks** on the Status page: both "passed" in daylight (lesson 34).
- **Sums:** Distribution Solar = LSS+NEM+FiT+SELCO; the Other RE split = its total (lesson 38); Current Solar =
  the Solar page's five parts; Current BESS = discharge + charge; Current Grid Demand = the home page's Grid Demand
  line (the System Demand page's figure is 0-60 MW higher: a different figure); home tie-line total = minus
  (EGAT + HVDC + PLTG). Any figure the site says is "the same" as another must match here (lesson 47).
- **Midnight:** the home page list misses 23:40 and 23:50 every night (GSO publishes them after its page has
  moved to the new day). The charts join that gap; anything longer is new.
- **Stalls:** count readings per hour for the home page and System Demand page; hours with none while the
  Generation page has readings are a GSO stall (lesson 48). Check which moments are marked "frozen" and that each
  really repeats stalled figures. A mark is lifted when GSO later fills the gap (4 Nov 00:00 was, the same morning).
- **LSS farms:** on the Solar page's "LSS Farms: Any Moment or Period" card, look at a sunny noon of the week and at a
  period's capacity factor (Nov 2026: about 15% for the fleet). Farms marked "GSO figures look wrong" (PTRM, SKCL in
  Nov 2026) should be the only ones; a new one is worth a look at its readings before sunrise and after sunset.
- **Measured sunshine:** the Status page's `irradiance` collector ran within the last 2 hours; the probe's
  `irradiance-trial` shows the newest hour about 1 hour behind. If Open-Meteo's Himawari feed breaks (it did from
  6 Jan to 4 Mar 2026), the Weather page falls back to the forecast; nothing else depends on it.
- **Weather:** the Status page's `weather` collector ran within the last 3 hours (a few "429 Too Many Requests"
  failures are normal: Open-Meteo's free limits are per address and GitHub's machines share addresses), and the Weather page's sunshine
  follows the farms' output on clear days. It is Open-Meteo's, never GSO's: it must never stop GSO collection.
- **Constraints:** the Constraints page's two lists were read within the last hour and match GSO's home page
  (same number of rows); the trial's `constraints` result is "ok" with GSO's column headings unchanged.
- **Negative values:** Tie-Line (power coming in) and Co-Gen can be below zero; they must not draw spikes.

- **Storage (GitHub's limits):** the published site must stay under GitHub Pages' 1 GB limit. The build log's
  "Final size is N bytes" (upload-pages-artifact) is the compressed size; the site itself was 46 MB on 16 Nov 2026
  and grew about 1.5-2 MB a day (monthly CSVs about half of it, the whole-archive download a third). Plan a change
  (e.g. stop publishing monthly CSVs, or publish the full archive file only in the backups) before it passes 700 MB.
  The Actions cache allows 10 GB per repository; the daily backups are separate release files. The site records
  its own size (meta.json `site_bytes`) and the hourly check emails from 700 MB (lesson 66): read the size from
  the check's notes.

## 3. Do the pages show it right?

- `python -m pytest` (includes the browser checks at every width).
- Build the static site from the restored backup (`export-static`) and look at the Overview, Solar, Demand and
  Generation pages at 320 px and 1440 px. Hover a few moments and compare the tooltip with the backup.
- The Overview still follows GSO's home page: the probe log's "sections in LandingPage.aspx.html" list.

## 4. Has GSO changed anything?

- The probe job (every push and daily at 19:43 UTC): the trial must report no "COLLECTOR BUG"; "could not fetch"
  is GSO being slow. Compare GSO's scripts in the log with docs/SOURCE_INVESTIGATION.md when a number looks odd
  (lessons 9, 27).

## 5. Report

A new problem found in GSO's own figures also goes on the About page's "Known problems in GSO's data" list
(web/js/pages/about.js), in plain words with what the site does about it.

### What to report

Plain words: what was checked, what was found and fixed (with the version), what still waits on GSO, and the
improvements that need the owner's decision.
