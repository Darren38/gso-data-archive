# Changelog

## 30 October 2026 (sixteenth update) — GSO Grid Archive 5.8

More trustworthy for people who use this site instead of GSO's own.

- **New: a clear warning when readings are late.** If the newest GSO reading on the site is more than 45 minutes old (because GSO's website or this archive's collection has a problem), every page now says so in a yellow note at the top, with the time of that reading, so old figures are never taken for current ones. The note goes away by itself when fresh readings arrive. Normally readings arrive 15 to 25 minutes after the time they are for.
- **New: GSO's pages are checked against each other.** GSO publishes two figures on two different pages, and in the real archive they agree at every daylight reading: the Solar page's Grid solar equals the Generation page's Solar, and the home page's Distribution Solar equals the Solar page's Distribution + NEM + FiT + SELCO. GSO's Solar page and home page send unlabelled lists, so if GSO ever changed their order, numbers could be filed under the wrong names without anyone noticing. Now the Collection Status page shows whether the pages still agree, and the hourly check emails the owner if they stop agreeing.
- **The hourly check also catches old data.** Before, it only noticed if collection stopped. Now it also fails if collection runs but GSO's newest reading is more than 3 hours old.
- **Fixed: the forecast looked twice as accurate as it is.** The Solar page's "Forecast vs Actual" counted every night-time moment, when both the forecast and the actual are zero. That halved the "typical miss". With night left out, the typical miss on 28 October was 115 MW, not 48 MW, and actual solar was on average 95 MW above GSO's forecast, not 39 MW.
- **Checked:** the Solar page's readings are on the right times. Its Grid figures equal the Generation page's solar at exactly the same times (78 of 78 daylight readings). The repair in 5.7 was run on a copy of the real archive: it put every misfiled Solar page reading back on its own day and removed the copied day, and both checks above pass on it.
- **Known and unavoidable:** GSO's Solar page and home page start the new day's list at midnight, before the readings for 11:40 pm and 11:50 pm are published, so those two night-time readings are always missing on those pages. They are shown as gaps; nothing is made up.
- A test that depended on the time of day (it failed between 11:30 pm and 12:30 am) now always uses the time the real GSO answers were saved.

## 29 October 2026 (fifteenth update) — GSO Grid Archive 5.7

Fixed: every evening the Solar page's readings were filed under the day before.

- GSO's Solar page lists today's readings only. After sunset, GSO's "time of the latest reading" stops moving forward, but the list of readings keeps growing through the night. The archive used that time to decide which day a list belonged to, so each evening the list looked "too long for today" and the whole day was saved under the previous day.
- What this did: the archive's "27 October" was really a copy of 28 October (none of its Solar page readings were collected on the 27th itself), and 28 October was missing its evening from 8:20 pm. Left alone, tonight's readings would have overwritten the 28th's.
- Now the real clock decides the day. The readings already misfiled were moved back to the right day and the copied day removed. Nothing was made up: every reading kept is one GSO published. The Solar page now correctly says collection began on 28 October, and its peak (3,969 MW at 1:30 pm) is dated 28 October.
- Clearer: the Demand page's "Minimum System Demand" now shows the time it happened, like the peak does (for example "25 Oct 2026, 07:40 MYT" instead of "2026-10-25").
- Checked again with the real archive saved on GitHub this morning: every number on the Overview, Solar, Demand, Tie-Line and BESS pages was worked out separately and matches. Every page at 7 screen widths (phone to large desktop), light and dark, both clocks, and every button: no errors, nothing cut off or spilling sideways.

## 29 October 2026 (fourteenth update) — GSO Grid Archive 5.6.2

Another full check of the site and its numbers, with real GSO answers.

- Every main number was worked out again separately from the archive and from GSO's own totals, then compared with what the pages show. They match: current solar (3,939 MW, the same as GSO's own figure), demand, battery status, the forecast peak, the Generation Mix and Generation Availability totals, the solar farms (58 farms, 1,813 of 2,359 MW), solar energy, ramps and solar's share of demand.
- Fixed: daily energy totals left out the last few minutes of each day (from the last reading before midnight to the first one after). Energy figures for solar, demand and batteries were about 1% too low; for example a week of demand showed 2.00 TWh instead of 2.04 TWh.
- Fixed: on the Solar Map, pointing at or tapping a farm didn't show its output and capacity. A setting that hid pop-ups for the land also hid them for the farms.
- Fixed: "Data Completeness" on the Solar page counted the days before the archive started collecting as missing (GSO's Solar page only ever shows today, so those days can't be filled). It now counts from the day collection began and says so.
- Fixed: long date ranges asked for monthly data files from before the archive began, which don't exist. Only months with readings are fetched now.
- Checked: every page at 7 screen widths, light and dark, both clocks, and every button, range, menu and map interaction: no errors, nothing cut off or spilling sideways, no "NaN" or "undefined".

