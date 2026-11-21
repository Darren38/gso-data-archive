# Notes for working on this project

An archive and dashboard for the Malaysian Grid System Operator's (GSO) public data. The code is at the top level
of the repository. One GitHub Actions workflow (`.github/workflows/archive.yml`) collects data about every 2–3 minutes and
publishes the site to GitHub Pages: https://darren38.github.io/gso-data-archive/

## How the owner likes changes made

- When a choice isn't settled here, look at how the owner's other repositories do it before asking:
  Tech Comparison Hub (automatic updates on GitHub Actions, `seed_live.py`, health check, keepalive, pinned actions),
  EPF Goal Planner (`CLAUDE.md`, `sw.js`, README style) and Physics Fruit Rush (version numbers, CHANGELOG).
- In the owner's other projects changes are committed straight to `main` with no pull requests.
- Commits are authored by Darren38 only, with no co-author or session lines, so Darren38 stays the only contributor.
- Commit messages, the README and the CHANGELOG are written in plain, friendly words for people who are not developers.
- Email the owner only for critical problems (20 Nov 2026), through the hourly check (lesson 67). Never add a
  job that fails a run for anything else.
- Keep the owner updated while working: short progress notes with a text progress bar (e.g. `▓▓▓▓▓░░░░░ 50% · step 3 of 6`).
- **The owner's rule for this website (20 Nov 2026): it must fetch every new piece of GSO data automatically, store
  all of it from time to time (nothing GSO publishes may be lost), load it properly and display it correctly, and the
  website must be kept fast. On top of that it must sustain itself: keep running for months with nobody looking
  after it (collection restarts itself, storage stays inside GitHub's limits with an alarm well before, packages
  can't jump to a breaking new version, and anything only a person can do sends an email in time).**
  Every change is judged against this first.
- The owner's first rule: the site must keep collecting by itself whenever GSO publishes. Any change to `archive.yml`
  (above all the `next` job) must pass `tests/test_workflow_next.py`, and after pushing, watch several runs on GitHub
  follow each other every 2-3 minutes before calling it done.
- From time to time the owner asks for a maintenance check-up: follow docs/MAINTENANCE.md.
- After every check, end with the possible improvements to the current version that need the owner's decision
  (what each would do, its cost or risk, and a recommendation), even when everything passed.
- READMEs follow the owner's format: centred title, bold one-line description, green "OPEN THE SITE" badge, a clickable
  screenshot, then "What it is", "How current is it?", "Open it" (the site is online only: no install or local-run
  steps in the README; developer instructions live in docs/DEVELOPMENT.md), and credits.
- GitHub only: Actions and Pages, no paid server or database service. One exception the owner approved (20 Nov 2026):
  a free outside scheduler (cron-job.org) starts `watchdog.yml` every 10 minutes with a token limited to this
  repository's Actions (docs/DEVELOPMENT.md, "Watchdog"). Don't commit the archive database or raw data
  to git: the archive lives in the Actions cache, the published site and the `archive-backups` release.
- History lock: on 20 Nov 2026 the owner had the full history locked (public: newest 7 days, lesson 63) and the same
  day asked for the password to be removed. It is switched OFF by not passing `ARCHIVE_PASSPHRASE` to the jobs in
  `archive.yml` (the line is left there as a comment); the code stays, and everything is public again. Switch it back
  on only if the owner asks. Never ask for a passphrase in chat or write a real one into the repository.
- No `Version N/` folders on `main` (the owner asked for them to be hidden). Like Physics Fruit Rush, a substantial
  update gets a new version number (`gso_archive/__init__.py`, the commit message "GSO Grid Archive N.0 - …" and a
  CHANGELOG entry). Versions 1–3 are preserved as they were on the `versions` branch; never change or delete it.
- Requests to other sites name the project, never the owner (no name or email in the User-Agent).
- Never invent readings, endpoints or source capabilities. Demonstration data is watermarked and labelled everywhere.
- The Overview follows GSO's home page: its seven headline boxes in GSO's order, then the generation chart ("System
  Demand Profile for Peninsular Malaysia"), then Generation Availability, then Generation Mix (GSO's order, from the
  probe's "sections in LandingPage.aspx.html" list, 31 Oct 2026). The Generation Mix ring follows DrawGenMixPieChart
  (`mixRing` in charts.js, `MIX`/`BREAKDOWN` in overview.js): GSO's slice order and rules, and an outer ring opened by
  tapping Distribution Solar (LSS/NEM/FiT/SELCO) or Other RE (Biogas/Biomass/Mini Hydro). One deliberate difference:
  without the split GSO drops the Other RE slice; ours keeps it. GSO's solar profile and map stay on Solar.
  Solar detail belongs on the Solar page, demand comparisons on the Demand page.
- Where GSO has the same chart (for example its System Demand Profile), draw ours the way GSO draws it: same
  stacking order, colours and key order. Charts this site works out itself (comparisons, profiles, ramps) stay as they are.

## Search engines (the same way as Tech Comparison Hub and EPF Goal Planner)

- `web/index.html` carries a description (under 160 characters), the canonical address, share-preview tags and a
  schema.org summary. Keep them true when the site changes.
- `web/sitemap.xml` lists the site (its pages are `#/` views of one page, so there is one address). A `robots.txt`
  here would never be read: only one at darren38.github.io itself counts.
- IndexNow (Bing, Yandex and others): the `indexnow` job in `archive.yml` runs `scripts/indexnow.py submit` only after
  a push has been published, never on the every-few-minutes data runs. It waits until the new page is live, then sends
  the address. The key in `web/indexnow.txt` is public by design. Never let it fail a run.

## Lessons from bugs found here

1. **A row of buttons that doesn't wrap widens the whole page on a 320 px phone.** The Solar page's seven date buttons
   pushed it 31 px sideways. Give button groups `flex-wrap: wrap; max-width: 100%`, and toolbar children `min-width: 0`.
2. **Chart axis titles sit just under the top of the plot, where the legend is.** With two y-axes the titles overlapped
   a long legend. Keep `grid.top` at about 52 px and the legend inset from both sides.
3. **A service worker makes its own requests, so Playwright's `page.route()` can't fake them.** Browser tests that fake
   API failures or slow responses must open their context with `serviceWorkers: "block"`.
4. **`pkill -f <pattern>` can kill the shell that runs it** when the pattern appears in its own command line. Stop
   test servers by PID.
5. **GitHub Pages caches files for about ten minutes.** That's why `sw.js` exists, and why the archive is carried
   over from the Actions cache first and the live site second (the live copy can be a few minutes old).

6. **Time-axis labels run together when a chart is narrow** (a 320 px phone with two y-axes leaves ~140 px of plot).
   `timeChart` uses fewer ticks and smaller labels under 400–520 px. Pie slice labels are hidden under 480 px.
7. **A page that redraws itself must not lose the visitor's place.** Live refresh builds the page in a hidden buffer
   and swaps it in. Every setting a visitor can change lives in the address (`getParam`/`setParams` in `ui.js`), and a
   page's `render` must `await picker.start()` so the swap happens only when the page is complete.
8. **Values from links can't be trusted.** The Explorer ignores unknown series keys in `?series=`.
9. **Don't guess what a GSO number means; read GSO's own script.** The Solar page's data is "$"-joined text whose
   parts are only labelled inside `Scripts/Solar.v19.js` and `Scripts/SolarLandingPage.v5.js`. `gso-archive probe`
   (run on GitHub, where gso.org.my is reachable) prints those scripts' parsing code. The guessed address
   `Solar.aspx/GetChartDataSource` answered 401.
10. **GSO answers 406 to a JSON/HTML-only `Accept` header for `.js` files.** Script downloads send `Accept: */*`.
11. **Today-only answers need a date check around midnight.** `_pick_day` treats a list longer than today could
    have as yesterday's, and the forecast is skipped between 23:30 and 00:30 rather than guessing its day.
12. **Series created by a transform must be found by key.** `resolve_series` looks up the source label and then the
    series key; before that, every Solar-page series was named "(auto-discovered)".
13. **A scrolling chart legend hides names behind "1/6" arrows on phones.** `legendFor` in `charts.js` wraps the legend
    and moves the plot down to make room; it keeps scrolling only for very long lists (e.g. one line per day).
14. **Phone rules in a media query override earlier container-query rules of equal weight.** The narrow-card
    `@container` rules for `.kpi` sit at the very end of `app.css`; their widths are the card's inner width.
15. **GSO's chart data comes from two pages with different times.** A snapshot (the Generation Mix donut) must use one
    timestamp where every series has a reading (`latestCommon` in `overview.js`), never each series' own latest value.
16. **Test with real-shaped data, not only the demo.** A stand-in GSO that serves `tests/fixtures/real/` for the
    today-only pages, then `collect`, `backfill` and `export-static`, gives the same static site Pages serves.
17. **A stacked chart counts a missing lower reading as zero** and draws every layer above it too low: a fake dip.
    `alignStack` in `analysis.js` puts sources on GSO's 10-minute steps and gaps a moment for every layer when any
    source has no reading there. Sources that come from different GSO pages (Generation Mix and the home page) never
    share exact timestamps, so they must always go through it before stacking.

### Lessons from EPF Goal Planner (the owner's other site), worth checking here too

18. **The `hidden` attribute loses to a class that sets `display`.** Keep `[hidden]{display:none !important}` (present).
19. **Hover-only interactions do nothing on a phone.** Anything that shows detail on hover must also work by tap.
20. **A floating bar at the bottom of a phone screen covers whatever scrolls to the bottom.** Give the page
    `scroll-padding-bottom` and end padding the bar's height. (Today's toast is fine: it is brief and lets taps through.)
21. **A dialog's Escape key must be heard on the whole page**, not only inside it (present for the menu).
22. **Grid and flex children with text that never wraps widen the page.** Give them `min-width:0`, and write
    `minmax(min(330px,100%),1fr)` rather than a bare `minmax(330px,1fr)`.
23. **Saved settings can be old or damaged**, like values from links (lesson 8): accept only known choices.
24. **GSO's "last available" time is in the future before sunrise** (07:00 of the coming morning). Date readings with
    `_reading_time` (never later than the real clock), decide the forecast's day by the clock, and `apply_readings`
    refuses anything dated more than 15 minutes after collection. Real midnight answers: `tests/fixtures/real/*night*`,
    `*after_midnight*`. Migration 2 removed the readings this had misdated.
25. **A summary card must describe the same thing as the chart next to it.** The Solar page's cards follow the chosen
    series ("All solar" by default, the same total as the Solar Profile chart) and name it when it is a single kind.
26. **"Today" is never a full day.** Completeness and "expected readings" for today count only the time so far
    (`analytics.daily`, `dailyFromPoints` in `analysis.js`).
27. **Check a surprise against GSO's raw answers before calling it a bug.** The new day's forecast looked like a copy of
    yesterday's; the probe (`archive.yml` with `probe: true`) showed GSO really had published a new one.
28. **Every GitHub Pages deployment needs its own build version.** `actions/deploy-pages` sends the commit as
    `pages_build_version` and checks the deployment with that id, so republishing the same commit every few minutes made
    hundreds of deployments share one identity: GitHub served an old copy and the step said "success" in seconds.
    GitHub only accepts a commit as the version (other text: 404), so `scripts/deploy_pages.py` makes a commit object
    per run (same tree, parent = the real commit, on no branch: not in history or contributors), publishes under it and
    waits for that deployment. A same-version republish shows "succeed" with no queued/syncing steps: that's the tell.
    The hourly live-site check ("last collection N min ago") is what showed it.
29. **Daily energy must keep the slice across midnight.** Integrating each day's readings on their own drops 23:50→00:00
    (about 1% of a day). `_daily_energy` (analytics.py) and `dailyFromPoints` (analysis.js) split that slice at midnight.
30. **A geo component's `tooltip: {show: false}` also hides the tooltips of series drawn on it.** Use `silent: true` on
    the geo instead. The browser check asks the solar map for a farm's tooltip.
31. **Check numbers, not just pages.** Recompute the headline figures from the archive and GSO's own totals (e.g. the
    Solar page's "currentMW") and compare with what the pages show; a page can render cleanly and still be wrong.
32. **GSO's "last available" time stops moving after sunset, but the Solar page's list keeps growing.** Judged by that
    time, every evening list looked too long for today and was filed under yesterday (the archive's "27 Oct" was a copy
    of the 28th). `_solar_actual` picks the day by the real clock (`ctx["now"]`); migration 4 refiled the old readings.
    Look for this by counting readings per day and comparing a day's values with the next day's.
33. **A derived accuracy figure must leave out moments that test nothing.** "Forecast vs Actual" counted night (both
    zero) and showed a typical miss of 48 MW; in daylight it was 115 MW. `forecastError` skips both-zero moments.
    The browser's own sums are checked in `tests/frontend/check_analysis.mjs`.
34. **Unlabelled "$" lists need an alarm, not just a parser.** GSO publishes two figures twice (Distribution Solar on
    the home and Solar pages, always exactly equal; Grid solar on the Solar and Generation pages). `crosscheck.py`
    compares them every run (daylight only); the Status page shows the result and the health check fails if they
    disagree. A swap of NEM and SELCO would pass both (their sum is unchanged), so `_order_by_labels` (gso_live.py)
    reads GSO's one labelled part, r[7] (the Distribution Solar pie: "LSS", "NEM", "FiT", "SELCO" with the newest
    figures), and files the lists by those names. It never stops collection: after sunset the labels may refer to
    an earlier reading (it searches back for the matching moment), and labels that match nothing only leave a note.
