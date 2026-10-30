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
- After every check, end with the possible improvements to the current version that need the owner's decision
  (what each would do, its cost or risk, and a recommendation), even when everything passed.
- READMEs follow the owner's format: centred title, bold one-line description, green "OPEN THE SITE" badge, a clickable
  screenshot, then "What it is", "How current is it?", "Open it" (the site is online only: no install or local-run
  steps in the README; developer instructions live in docs/DEVELOPMENT.md), and credits.
- GitHub only: Actions and Pages, no paid server or database service. Don't commit the archive database or raw data
  to git: the archive lives in the Actions cache, the published site and the `archive-backups` release.
- No `Version N/` folders on `main` (the owner asked for them to be hidden). Like Physics Fruit Rush, a substantial
  update gets a new version number (`gso_archive/__init__.py`, the commit message "GSO Grid Archive N.0 - …" and a
  CHANGELOG entry). Versions 1–3 are preserved as they were on the `versions` branch; never change or delete it.
- Requests to other sites name the project, never the owner (no name or email in the User-Agent).
- Never invent readings, endpoints or source capabilities. Demonstration data is watermarked and labelled everywhere.
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
    (`plan_cycle`) and with no retries (`collect_one`) until it succeeds again. The trial uses one try per address.

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