## 29 October 2026 (thirteenth update) — GSO Grid Archive 5.6.1

Fixed: the live site stopped showing new readings for hours at a time.

- Collection never stopped. Every run kept saving GSO's readings into the archive every 2 minutes, but from early on 29 October the published site stayed hours behind (for example still showing 6:40 am at 9:41 am).
- The cause was how the site was published. GitHub names each published copy, and the publishing step always used the code's version number. Because the site is republished every few minutes from the same version, hundreds of copies shared one name. GitHub kept serving an older copy and reported "success" each time.
- Now every run publishes under its own name and waits until that exact copy is live. GitHub only accepts a code version as that name, so each run makes a private copy of the version that sits on no branch: it never appears in the project's history or list of contributors, and GitHub tidies it away later. If publishing really fails, the run fails and GitHub emails the owner.
- The hourly check of the live site is what caught this: it marked the 6, 7 and 9 am checks as failed because the site's last collection was hours old.

## 29 October 2026 (twelfth update) — GSO Grid Archive 5.6

A solar map like GSO's, and every number checked again.

- **New: Solar Map.** The Solar page now has a map of Peninsular Malaysia with every LSS solar farm from GSO's solar map at its location. The colour shows how much of its capacity each farm is producing right now (grey = little or none, orange = close to full), bigger dots are bigger farms, and circles and diamonds show grid and distribution connection. Above the map: each region's output as a share of its capacity (North, Central, South, East and all together). Tap or hover a farm for its numbers; drag or pinch to zoom. The farms' locations come from GSO's own map data. The outline of the land is from Natural Earth (free to use).
- **Fixed: solar-farm readings at night were dated 07:00 the next morning.** Before sunrise GSO's "time of the latest reading" says 07:00, a time still to come. Farm readings now use the real time of collection, any reading dated in the future is refused, and the wrongly dated readings already in the archive are removed.
- **Fixed: "Data Completeness" counted a whole day's readings for today.** Just after midnight it showed about 50% for "48 h". Today now only counts the readings GSO could have published so far.
- **Clearer: the Solar page's numbers now match its chart.** They describe all solar together (Grid + Distribution + NEM + FiT + SELCO), the same total as the Solar Profile chart. Before, they described Transmission Solar alone (for example a peak of 1,669 MW next to a chart reaching about 4,000 MW). You can still pick one kind of solar, and the cards then say which one ("Peak Transmission Solar").
- **Fixed: "Solar Share of Demand" could divide readings from different times.** It now only uses a solar and a demand reading taken at the same moment.
- **Checked, and correct:** the forecast line for the new day just after midnight is GSO's genuinely new forecast (for 29 October GSO forecast a peak of 3,661 MW at 12:20; for 28 October it was 3,616 MW at 13:20), not a copy of the day before.
- Chart time labels no longer run together on half-width charts showing two days.

## 28 October 2026 (eleventh update) — GSO Grid Archive 5.5

Easier to find on Bing and other search engines, the same way as Tech Comparison Hub.

- The site now has a clear title and description for search results, its official address, share previews with a screenshot (for WhatsApp, Facebook and the like), and a summary search engines can read.
- A sitemap lists the site for Bing and Google.
- After every update to the site's code, an automatic step waits until the new version is live and then tells Bing, Yandex and others through IndexNow. The readings that arrive every few minutes don't trigger it, so search engines aren't flooded.

## 28 October 2026 (tenth update) — GSO Grid Archive 5.4

The demand chart now looks like GSO's own System Demand Profile.

- On the **Demand** page, for any range up to a month, the main chart is now drawn the way GSO draws its "System Demand Profile for Peninsular Malaysia": coal at the bottom, then gas, co-gen, oil, tie-line, hydro, BESS, transmission solar, distribution solar and other renewables stacked on top, in GSO's colours and with GSO's key order, plus the System Demand line (dashed) and GSO's Grid Demand line (solid, when GSO publishes it). Longer ranges keep the single demand line, which is easier to read over months.
- The **Generation Mix** chart on the Generation page uses the same GSO-style chart, so it now also shows tie-line, BESS and the demand lines.
- Fixed: stacked charts could show a fake dip. When one source had no reading at a moment, the chart counted it as zero and drew every layer above it too low. Sources are now lined up on GSO's 10-minute steps, and a moment where any source has no reading is left as a gap, as everywhere else on the site.
- Charts this site works out itself (today against yesterday, daily peaks, profiles, ramps and so on) are unchanged.

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