35. **GSO revises its Solar page's figures; its Generation page doesn't follow.** On 29 October the Solar page re-sent
    the morning's Grid values up to 7 times in the afternoon (up to 8.5% lower) while the Generation page kept its own,
    so the Grid cross-check allows 15% or 15 MW. A check that is exact on one day's backup can fail on the next: try
    any new alarm on several days of real backups before it can email the owner.
36. **Visitors may use this site instead of GSO's.** Old figures must never pass for current ones: past 45 minutes
    every page shows a "Readings are delayed" note (`setBanner` in `app.js`), and the health check fails if the
    newest reading is 3 hours old while collection runs. Readings normally arrive 15-25 minutes after their time.
37. **Tests that run the collector must pin the clock** (`at_fixture_time` in `test_gso_live.py`): the collector uses
    the real time to pick the day and skips the forecast between 23:30 and 00:30.
38. **Data GSO sends without a time is dated by a figure that has one, or not kept.** The other renewables split
    (`other_re`) has no time; its total equals the home page's newest "Other RE" reading, which `genmix_live` shares
    through `ctx["shared"]` (cleared every cycle), so `other_re` must run after `genmix_live`. If the totals differ,
    nothing is kept. Lists of rows with text (GSO's power stations) go through `store.keep_table`, which records every
    change GSO makes and keeps stations GSO stops listing.
39. **Pages pick their series by key, never by "the first of a category".** Adding the home page headline figures
    (category "demand" at first) would have made the Demand page chart "headlines.current_bess", because it took the
    first demand series and keys sort alphabetically. New collectors get their own category ("headline"), and
    `demand.js` now asks for `system_demand.demand` by name.
40. **One collector's bug must never stop the others.** On its first live run the new `cbpe` collector met a part GSO
    sent as a bare `null`, raised a TypeError, and the whole collection cycle stopped: the collectors after it
    (availability, solar farms) didn't run. `collect_one` now records any unexpected error while reading an answer
    as that collector's failure, and `run_cycle` guards each collector. Real answers can be `null` where a list is
    expected: test new parsers with that too, and try a new collector with `trial` on GitHub before adding it to
    GSO_ADAPTERS (docs/DEVELOPMENT.md, "Adding a collector").
41. **One slow GSO address must not slow everything else.** On 30 October GSO's home page headline figures timed out
    for hours: 30 s a try and 4 tries made every round take 4 minutes instead of 30 seconds, so all other figures
    arrived less often. After `BACKOFF_AFTER` failures in a row a collector is tried only every `BACKOFF_SECONDS`
    (`plan_cycle`) and with no retries (`collect_one`) until it succeeds again; that one try may wait
    `BACKOFF_TIMEOUT` (60 s), since GSO is often slow rather than down. The trial uses one try per address.
42. **An alarm must point at something the owner can fix.** That evening the Solar page, the headline figures and CBPE
    all timed out on GSO's side, and the hourly check emailed "failed" every hour. `health.py` now treats timeouts,
    lost connections and GSO's 5xx answers as a note until the collector has had no success for 12 hours; any other
    error (a changed answer, a 4xx) still fails after 12 in a row. Separately, a source with nothing new for 6 hours
    of daytime (07:00-19:00 MYT, `silent_sources`) fails the check once, then once a day (each further 12 daytime
    hours) was emailed once a day until 20 Nov 2026; now it is only listed (lesson 67: only critical problems email). Visitors see the delay through freshness and the
    "Readings are delayed" note. The same day GitHub answered 502 to the `next` job's `gh workflow run` and collection
    stopped for 80 minutes, so that step now tries again before giving up. The probe also tries each address once
    (`run_probe`): with four tries it ran out of its 10 minutes on a slow night and printed nothing.

43. **A stacked layer that goes below zero draws spikes, and the home page misses 23:40 and 23:50 every night.**
    Stacked layers have no outline, as GSO's (`lineColor: 'transparent'`); the spikes themselves were lesson 45. The missing 23:40 and 23:50 blanked the whole stack; like GSO's
    `interpolateNulls`, `alignStack(..., { bridge: 3 })` joins gaps of up to 30 minutes in the drawing only (marked
    "joined"; the tooltip says "no reading"). Regular check-ups follow docs/MAINTENANCE.md.

44. **An empty answer is GSO publishing nothing, not a new format.** On 1 Nov 2026 from 08:30 MYT GetOtherREData
    answered `[]` and GetSolarMap had no rows. Raising SchemaError made both "fail" all day, back off, and would have
    alarmed. `_other_re` and `_solar_farms` now return no readings with `EMPTY_NOTE` (no signature, so no "format
    changed"); content that can't be read still raises. Cards show `staleNote` (ui.js) when their figures are over 45
    minutes old.

45. **ECharts' default stacking ("samesign") draws a value of exactly 0 at the bottom of the chart**, not on the layer
    below. Oil/DF, Co-Gen and Tie-Line touch 0 often, so every 5 → 0 → 5 drew a full-height red or green sliver, worst
    on 7-day and longer ranges (5.14.3's split by sign only hid it on short ones). `timeChart` gives stacked series
    `stackStrategy: "all"` and no `sampling` (thinning each layer separately breaks the stack). The demo browser check
    fails if any stacked chart loses either. Check stacked charts at 7 and 30 days, not just today.

46. **`100vh` on a phone reaches behind the browser's own toolbar.** The menu's Theme and 12-hour buttons, at its
    bottom, were hidden on phones; the phone menu is pinned with `top: 0; bottom: 0; height: auto` instead. And
    `:not(:first-child)` hid every top-bar pill but "Auto", so phones never saw how old the figures were: phones keep
    the freshness pill (`ok`/`warn`/`bad`) and the demo label. The "real" browser check tests both at 360 x 560.

47. **"The same figure on two GSO pages" must be checked, not assumed.** One matching reading (17,696 at 12:20) made
    the site treat the System Demand page's figure as the home page's Grid Demand; over four days it is 0-56 MW higher.
    Current Grid Demand stands in only from the home page's own Grid Demand line (`genmix_live.total_generation`).
    Likewise the home page's tie-line total is minus the Tie-Line page's lines (GSO: "+ve = Export"). The
    maintenance checklist's sums (docs/MAINTENANCE.md) found both; both are now cross-checks (`grid_demand`,
    `tie_line`, with `right_sign: -1`), so the hourly check emails if GSO reorders those figures.

48. **GSO can stall and then publish a stale figure as a new reading.** On 3-4 Nov 2026 the home page and System
    Demand page stopped at 21:10 MYT; at 00:00 the home page started a new day with one value per list repeating the
    stalled figures (Grid Demand 20,858), then nothing until 01:10. `quality.py` marks such a moment "frozen" (alone
    within an hour either side, no System Demand page reading at that time) every cycle over 3 days (migration 6 once
    over all); analytics leaves frozen readings out of latest values, freshness and daily figures, and `getPoints`
    (data.js) turns them into "no reading". Gaps over 30 minutes in the System Demand Profile are shaded
    (`stackGaps`) and labelled "No readings from GSO". Only 4 Nov 00:00 was ever frozen, and at 10:31 MYT that day GSO
    filled in 00:00-01:10 and corrected it (20,858 -> 18,941 -> 18,929), so the next pass lifted the mark: by design.
    A check-up finding no frozen readings is therefore fine; check the revision history for what GSO corrected.

49. **An answer with only summary rows is "nothing published" too.** On 15 Nov 2026 (GSO's solar outage from 08:10)
    GetSolarMap sent only its state totals (`STATE,lat,lon,,MW`) and no stations. `_solar_farms` treats that exact shape
    as `EMPTY_NOTE` (lesson 44); anything else it can't read still raises.

50. **Recent views must not download whole months.** Late in a month the Overview fetched ~1.1 MB of month files for
    24 hours of readings. `export-static` writes `data/points/<key>/recent.json` (newest 3 days) and `week.json`
    (newest 8 days, for the "7 days" views: 40-60% less to download on 20 Nov, more late in a month), and `getPoints`
    (data.js) uses the smallest one the range starts inside: the Overview is now ~100 KB. Keep `RECENT_DAYS` and
    `WEEK_DAYS` equal in `export_static.py` and `data.js`.

51. **GSO's solar map can show output that can't be solar.** PTRM and SKCL show ~18 of 18 MW at 07:20 and 19:10.
    `implausibleSolar` (analysis.js: half capacity or more before 07:30 or after 18:45, at two moments or more) marks
    such farms "GSO figures look wrong": listed as published, left out of maps and totals. Capacity factors
    (`capacityFactor`) leave out time between readings more than 30 minutes apart rather than guess it.

52. **Data that isn't GSO's is labelled everywhere and can't hurt collection.** The Weather page's forecasts come from
    Open-Meteo (`gso_archive/weather.py`, every 3 hours, `WEATHER_ENABLED`); it never raises, records failures as
    its own runs, and its runs are dated by the cycle's clock (`started_at=now`) so `due()` works with a pinned
    clock. After a failure it waits `RETRY_AFTER` (20 min) and each try waits at most `TIMEOUT` (20 s): its first
    live try timed out (TLS handshake), and trying every cycle would slow GSO collection (lesson 41). The probe job
    has no archive, so `weather-trial` falls back to `FALLBACK` locations. Open-Meteo's free service limits requests
    per address and GitHub's runners share addresses, so it sometimes answers 429 (seen on the trial, 15 Nov); after a 429 it waits
    `RETRY_AFTER_BUSY` (1 h). The About page's "Known problems in GSO's data" lists every GSO data problem found
    (lessons 43-51) in plain words: add to it when a new one is found. Weather is not in GSO_ADAPTERS, so the hourly check never alarms on it. The page credits Open-Meteo and calls the LSS estimate this site's own. This session can't reach
    Open-Meteo: the probe job's `weather-trial` step tries it on GitHub.

53. **The LSS explorer (lss.js) has four views (moment, period, daily, day), shared filters (region, connection,
    farm, hours for period views, include-flagged) all in the address, and a CSV for each view** (`csv()` leaves a
    missing reading empty, never 0; files start with a "# Source" line). Hours windows count only slices with both
    ends inside the window (`cfInWindow`). Periods are capped at `MAX_DAYS` (92) day files (~40 KB each). The demo
    browser check clicks every view and every CSV button.

54. **Not all of GSO's data comes from a PageMethod.** System constraints were thought unpublished until 15 Nov 2026:
    GSO writes them as two HTML tables into `LandingPage.aspx` (probe summary "constraints in" section). An
    `AdapterSpec.html_transform` collector GETs the page and reads the tables by GSO's own `<th>` headings
    (`adapters/constraints.py`); `ParsedPayload.tables` keeps each as `constraints_<name>` via `store.keep_table`.
    A row is known by its whole content, so an edit shows as "no longer listed" + "added". The probe summary prints
    any page lines with "onstraint|Outage" so a change of GSO's markup is visible.

55. **A farm GSO stops listing must not count as "now".** On 15 Nov 2026 GSO's solar map dropped MCLS, KDLS and BSLS;
    the Solar page's "now" map, totals and table took each farm's latest value, so their morning figures stayed in.
    Farms whose newest reading is over an hour older than the map's newest are left out and named under the map
    (`dropped` in solar.js). The LSS explorer is unaffected (it reads each moment's farms from the day files).
    Farms `implausibleSolar` flags over yesterday's and today's day files are also left out of the "now" map and
    totals and listed last with the mark, as in the explorer. Every "now" card names the reading's time.

56. **Measured sunshine comes from a satellite, hourly, and must never stand in for GSO's freshness.** `irradiance.py`
    (Open-Meteo satellite API, model `jma_jaxa_himawari`, every hour, `past_days=2`) shares `weather.collect_from`
    (never raises, same back-off). Chosen by `irradiance-trial` on GitHub: about 1 hour behind; NREL NSRDB stops at
    2020 for Malaysia and NASA POWER hourly lagged over 2 weeks. Its series are "actual", so the health check's
    "newest GSO reading" counts only enabled GSO collectors (it would otherwise hide a GSO outage); the page banner
    already uses `LIVE_DATASETS`. The Weather page learns the tomorrow estimate from measured sunshine when there are
    12+ hours of it, and "How Closely the Farms Follow the Sunshine" matches each hour's average farm output (3+
    readings in the hour ending at T) with the satellite value at T.

57. **The farm map follows GSO's (Solar.v19.js) and updates in place.** `solarMap` (charts.js) colours on GSO's colorAxis
    stops (`GSO_STOPS`/`gsoSolarColor`), prints each farm's share on its dot (`labelLayout.hideOverlap`, so zooming in
    reveals them), and has gliding +/−/⟲ buttons. Calling it again on the same element with the same metric only
    replaces the series data, so the explorer's ◀ ▶, slider and Play keep the visitor's zoom; the moment view keeps
    its DOM (`out.dataset.view === "moment"`) for that reason. "Today's Solar Profile" (solar.js
    `solarProfileStrip`) works out GSO's UpdateSolarDashboard figures from the five parts and the forecast; GSO's
    answers carry them too (actual r[5] current, r[6] past change; forecast r[2] peak label, r[3] next-hour change),
    and on 16 Nov they matched, except that GSO's next-hour figure lagged one reading behind.

58. **The explorer must show a gap, not step over it.** On 19 Nov 2026 GSO's Solar page and solar map sent nothing from
    08:10 to 13:00 MYT (collectors "success" with 0 new and 0 unchanged: the tell of an empty answer, lesson 44). ◀ ▶ went
    08:10 → 13:00 silently and "Through a day" drew a straight line across. `gapsOf`/`withBreaks` (lss.js) name gaps over
    30 minutes and break the line. GSO refilled its Solar page's day list afterwards (460 = 5 parts × 92 times), but the
    map is "now" only, so per-farm gaps are permanent. The live site can't be fetched from a cloud session; read the
    `build` job's collect log (`get_job_logs`, saved to a file) for each collector's counts.

59. **ECharts lays labels out only when a chart is redrawn, not after a wheel, pinch or drag zoom.** The farm map's
    `hideOverlap` labels stayed as laid out at the whole-peninsula view (24 of 54 shown at any zoom). `solarMap` redraws
    them on `georoam` (debounced) and at the end of a button glide; zoom goes to 40x. Nudging labels apart
    (`moveOverlap: "shiftY"`) was tried and made clusters unreadable. The demo browser check zooms with a `geoRoam`.
    ECharts also pans a geo only from inside its own box, so `solarMap` turns a drag that starts on the empty area
    (no target, outside `containPixel({geoIndex: 0})`) into `geoRoam` dx/dy itself.

60. **The farm map corrects figures the way GSO's does; the data never changes.** GSO's `getData` (Solar.v19.js, "Data
    correction") shows a share below 0 as 0 and above 100 as 100, and output above capacity as the capacity. `solarMap`'s
    `shownOf` does the same for the real-time metric (labels, colour, tooltip, which also names GSO's figure); tables,
    totals and CSVs keep GSO's figures (MRLS 111 of 106 MW on 17 Nov). The period views' ◀ ▶ (`pstep` in lss.js) move
    the period by its own length within the archive and keep the map's zoom (read from the old map before redrawing).

61. **A run GitHub never starts breaks the collection chain, and the backup schedules may not help.** Run 10811
    (16 Nov 2026, 03:40 UTC) stayed "queued" for good and 8310 (11 Nov, 20:17 UTC) ended "startup_failure"; no schedule
    fired for 4 h and 2 h 45 min. Whole-day lists were refilled later, but "now only" answers (headlines,
    availability, solar_farms) were lost. The `next` job now watches for about 4 minutes after starting a run: if no
    other run is in progress and no newer one finished properly, it cancels the waiting newer runs and starts again
    (twice at most; it never fails the run, lesson 42). Only runs NEWER than the current one count as the next
    collection: on 20 Nov 2026 an older run still finishing its slow backup job was counted, no run was started, and
    collection stopped for an hour (14:06-15:09 MYT). The logic is tried with a stand-in `gh` (healthy, an older run
    finishing, newer running, newer waiting for its turn, stuck once, stuck always).
    Root cause of that hour, three parts: (1) the check counted older runs; (2) it was only tried against the cases
    imagined, not the run list GitHub really shows, and after pushing only ONE live run was read, whose log said "A
    newer run is already on its way" when none existed: a log line was taken on trust; (3) the backup and check jobs
    installed packages on every run (once 5 minutes), which kept old runs "in progress". Now: a job decides whether it
    has work before installing anything, installs use `cache: pip`, and after any change to the chain, compare what
    each `next` log says with the run list itself, for several runs in a row, before calling it done. Find stops with gaps between `collection_runs` (docs/MAINTENANCE.md step 1).
    Run 10811 has no jobs at all, and GitHub refuses a normal cancel (409 "has not been queued yet"), from the API and
    from the website; the website offers no delete for it either. The `tidy` job therefore force-cancels
    (`POST .../runs/{id}/force-cancel`) any run of this workflow still queued after an hour: such a run points at old
    code and must never start late, and no real run waits that long.

62. **Locked copies must still be readable by the next run, and check-ups must not need them.** With
    `ARCHIVE_PASSPHRASE` set, `export_static` publishes only `archive.sqlite3.gz.enc` (meta `archive_download: false`
    hides the About page button) and `seed_from_live` reads it, falling back to the unlocked file for the first run
    after the secret is added. The backup job seals, checks the copy opens again (`cmp`), uploads, then deletes the
    unlocked assets. OpenSSL AES-256-CBC + PBKDF2 (600,000 rounds), passphrase through the environment only. Its
    "Check-up figures" step (`gso-archive checkup`) prints readings per source and day and collection stops.

63. **The public sees the newest 7 days; the owner's passphrase opens the rest, in the browser.** With
    `ARCHIVE_PASSPHRASE` set, `export_static`'s `put` writes each history file (points months, daily, farms index
    and days, tables) in full as `NAME.json.enc` and a public copy trimmed to the 7 days from `public_from` (newest
    reading day - 6; months before it have no public file; monthly CSVs aren't written). meta.json carries `lock`
    (salt, rounds, a check value). `lock.js` derives the same key once (PBKDF2-SHA256, 600,000 rounds, fixed salt) and
    opens "GSO1" + nonce + AES-256-GCM files; `data.js` `getData` reads `.enc` when a key is held (falls back to the
    plain file, and forgets a key that no longer opens anything). `rangePicker` waits for the lock check in `start()`,
    hides 30d/90d/1y, sets the date inputs' min and re-writes `setData`'s text when the check finishes after it.
    Tested: Python/JS round trip (`check_lock.mjs`), the unlock flow at 320 and 1280 px (`check_lock_ui.cjs`), and a
    sweep of every page on the real archive, locked and unlocked.

64. **A watchdog outside GitHub covers GitHub's own schedule failing.** `watchdog.yml` starts `archive.yml` when no run
    started in the last 8 minutes and none under way started in the last 30 (an old stuck "queued" run doesn't count),
    and does nothing otherwise, so it never doubles a healthy chain. It is started every 10 minutes by cron-job.org
    and by its own schedule; `keepalive` keeps both workflows switched on. `tests/test_workflow_next.py` covers it.

65. **GSO's Generation Mix ring is drawn from its home page's own fuel figures, not the Generation page's.**
    LoadGenMixData (LandingPage.aspx) pops GetGenMixData's last parts: r[13] last Thursday, r[14] time, r[15] the
    ring's slices (JSON, = the newest values of r[0]..r[7]), r[16] Distribution Solar total, r[17] slice names, r[18]
    midnight flag; its middle figure is the sum of the slices (DrawGenMixPieChart line 1444). On 20 Nov 2026 at 15:00
    GSO showed 21,047 MW and this site 21,088 MW, because the ring took coal/gas/hydro from the Generation page.
    `genmix_live` now keeps r[0] coal, r[1] gas, r[2] cogen, r[3] oil, r[5] hydro, r[6] solar, and overview.js
    `HOME_FUEL` uses them for the ring when present. The System Demand Profile still stacks the Generation page's
    fuels (they have the full history). Ring labels show from 380 px (smaller ring and text under 560 px).

66. **A site that grows every day needs an alarm before it hits a limit, not a note in a checklist.** GitHub Pages
    allows 1 GB and this site grows about 1.5-2 MB a day (full within about 18 months). `export_static` records
    `site_bytes` in meta.json; `health.site_size_alert` lists it from 350 MB (⚠️ from 700 MB) and emails from 900 MB
    (critical: about 50 days left). Package versions are capped below their next major version (`requirements.txt`,
    `pyproject.toml`): every run installs afresh, so an incompatible release would otherwise stop collection by itself.
    Switching the lock on (lesson 62) once deleted every unlocked daily backup; each backup holds the whole archive,
    so nothing was lost, but only that day's copies were left.

67. **Collection is proven every hour against GSO itself, and only real problems email.** The `check` job (archive.yml)
    restores the archive its own run just saved, fetches every source's current answer once and reads it as collection
    does (`trial.fetch_parse`), and `verify.py` reports any reading GSO shows that the archive lacks (a hole, or over 45
    minutes old). Found once, it is noted (GSO may have just added it); found again an hour later, it is a problem. GSO's
    lists cover only today, so the check also runs at about 23:40 MYT, when anything missing is a problem at once.
    Solar map moments (the map shows only the present) are compared with the Solar page's daylight times; a moment no
    map collector attempt covered is "lost". The check runs whenever the last one is 55 minutes old, so every collection
    run makes sure it happens. Emails (owner, 20 Nov 2026: "only meaningful and important"): only the check may fail a
    run (the other jobs have `continue-on-error`; what keeps failing in them shows in the check as an old site or an old
    backup), and `alerts.decide` emails a problem when it is new and then at most once a day while it lasts
    (`problem_id` ignores the figures in it); its memory is the `health-state-` Actions cache. The owner then asked
    for email ONLY when something is critical: the site or collection down, a collector broken on our side, GSO's
    figures filed under wrong names, readings GSO shows missing from the archive, 3+ solar map moments lost in a day,
    no backup for 2 days, the site near 1 GB. GSO's own outages and silences are listed with ⚠️ and never email.
    The check's comparison (`proof` in its saved notes) is restored by the next build (`HEALTH_STATE`) and shown on
    the Status page as "Proof against GSO".

68. **GSO's Other RE split runs one step ahead of its home page chart.** The 21 Nov 2026 check-up counted only 113-138
    `other_re` readings a day: the split (no time of its own, lesson 38) was refused whenever its total differed from
    the chart's newest reading, and 189 of 205 such totals equalled the chart's NEXT reading exactly. A split that
    matches nothing yet is now remembered (`AdapterSpec.keeps_state`: the collector loads `ctx["state"]` and saves
    `ParsedPayload.state` in system_state "adapter:<key>") and filed when the chart's next reading, within 20 minutes,
    has the same total. Look for this kind of loss by counting readings per source and day (`gso-archive checkup`).
    The same check-up missed that GSO's Solar page had published nothing since 08:10 that day: the hourly check listed it
    with ⚠️ and it was read as healthy because everything GSO did show was archived. Read the ⚠️ notes in a check-up.
    The owner saw the outage on a phone as "missing data", so the Solar Profile chart now shades GSO's gaps too, with
    `stackGaps(..., { until })` also marking a gap still going on (no reading for 45+ minutes up to now), and the
    "No readings from GSO" label shows from 280 px.

## How to check a change

```bash
python -m pytest                       # all tests, including the browser checks
TEST_DATABASE_URL=postgresql://… python -m pytest --ignore=tests/test_frontend.py   # same suite on PostgreSQL
```

The browser checks (`tests/frontend/check_states.cjs`, preinstalled Playwright + Chromium) cover every main page at
320, 360, 390, 768, 1024, 1440 and 1920 px: no sideways scrolling, and no `NaN`, `undefined` or `Infinity` on screen.
They also cover the empty, loading, error, demo and static-site states, click through everything a visitor can do,
and simulate new readings arriving. Look at the Solar and BESS pages yourself at 320 px and 1440 px after any layout
change. Real GSO answers saved on 28 October 2026 are in `tests/fixtures/real/`.
