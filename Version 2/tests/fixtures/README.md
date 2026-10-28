# Test fixtures — SYNTHETIC values in the documented GSO response format

These files are **not real GSO data**. This development environment could not reach
`www.gso.org.my` (network policy), so no first-hand responses could be captured.

The *structure* follows the GSO ASP.NET PageMethod format as implemented by the
maintained open-source Electricity Maps parser (`electricitymap/contrib/parsers/GSO.py`,
`capacity_parsers/MY_WM.py`):

* POST `/SystemData/<Page>.aspx/GetChartDataSource` with `{"Fromdate": "DD/MM/YYYY", "Todate": "DD/MM/YYYY"}`
  (tie-lines add `"Line": "EGAT" | "HVDC" | "PLTG"`).
* Response `{"d": "<JSON string of a list of records>"}`.
* CurrentGen records: `DT` + `Coal`, `Gas`, `CoGen`, `Oil`, `Hydro`, `Solar` (MW).
* SystemDemand records: `DT` + `MW`. TieLine records: `Tarikhmasa` + `MW`.
* PowerStation `GetDataSource` records include `Fuel` and `Capacity (MW)`.

All numbers are invented. Replace or supplement these with real responses saved by
`gso-archive probe` once the source is reachable (keep the synthetic ones for edge cases).
