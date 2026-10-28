# GSO source investigation

Investigation date: 28 October 2026. Every statement is labelled with how it was established.

| Label | Meaning |
|---|---|
| **[OBSERVED]** | Seen first-hand by this project |
| **[3RD-PARTY]** | Taken from maintained third-party code or documentation; not observed first-hand |
| **[INFERRED]** | Reasoned by analogy; must be verified |
| **[UNKNOWN]** | Not determined |

## 1. What was attempted

| Attempt | Result |
|---|---|
| `curl https://www.gso.org.my/SystemData/Solar.aspx` from the development container | **Blocked**: the container's egress proxy refused `www.gso.org.my` (network policy, HTTP 403 on CONNECT) **[OBSERVED]** |
| Web-fetch tool for `/`, `/SystemData/Solar.aspx`, `/SystemData/SystemDemand.aspx` | **Failed**: DNS `ENOTFOUND` from that tool's sandbox **[OBSERVED]** |
| Web search for documentation of the pages | No official API documentation found **[OBSERVED]** |
| Electricity Maps `electricitymaps-contrib` repository (cloned) | Contains a maintained GSO parser. See §2 **[OBSERVED that the code exists; its claims are 3RD-PARTY]** |
| Aether03 `malaysia-energy-transition-dashboard` README | Makes a statement about GSO's terms of use. See §5 **[3RD-PARTY]** |

The source could not be inspected directly with browser tools or network inspection, so
nothing in this archive's configuration counts as "verified". Run `python -m gso_archive probe`
from an allowed network to close this gap (§6).

## 2. Access method: ASP.NET PageMethods [3RD-PARTY]

Source files:
`electricitymap/contrib/parsers/GSO.py` (production, consumption, exchange) and
`electricitymap/contrib/capacity_parsers/MY_WM.py` (capacity), cloned on 28 October 2026.

* The site is ASP.NET WebForms. Chart data comes from **PageMethods**: an HTTP `POST` of a
  JSON body to `<page>.aspx/<MethodName>`.
* The response is `{"d": "<JSON string>"}`. The inner string decodes to a **list of records**.
* No authentication is used by that parser. It sends `Content-Type: application/json` and,
  for capacity, `Origin`/`Referer` headers.
* **Historical queries are supported:** each method takes `Fromdate` / `Todate` as
  `DD/MM/YYYY`, and the parser requests one Malaysian calendar day at a time for any
  `target_datetime`. A response therefore holds **all readings for that day**, not only the latest.
* Timestamps are naive local time. The parser attaches `Asia/Kuala_Lumpur`.
* The parser is decorated with `@use_proxy(country_code="MY")`, which suggests GSO
  **may block or degrade non-Malaysian clients** **[INFERRED from that decorator]**.

| Dataset | Endpoint | Body | Fields | Unit |
|---|---|---|---|---|
| Generation mix | `/SystemData/CurrentGen.aspx/GetChartDataSource` | `Fromdate`, `Todate` | `DT`, `Coal`, `Gas`, `CoGen`, `Oil`, `Hydro`, `Solar` | MW |
| System demand | `/SystemData/SystemDemand.aspx/GetChartDataSource` | `Fromdate`, `Todate` | `DT`, `MW` | MW |
| Tie-lines | `/SystemData/TieLine.aspx/GetChartDataSource` | `Fromdate`, `Todate`, `Line` ∈ {`EGAT`, `HVDC`, `PLTG`} | `Tarikhmasa`, `MW` | MW |
| Installed capacity | `/SystemData/PowerStation.aspx/GetDataSource` | none | `Fuel`, `Capacity (MW)`, … | MW |

Electricity Maps maps `PLTG` to Singapore and `EGAT` + `HVDC` to Thailand, and treats the value as
net flow in the sorted-zone direction, which implies **positive = export from Peninsular Malaysia**.
GSO's own sign convention is **[UNKNOWN]**. The archive stores values exactly as published.

## 3. Solar

