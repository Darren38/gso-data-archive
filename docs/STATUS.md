# Status: facts, limitations, next steps

Status as of 28 October 2026 (GSO Grid Archive 5.1).

## What is working

* **Live collection from gso.org.my** runs in GitHub Actions about every 2–3 minutes. Every data address used was
  seen working from GitHub's servers ([SOURCE_INVESTIGATION.md](SOURCE_INVESTIGATION.md)).
* **Datasets:** generation by fuel, system demand, three tie-lines, installed capacity; and from GSO's Solar page and
  home page: grid, distribution and rooftop solar, the solar forecast, BESS charge and discharge, other renewables,
  total generation, total tie-line flow, system availability, and about 60 solar farms.
* **Storage:** a SQLite archive carried between runs (Actions cache, then the copy on the live site, merged so
  nothing is lost), published with the site, and copied daily to the `archive-backups` release.
* **Site:** GitHub Pages, published after each run once Pages is switched on in the repository settings.

## Test results

| Run | Result |
|---|---|
| Full suite on SQLite, incl. browser checks | see the CI run on GitHub (all passing before release) |
| Collectors for GSO's Solar and home pages | tested on real answers saved on 28 October 2026 (`tests/fixtures/real/`) |

The real-answer tests check two things against GSO's own page: the five solar series' latest values add up to GSO's
"current MW" (3,939), and the forecast peak (3,616 MW) falls at 13:20, as GSO's page states.

## Limitations

* GSO's Solar and home page data is **today only**. If GitHub delays runs for a long time late in the evening, the
  last readings of that day can be missed. There is nothing to back-fill for those sources.
* GitHub sometimes runs schedules late or skips them, so the real interval varies (the Auto label shows it).
* NEM, FiT and SELCO rooftop values are GSO's estimates from registered capacity, not measurements.
* The forecast has no issue time from GSO; the archive uses the time it collected it.
* No system-constraints data exists on gso.org.my.
* Static (Pages) mode has no Excel export or revision viewer; those need the API deployment.

## Needs the owner

1. **Settings → Pages → Source: GitHub Actions**, so the site link works. The workflow skips publishing with a warning until then.
2. Optionally, read GSO's terms (`/TermsConditions.aspx`); collection is on at the owner's instruction.

## Next steps

1. Archive the home page's headline figures once their labels are read from the page (§6 of the investigation).
2. Decode the CBPE forecast page.
3. Measure how far back GSO keeps the date-based pages and run one `backfill` of everything available.
4. Add weather and irradiance context, and capacity factors per solar farm (live MW ÷ capacity over time).
