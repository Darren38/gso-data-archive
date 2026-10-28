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
