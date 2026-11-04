# Maintenance check-up

The owner asks for a check-up from time to time: "is the site still showing reliable results?" Work through this
list, fix what is wrong (CLAUDE.md lessons first), and end with the improvements that need the owner's decision.

## 1. Is collection running?

- Latest runs of `archive.yml`: build, deploy and check green? Any gap of more than ~10 minutes between runs
  (the `next` job failing, GitHub skipping schedules)?
- The hourly check's notes: last collection age, collectors failing in a row and why (GSO timeouts are notes for
  12 hours; anything else is a bug here), series without new readings.

## 2. Are the numbers right? (lesson 31: check numbers, not just pages)

Download the newest `archive-backups` asset (github.com release downloads work from a session) and restore it:
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
  really repeats stalled figures.
- **Negative values:** Tie-Line (power coming in) and Co-Gen can be below zero; they must not draw spikes.

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

Plain words: what was checked, what was found and fixed (with the version), what still waits on GSO, and the
improvements that need the owner's decision.