| Question | Answer |
|---|---|
| Is solar generation published? | Yes, as the `Solar` field of the generation-mix feed **[3RD-PARTY]**. This is the archive's primary solar series (`generation_mix.solar`). |
| Transmission vs distribution split? | **[UNKNOWN]**. Possibly on `Solar.aspx` |
| Solar forecast, forecast issue time? | **[UNKNOWN]** |
| Peak values, historical profiles? | Daily profiles via `Fromdate`/`Todate` **[3RD-PARTY]**. Peaks are derived by this archive |
| `Solar.aspx` endpoint | Assumed `SystemData/Solar.aspx/GetChartDataSource` with the same body **[INFERRED]**. Adapter `solar_profile` is registered but **off by default** |
| Time resolution | **[UNKNOWN]**. The archive infers the interval from the data |
| Does `Solar` mean transmission-connected only? | **[UNKNOWN]**. Labelled "as published in generation mix" |

Because the `Solar.aspx` field names are unknown, the `solar_profile` adapter **auto-discovers**
every numeric field and stores it under its source name. Fields whose names contain
"forecast" go to the forecasts table. Nothing is renamed on a guess.

## 4. Other categories

| Category | Status |
|---|---|
| Demand | Endpoint documented **[3RD-PARTY]**. Whether "system" and "grid" demand are published separately is **[UNKNOWN]** |
| Generation by fuel | Documented **[3RD-PARTY]**. New fuel fields are auto-discovered |
| Installed capacity | Documented **[3RD-PARTY]**. Archived daily as a snapshot summed by fuel |
| Tie-lines | Documented **[3RD-PARTY]** |
| BESS | No endpoint known **[UNKNOWN]**. Not implemented |
| System constraints | No endpoint known **[UNKNOWN]**. Not implemented |

Electricity Maps' data-source list also references `https://www.gso.org.my/LandingPage.aspx`.
The landing page probably carries the live headline values. `probe` saves it for review.

## 5. Terms of use and automated access

* The Aether03 project states: *"The Grid System Operator's terms forbid downloading or
  storing its data without TNB's written consent"*. It keeps its own GSO adapter disabled pending
  consent **[3RD-PARTY; this is their paraphrase and the original terms text was not seen]**.
* No `robots.txt`, rate-limit documentation or official API was observed **[UNKNOWN]**.
* Whether a 5-minute polling frequency is acceptable is **[UNKNOWN]**.

**Project response:** live access to `www.gso.org.my` is gated behind `GSO_LIVE_ENABLED`
(default `false`). The HTTP client refuses to contact the host unless it is set. When enabled, the
collector stays polite: one request at a time, at least 2 s between requests, an identifying
User-Agent, retries only for 5xx/429/timeouts, and `Retry-After` honoured. It never
bypasses authentication, CAPTCHAs or access controls. At the default settings a cycle sends about
one small request per dataset for today every 2–3 minutes (about 6 requests), plus an hourly re-check of yesterday and occasional back-fill. If GSO publishes less often than that, the extra requests simply find nothing new (recorded as unchanged).

**Recommendation:** before enabling, read the terms on gso.org.my and, if consent is
required, request it from GSO/TNB, describing the use (non-commercial research archive) and
the request rate.

## 6. How to verify (closes the remaining unknowns)

From a machine that can reach the site (a Malaysian network is best), after the terms review:

```bash
GSO_LIVE_ENABLED=true python -m gso_archive probe
```

This GETs each SystemData page once and extracts PageMethod names, AJAX URLs, form fields,
chart library and any terms/disclaimer text. It then POSTs each discovered method once for
today's date and saves everything under `data/probe/<timestamp>/` along with `report.json`.

Then:

1. Compare `report.json` with §2. If they match, change `verification` to `"verified"` in
   `gso_archive/adapters/registry.py`.
2. Copy representative responses into `tests/fixtures/` (real fixtures) and add tests.
3. If `Solar.aspx` exposes data, set the correct method name, add it to `GSO_ADAPTERS`, and
   map any newly discovered fields to friendly names in `SOLAR_PROFILE.fields`.
4. Record the observed time resolution and how far back the source keeps history (try `backfill`
   on older dates), and update this document.
