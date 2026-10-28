# GSO source investigation

Last checked: 28 October 2026, from GitHub's servers (the development container itself cannot reach gso.org.my).
Labels: **[OBSERVED]** seen first-hand by this project · **[GSO SCRIPT]** read from GSO's own page scripts ·
**[3RD-PARTY]** from another project · **[UNKNOWN]**.

## 1. How it was investigated

1. The development container's network policy blocks gso.org.my, so the first version relied on the open-source
   Electricity Maps GSO parser **[3RD-PARTY]**.
2. A `probe` job in the GitHub workflow then opened each GSO page from GitHub's servers. It listed every data address
   the page's HTML and scripts call, tried each one once, and printed the answers and the scripts' parsing code to the
   run log **[OBSERVED]**. It runs after each push and once a day, so changes on GSO's side show up.
3. GitHub's servers reach gso.org.my without problems (HTTP 200, no blocking seen) **[OBSERVED]**.

## 2. How GSO serves data **[OBSERVED]**

* ASP.NET WebForms. Charts load data with `POST <Page>.aspx/<Method>` and a JSON body. The answer is `{"d": …}`.
* No login, cookie or prior page visit is needed. The archive skips page visits to save GSO bandwidth.
* `.js` files are refused with **HTTP 406** unless the request accepts `*/*`.
* Wrong addresses answer **HTTP 401** (e.g. the guessed `Solar.aspx/GetChartDataSource`) or an HTML error page.

## 3. Data addresses used by the archive

| Collector | Address | Body | Answer **[OBSERVED]** | Meaning |
|---|---|---|---|---|
| `generation_mix` | `SystemData/CurrentGen.aspx/GetChartDataSource` | `Fromdate`, `Todate` (`DD/MM/YYYY`) | JSON list: `DT`, `Coal`, `Gas`, `CoGen`, `Oil`, `Hydro`, `Solar`, **every 10 min** | MW by fuel; any past day |
| `system_demand` | `SystemData/SystemDemand.aspx/GetChartDataSource` | same | `DT`, `MW`, every 10 min | MW; any past day |
| `tieline_*` | `SystemData/TieLine.aspx/GetChartDataSource` | + `Line` = `HVDC` / `PLTG` / `EGAT` | `Tarikhmasa`, `MW`, `Line`, **every 30 min**, newest first | MW. GSO's menu (`LoadLine`) lists only HVDC (Thailand) and PLTG (Singapore), but EGAT still answers |
| `power_station` | `SystemData/PowerStation.aspx/GetDataSource` | none | `Name`, `Fuel` (padded, e.g. `"Water     "`), `Type`, `Capacity (MW)`, `PPAExpiry` … | Installed capacity |
| `solar_profile` | `SystemData/Solar.aspx/GetSolarActualData` | `{}` | `"$"`-joined text, see §4 | **Today only** |
| `solar_forecast` | `SystemData/Solar.aspx/GetSolarForecastData` | `{}` | 144 values + summary, see §4 | **Today only** |
| (time stamp) | `SystemData/Solar.aspx/GetLastAvailableData` | `{}` | `"2026-10-28 13:30\|28/10/2026 13:30"` | Time of newest solar reading |
| `genmix_live` | `LandingPage.aspx/GetGenMixData` | `{}` | `"$"`-joined text, see §5 | **Today only** |
| `availability` | `LandingPage.aspx/GetSysAVData` | `{}` | `"28 October 2026 1:20 PM$11252$10705$0$2093$1615$2324$100"` | Snapshot with its own time |
| `solar_farms` | `LandingPage.aspx/GetSolarMap` | `{}` | rows `state,lat,lon,code,%,region,live MW,capacity MW,state %,GRID/DN` | Live snapshot |

Timestamps without a timezone are Malaysia time (UTC+8). The first value of each "today" list is 00:00, then
every 10 minutes **[OBSERVED, GSO SCRIPT]**.

## 4. GSO's Solar page **[GSO SCRIPT: `Scripts/Solar.v19.js`, `DrawSolarChart`]**

```
r = response.split('$')
r[0] ActualToday     -> chart series "Grid"          (transmission-connected solar)
r[1] ActualDistToday -> "Distribution"
r[2] NEM, r[3] FIT ("FiT"), r[4] SELCO   -> "NEM, FiT and SELCO values are estimates based on registered data as of <date>"
r[5] currentMW (= sum of the five latest values; 3939 in the saved answer)   r[6] pastChange
forecast answer: list(144) $ 4520 $ "3,616 MW <br />@ 13:20" $ -518 $ 22-Oct-2026
```

Checks against the saved real answers (tests/fixtures/real) **[OBSERVED]**: the five latest values add up to
GSO's `currentMW` (3,939 MW), and the forecast's largest value, 3,616 MW, lands at 13:20, matching GSO's own label.

## 5. GSO's home page **[GSO SCRIPT: `Scripts/SolarLandingPage.v5.js`]**

`GetGenMixData`, `DrawGenMixChart(r)`: r[0] Coal, r[1] Gas, r[2] CoGen, r[3] Oil, r[4] TieLine, r[5] Hydro,
r[6] Solar, r[7] NonSolar (plotted as "Other RE"), r[8] TotGen (plotted as "Grid Demand"), r[9] DistSolar,
r[10] null flag, r[11] BessDischarge, r[12] BessCharge (negative), r[13] registration date,
r[14] `"Wednesday, 28 October 2026 1:20 PM"` (time of the newest value). The archive keeps r[4], r[7]–r[9] and
r[11]–r[12]; the fuels are already archived from the generation page. GSO fills gaps by interpolation for its chart;
the archive does not.

`GetSysAVData`, `DrawSysAvPieChart`: time, Coal, Gas, CoGen, Hydro, Solar, DNSolar, Bess ("System Availability").

`GetSolarMap`, `getData(point)`: [3] station code, [4] MW percentage, [5] region, [6] live generation, [7] capacity,
[9] "GRID" or "DN". Rows with fewer fields are state summaries.

## 6. Found but not archived (yet)

| Address | Why not |
|---|---|
| `LandingPage.aspx/GetFeatureSectionData` | Seven headline figures (e.g. 18,356 MW; record 22,014 MW on 6 Aug 2026 20:30) without labels in the answer. Needs the labels from the page before archiving |
| `LandingPage.aspx/GetOtherREData` | Other renewables split (biogas 99, biomass 18, mini hydro 51) with no time stamp. Total is archived via `genmix_live.other_re` |
| `SystemData/CBPE.aspx/ForecastChart*` | A forecast page; the answer format isn't decoded yet |
| `*/DownloadFile`, `*/Plot_Click` | A file token and an HTML table of the same data |

System constraints: no page or data address found **[OBSERVED]**.

## 7. Terms of use

The site footer links to `/TermsConditions.aspx` **[OBSERVED]**. Its text hasn't been read by this project. Another
project states that GSO's terms require TNB's written consent to download or store GSO data **[3RD-PARTY]**.
Collection is switched on at the owner's instruction (repository variable `GSO_LIVE_ENABLED=false` pauses it). The
collector names the project, not a person, in its requests. It asks about once every 2–3 minutes per dataset,
waits 2 s between requests, and backs off on errors.

## 8. Remaining unknowns

* GSO's tie-line sign convention (Electricity Maps reads positive as export from Peninsular Malaysia) **[UNKNOWN]**.
* What the forecast summary values `4520` and `-518` mean (probably capacity and next-hour change) **[UNKNOWN]**.
* How long GSO keeps past days on the date-based pages; try `backfill` on older dates **[UNKNOWN]**.
