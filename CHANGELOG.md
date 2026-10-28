# Changelog

## 28 October 2026 (ninth update) — GSO Grid Archive 5.3

Looks more like GSO, and a full check for bugs.

- Charts look more like GSO's home page: "Generation Mix" and the new "Generation Availability" are rings with the total MW in the middle in green, labels such as "Gas: 36.5%", round colour dots in the key, and the date and time underneath the title in GSO blue (for example "28 October 2026, 4:20 pm MYT").
- Card titles are in capitals with a short green bar underneath, like GSO's headings, and GSO green is used for buttons and the selected page.
- The Generation Mix now shows one moment in time, the newest time at which every fuel has a reading, so its numbers add up the way GSO's do. Before, it could mix readings from slightly different times.
- "Last Updated" is now "Latest GSO Reading": it shows the time of GSO's newest reading, how long ago that was, and when this site last checked GSO. (GSO adds a reading every 10 minutes and publishes it a little later, so "20–30 min ago" is normal.)
- Checked every page at 7 screen widths, in light and dark mode and with both clocks, using real GSO answers: no errors, no sideways scrolling, no "NaN" or "undefined", and nothing cut off. Fixed along the way:
  - big numbers spilling out of narrow cards (for example 14,350 MW on a 1,024 px screen, "Connected" on a 320 px phone)
  - "Observed -23450 s ago" when a time was slightly in the future (now "just now")
  - donut labels cut off ("Transmission Sol…"); they now wrap onto two lines like GSO's
  - the donut key falling back to small "1/7" arrows on phones
  - the energy total "653,517 MWh" overflowing its ring (now "653.5 GWh")

## 28 October 2026 (eighth update) — GSO Grid Archive 5.2

Choose your clock.

- A new **12-hour / 24-hour** button next to Theme (in the menu on phones) switches every time on the site, including cards, tables, chart labels and tooltips, between "13:30" and "1:30 pm". Your choice is remembered on your device.
- The "Short forms used on this page" notes are now a dropdown: press to expand. Very short lists stay open.

## 28 October 2026 (seventh update) — GSO Grid Archive 5.1

Livelier headline numbers, and GSO's own words.

- Every headline number now has a small colourful picture, in the spirit of GSO's own home page: a solar panel for solar, a power tower for demand, a battery for storage, a light bulb for the day's peak, a sun behind a cloud for the forecast, a clock for when the data was updated, and a flame, factory or water drop for whichever fuel is making the most electricity right now.
- The pictures are drawn for this site (not copied from GSO) and work in light and dark mode.
- On phones the picture sits above its label, and numbers such as "15,216 MW" now stay on one line.
- The words now match GSO's own pages: "Current System Demand", "Current Solar Generation", "Current BESS Status", "Solar Profile", "Generation Mix", "System Availability", "Cross-Border Power Exchange (Tie-Line)", and GSO's series names Grid, Distribution, NEM, FiT, SELCO, Forecast, Transmission Solar, Distribution Solar, Co-Gen, Oil/DF and Other RE.
- Each page has a short "Short forms used on this page" note explaining terms such as MW, MWh, BESS, NEM, FiT, SELCO, LSS, EGAT, HVDC and PLTG. It is open on computers and folded on phones (tap to open). The About page lists them all.

## 28 October 2026 (sixth update) — GSO Grid Archive 5.0

A clearer dashboard that's quicker to read.

- The Overview is now a dashboard: four big numbers at the top (solar right now, electricity demand, how much of demand solar covers, and the batteries), then today's solar against GSO's forecast, where electricity comes from right now, and today's demand against yesterday's.
- Every chart has a short line under its title saying what it shows and how to read it, in plain words ("Bars: the highest solar output each day. Line: total solar energy that day").
- Colours now follow GSO's own charts: the same oranges and yellows for each kind of solar, GSO's green for the forecast, grey for coal, blue for gas, green for hydro, and green and pink for batteries supplying and charging.
- Plainer names everywhere: "Large solar farms (grid)" and "Solar on local network" instead of "transmission" and "distribution"; "Fastest rise" instead of "steepest up-ramp"; "Typical miss" instead of "MAE".
- The Solar page leads with what matters most (solar by type, solar against demand, daily peaks, the forecast check, solar farms). The detailed analysis sits in its own "Deeper analysis" section below.
- Bigger text: larger headline numbers, chart labels and page text.
- Chart keys on phones now wrap onto extra lines instead of hiding names behind small arrows.
- Fixed: the battery figures showing a minus sign while charging; units such as "MW" splitting across two lines on narrow phones; all power plant types in one colour on the availability chart.
- The site was already plain HTML, CSS and JavaScript with nothing to install; it opens straight from the link in the README.

## 28 October 2026 (fifth update) — GSO Grid Archive 4.1

The site is online and collects from GSO without stopping.

- The site is live at https://darren38.github.io/gso-data-archive/ with real GSO data.
- GitHub had not started a single scheduled run in over an hour, so each run now starts the next one about a minute after collecting. New readings arrive every 2–3 minutes; only one chain ever runs; GitHub's schedule stays as a backup that restarts it if it ever stops.
- The page check (probe) runs only after a push or when asked, and the backup is made once a day, so the frequent runs don't add load on GSO.
- The README's "Run it locally" steps are replaced with "Open it": the site is meant to be opened online with one click. Developer steps are in docs/DEVELOPMENT.md.

## 28 October 2026 (fourth update) — GSO Grid Archive 4.0

Real data from GSO's Solar page and home page, checked first-hand.

- GitHub's servers can reach gso.org.my, so the archive now looks at GSO's pages directly. A check runs after each push and once a day and writes down which data addresses each page uses. Every address the archive uses has now been seen working, and each number's meaning comes from GSO's own page scripts.
- New from GSO's Solar page (the link given at the start): grid (transmission) solar, distribution solar, and NEM, FiT and SELCO rooftop solar every 10 minutes (the rooftop values are GSO's own estimates and are labelled that way), and GSO's solar forecast for the day.
- New from GSO's home page: battery storage (BESS) charge and discharge, total generation, other renewables (biogas, biomass, mini hydro), total tie-line flow, system availability by fuel, and the live output and capacity of about 60 solar farms.
- The Solar page has a new "Solar by connection" chart in GSO's style, forecast against the matching actual total, transmission against distribution, and a live solar-farm table. The BESS page now shows real charge and discharge. The Overview shows all solar and the battery's net flow.
- These GSO pages only show today, so they are collected all day; around midnight the archive checks which day a list belongs to rather than guessing.
- Fewer requests to GSO: no page downloads before asking for data, and the time of the latest solar reading is asked once per run.
- The EGAT tie-line is kept: GSO's menu no longer lists it, but it still answers with readings. The guessed Solar address used before (which GSO refused) is gone.
- The repository's front page no longer shows version folders: the code is at the top level, like the owner's other projects, and versions 1–3 are kept on the `versions` branch.

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
