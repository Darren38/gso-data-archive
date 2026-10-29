// Solar dashboard: the archive's primary page.
import { getDaily, getPoints, exportUrl, rollup } from "../data.js";
import { COLORS, FUELS, SOLAR_PARTS, solarMap, categoryChart, profileChart, timeChart } from "../charts.js";
import { combine, dailyFromPoints, extent, forecastError, intradayProfiles, ramps, sumSeries } from "../analysis.js";
import {
  addDays, card, downloadText, emptyState, errorState, esc, fmtDate, fmtDateTime, fmtEnergy, fmtLong, fmtNum, fmtTime,
  freshnessPill, getParam, h, kpi, loading, mytDayStart, pointsToCsv, rangePicker, renderTable, section, setParams, shortForms, verificationTag,
} from "../ui.js";

const RAW_LIMIT_DAYS = 370;
// Plain names for the series a visitor picks from.
const nice = (s) => (s.derived ? "All solar" : [...FUELS, ...SOLAR_PARTS].find((x) => x.key === s.key)?.label || s.name);

export async function render(main, { meta, isCurrent }) {
  // Solar farms (60+ series) have their own table; they are not offered as the page's main series.
  const solarSeries = meta.series.filter((s) => (s.category === "solar" && s.dataset !== "solar_farms") || s.key === "generation_mix.solar");
  const actuals = solarSeries.filter((s) => s.kind === "actual");
  const PROFILE = ["grid", "distribution", "nem", "fit", "selco"].map((k) => meta.series.find((s) => s.key === `solar_profile.${k}`)).filter(Boolean);
  const forecasts = solarSeries.filter((s) => s.kind === "forecast");
  const demand = meta.series.find((s) => s.key === "system_demand.demand");

  if (!actuals.length) {
    main.innerHTML = card({
      title: "No solar readings archived yet",
      body: emptyState("The solar archive is empty",
        "No solar observations have been collected. Once the collector runs successfully, solar generation from the GSO " +
        "generation-mix feed appears here. See <a href=\"#/status\">Collection Status</a> for what the collector is doing.", "☀"),
    });
    return;
  }

  // "All solar" = Grid + Distribution + NEM + FiT + SELCO, the same total as GSO's Solar page and the Solar Profile chart.
  // It is the default, so the cards describe the same thing as the chart next to them.
  if (PROFILE.length === 5) {
    const same = PROFILE.every((s) => s.latest_value != null && s.last === PROFILE[0].last);
    actuals.unshift({ key: "all", name: "All solar", derived: true, kind: "actual", unit: "MW", interval_s: PROFILE[0].interval_s || 600,
      verification: PROFILE[0].verification, first: PROFILE[0].first, last: same ? PROFILE[0].last : null,
      latest_value: same ? PROFILE.reduce((t, s) => t + s.latest_value, 0) : null });
  }
  const DEFAULT_PRIMARY = actuals[0].key === "all" ? "all" : "generation_mix.solar";
  const primary = actuals.find((s) => s.key === getParam("primary")) || actuals.find((s) => s.key === DEFAULT_PRIMARY) || actuals[0];
  const demo = meta.is_demo;

  const toolbarSlot = h("<div></div>");
  main.appendChild(toolbarSlot);

  const sourceBar = h(`<div class="toolbar">
      <label class="inline">Primary solar series
        <select name="primary">${actuals.map((s) => `<option value="${esc(s.key)}" ${s.key === primary.key ? "selected" : ""}>${esc(s.derived ? "All solar (Grid + Distribution + NEM + FiT + SELCO)" : nice(s))}</option>`).join("")}</select></label>
      <label class="inline"><input type="checkbox" name="demand" ${!demand ? "disabled" : getParam("demand") === "0" ? "" : "checked"}> Overlay system demand</label>
      <span class="grow"></span>
      <span id="solar-tags" class="small"></span>
    </div>`);
  main.appendChild(sourceBar);

  const body = h('<div class="grid"></div>');
  main.appendChild(body);

  let current = { primaryKey: primary.key, overlay: !!demand && getParam("demand") !== "0" };
  let range = null;

  const picker = rangePicker(toolbarSlot, {
    initial: "7d",
    presets: ["1d", "2d", "7d", "30d", "90d", "1y", "all"],
    onChange: (r) => { range = r; return draw(); },
  });
  picker.firstDay = primary.first ? new Date(Date.parse(primary.first) + 8 * 3600e3).toISOString().slice(0, 10) : null;
  sourceBar.querySelector('[name="primary"]').addEventListener("change", (e) => {
    current.primaryKey = e.target.value;
    setParams({ primary: current.primaryKey === DEFAULT_PRIMARY ? null : current.primaryKey });
    draw();
  });
  sourceBar.querySelector('[name="demand"]').addEventListener("change", (e) => {
    current.overlay = e.target.checked;
    setParams({ demand: current.overlay ? null : "0" });
    draw();
  });

  async function draw() {
    const p = actuals.find((s) => s.key === current.primaryKey);
    sourceBar.querySelector("#solar-tags").innerHTML = `${verificationTag(p.verification)} ${p.auto_discovered ? '<span class="tag unverified">auto-discovered field</span>' : ""} ${freshnessPill(p.last, p.interval_s)}`;
    const start = mytDayStart(range.startDay), end = mytDayStart(addDays(range.endDay, 1));
    const days = Math.round((end - start) / 864e5);
    const rawOk = days <= RAW_LIMIT_DAYS;
    body.innerHTML = loading(120) + loading(400);
    try {
      const others = [];
      const [pts0, daily0, dem, fc, comps, prof] = await Promise.all([
        rawOk && !p.derived ? getPoints(p.key, start, end) : null,
        p.derived ? null : getDaily(p.key, range.startDay, range.endDay),
        rawOk && demand ? getPoints(demand.key, start, end) : null,
        rawOk ? Promise.all(forecasts.map((f) => getPoints(f.key, start, end))) : [],
        rawOk ? Promise.all(others.map((c) => getPoints(c.key, start, end))) : [],
        rawOk || p.derived ? Promise.all(PROFILE.map((c) => getPoints(c.key, start, end))) : [],
      ]);
      if (!isCurrent()) return;
      // All solar: add the five parts up at each moment (a moment missing any part stays a gap) and work out the daily figures.
      const pts = p.derived ? { series: "solar_total (derived: grid+distribution+nem+fit+selco)", unit: "MW", is_demo: meta.is_demo, points: sumSeries(prof.map((x) => x.points)), interval_s: p.interval_s } : pts0;
      const daily = p.derived ? dailyFromPoints(pts.points, p.interval_s, range.startDay, range.endDay) : daily0;
      await layout({ p, pts, daily, dem, fc, comps, others, prof, rawOk, days });
    } catch (err) {
      body.innerHTML = errorState(err);
    }
  }

  async function layout({ p, pts, daily, dem, fc, comps, others, prof, rawOk, days }) {
    const rows = daily.rows;
    const withData = rows.filter((r) => r.count);
    const points = pts ? pts.points : [];
    const peakDay = withData.reduce((b, r) => (b && b.max >= r.max ? b : r), null);
    const energy = withData.reduce((s, r) => s + (r.energy_mwh || 0), 0);
    // Only days since this series began to be archived: GSO's Solar page shows today only, so earlier days can never
    // be filled and would make a fully collected day look incomplete.
    const since = p.first ? new Date(Date.parse(p.first) + 8 * 3600e3).toISOString().slice(0, 10) : null;
    const counted = rows.filter((r) => !since || r.date >= since);
    const completeness = counted.length ? counted.reduce((s, r) => s + r.completeness, 0) / counted.length : 0;
    const rampPts = rawOk ? ramps(points, pts.interval_s || p.interval_s) : [];
    const rampExt = extent(rampPts);
    const share = rawOk && dem ? combine(points, dem.points, (s, d) => (d > 0 ? (100 * s) / d : null)) : [];
    const shareExt = extent(share);

    body.innerHTML = "";
    body.appendChild(h(`<div class="grid kpis">
      ${kpi({ big: true, icon: "solar", label: p.derived ? "Current Solar Generation" : `Latest ${nice(p)}`, cls: "solar", value: p.latest_value != null ? fmtNum(p.latest_value) : null, unit: "MW",
        meta: p.last ? `Observed ${fmtDateTime(p.last)} MYT` : "No readings yet" })}
      ${kpi({ big: true, icon: "peak", label: p.derived ? "Peak Solar Generation" : `Peak ${nice(p)}`, cls: "solar", value: peakDay ? fmtNum(peakDay.max) : null, unit: "MW",
        meta: peakDay ? `${fmtDate(peakDay.max_time)} at ${fmtTime(peakDay.max_time)}` : "" })}
      ${kpi({ icon: "energy", label: p.derived ? "Solar Energy" : `${nice(p)} Energy`, cls: "solar", value: withData.length ? fmtEnergy(energy) : null,
        meta: `${withData.length} of ${rows.length} days with readings, worked out from the readings` })}
      ${kpi({ icon: "rise", label: "Fastest Ramp-Up", value: rampExt.max ? `+${fmtNum(rampExt.max[1], 1)}` : null, unit: "MW/min",
        meta: rampExt.min ? `Fastest fall ${fmtNum(rampExt.min[1], 1)} MW/min` : rawOk ? "Not enough consecutive readings" : "Shorten the range to compute ramps" })}
      ${kpi({ icon: "share", label: "Peak Solar Share", value: shareExt.max ? fmtNum(shareExt.max[1], 1) : null, unit: "%",
        meta: shareExt.max ? `${fmtDateTime(shareExt.max[0])} MYT` : demand ? "Needs overlapping demand data" : "Demand not archived" })}
      ${kpi({ icon: "check", label: "Data Completeness", value: fmtNum(completeness * 100, 1), unit: "%", meta: `Readings archived ÷ readings GSO has published (one every 10 minutes)${since && since > range.startDay ? `, since collection began on ${fmtDate(since)}` : ""}` })}
    </div>`));
    body.appendChild(h(shortForms(["MW", "MWh", "MW/min", "MYT", "Grid", "Distribution", "NEM", "FiT", "SELCO", "LSS"])));

    // ---- GSO Solar page: solar by connection, with GSO's forecast
    const profileTotal = prof.length === 5 ? sumSeries(prof.map((x) => x.points)) : [];
    const gsoCard = h(card({ title: "Solar Profile",
      sub: "From GSO's Solar page",
      desc: "Each colour is one kind of solar, stacked so the top edge is total solar. Grid and Distribution are measured; NEM, FiT and SELCO are GSO's estimates. Dashed green line: GSO's Forecast.",
      body: '<div class="chart tall"></div>' }));
    body.appendChild(gsoCard);
    if (prof.length && prof.some((x) => x.points.some((q) => q[1] != null))) {
      const part = (k) => SOLAR_PARTS.find((x) => x.key === k) || { label: k, color: COLORS.solar };
      const series = prof.map((x, i) => ({ name: part(PROFILE[i].key).label, points: x.points, color: part(PROFILE[i].key).color, area: true, areaOpacity: 0.85, stack: "gso", width: 0.6 }));
      if (fc.length) series.push({ name: "Forecast", points: fc[0].points, color: COLORS.forecast, dashed: true, width: 2 });
      timeChart(gsoCard.querySelector(".chart"), { series, demo });
    } else {
      gsoCard.querySelector(".card-b").innerHTML = emptyState(rawOk ? "No readings from GSO's Solar page in this range" : "Shorten the range",
        "GSO's Solar page only publishes today's values, so this archive has them from the day collection started.", "◌");
    }

    // ---- main time-series
    const xlKeys = p.derived ? PROFILE.map((x) => x.key) : [p.key];
    const main1 = h(card({ title: "Solar Generation vs System Demand", cls: "", desc: current.overlay && dem ? "Yellow area: solar (left scale). Blue line: System Demand, the electricity Peninsular Malaysia is using (right scale). Breaks mean no reading, never zero." : "Yellow area: solar generation. Breaks mean no reading, never zero.", sub: rawOk ? `${fmtNum(points.filter((x) => x[1] != null).length)} readings · gaps shown as breaks` : "",
      right: `<button class="btn" data-act="csv">CSV</button>${exportUrl(xlKeys, range.startDay, range.endDay, "xlsx") ? `<a class="btn" href="${esc(exportUrl([...xlKeys, ...(demand ? [demand.key] : [])], range.startDay, range.endDay, "xlsx"))}">Excel</a>` : ""}`,
      body: rawOk ? '<div class="chart tall"></div>' : `<div class="notice">The selected range is ${days} days. Raw readings are charted for ranges up to ${RAW_LIMIT_DAYS} days; daily statistics are shown below.</div>` }));
    body.appendChild(main1);
    if (rawOk) {
      const series = [{ name: nice(p), points, color: COLORS.solar, area: true, width: 2 }];
      const palette = [COLORS.solar3, COLORS.solar2, COLORS.cogen];
      comps.forEach((c, i) => series.push({ name: others[i].name, points: c.points, color: palette[i % palette.length], width: 1.4 }));
      // GSO's forecast is for total solar (incl. rooftop); it is compared with the matching total in the cards below.
      const yAxes = [{ name: "MW" }];
      if (current.overlay && dem) { series.push({ name: "System Demand", points: dem.points, color: COLORS.demand, yAxisIndex: 1, width: 1.6 }); yAxes.push({ name: "Demand MW" }); }
      if (points.every((x) => x[1] == null)) main1.querySelector(".card-b").innerHTML = emptyState("No solar readings in this range", "Try a different range. Gaps are never filled with zero.");
      else timeChart(main1.querySelector(".chart"), { series, yAxes, demo });
      main1.querySelector('[data-act="csv"]').addEventListener("click", () => {
        downloadText(`solar_${range.startDay}_${range.endDay}.csv`, pointsToCsv([pts, ...comps, ...(current.overlay && dem ? [dem] : [])]));
      });
    } else {
      main1.querySelector('[data-act="csv"]').disabled = true;
    }

    // ---- daily peak & energy + share
    const row2 = h('<div class="grid cols-2"></div>');
    body.appendChild(row2);
    const dailyCard = h(card({ title: "Daily Peak & Energy", desc: "Bars: the highest solar output each day. Line: total solar energy that day (MWh).", body: '<div class="chart"></div>' }));
    row2.appendChild(dailyCard);
    if (withData.length) {
      categoryChart(dailyCard.querySelector(".chart"), {
        categories: rows.map((r) => r.date.slice(5)), demo, zoom: rows.length > 45,
        yAxes: [{ name: "Peak MW" }, { name: "MWh" }],
        series: [
          { name: "Daily peak", data: rows.map((r) => r.max), color: COLORS.solar, unit: "MW" },
          { name: "Daily energy", type: "line", data: rows.map((r) => r.energy_mwh), color: COLORS.solar3, yAxisIndex: 1, unit: "MWh" },
        ],
        tooltipExtra: (i) => rows[i].max_time ? `Peak at ${fmtTime(rows[i].max_time)} MYT · completeness ${fmtNum(rows[i].completeness * 100, 0)}%` : "No readings",
      });
    } else dailyCard.querySelector(".card-b").innerHTML = emptyState("No daily statistics in this range");

    const shareCard = h(card({ title: "Solar Share of System Demand", desc: "Solar as a percentage of System Demand at the same moment. Higher means more of the country runs on sunshine.", body: '<div class="chart"></div>' }));
    row2.appendChild(shareCard);
    if (share.some((x) => x[1] != null)) timeChart(shareCard.querySelector(".chart"), { series: [{ name: "Solar share", points: share, color: COLORS.solar, area: true, unit: "%" }], yAxes: [{ name: "%", digits: 0 }], demo, unit: "%", digits: 1 });
    else shareCard.querySelector(".card-b").innerHTML = emptyState(rawOk ? "Not enough overlapping data" : "Range too long", demand ? "Needs solar and demand readings at the same timestamps." : "System demand has not been archived yet.");

    // ---- forecast vs actual & transmission vs distribution
    const row4 = h('<div class="grid cols-2"></div>');
    body.appendChild(row4);
    const actualForFc = profileTotal.some((q) => q[1] != null) ? profileTotal : points;
    const fcCard = h(card({ title: "Forecast vs Actual", desc: "Yellow: actual solar (Grid + Distribution + NEM + FiT + SELCO). Dashed green: GSO's Forecast. The closer they are, the better the forecast.", sub: "", body: '<div class="chart"></div><div class="stat-row fc-stats" style="margin-top:8px"></div>' }));
    row4.appendChild(fcCard);
    if (fc.length && fc[0].points.length) {
      timeChart(fcCard.querySelector(".chart"), { demo, series: [
        { name: "Actual", points: actualForFc, color: COLORS.solar, area: true },
        { name: "Forecast", points: fc[0].points, color: COLORS.forecast, dashed: true, width: 2 },
      ] });
      const err = forecastError(actualForFc, fc[0].points);
      fcCard.querySelector(".fc-stats").innerHTML = err
        ? `<span>Typical miss <b>${fmtNum(err.mae, 0)} MW</b></span><span>Actual was on average <b>${fmtNum(Math.abs(err.bias), 0)} MW</b> ${err.bias >= 0 ? "below" : "above"} the forecast</span><span class="muted">${fmtNum(err.n)} times compared</span>${fc[0].issue_time_inferred ? '<span class="muted">Issue time = archive collection time (GSO gives none)</span>' : ""}`
        : '<span class="muted">No overlapping timestamps to score.</span>';
    } else {
      fcCard.querySelector(".card-b").innerHTML = emptyState("No solar forecast in this range",
        "GSO's Solar page publishes today's forecast; the archive keeps each day's forecast from when collection started.", "◌");
    }

    const tdCard = h(card({ title: "Grid vs Distribution Solar", desc: "Grid: solar farms on the high-voltage transmission grid. Distribution: smaller solar feeding the local network near homes and businesses.", body: '<div class="chart"></div>' }));
    row4.appendChild(tdCard);
    const txi = PROFILE.findIndex((s) => s.key === "solar_profile.grid"), dxi = PROFILE.findIndex((s) => s.key === "solar_profile.distribution");
    if (rawOk && txi >= 0 && dxi >= 0 && prof[txi].points.some((q) => q[1] != null)) {
      timeChart(tdCard.querySelector(".chart"), { demo, series: [
        { name: SOLAR_PARTS[0].label, points: prof[txi].points, color: "#F26B38", area: true, areaOpacity: 0.7, stack: "td" },
        { name: SOLAR_PARTS[1].label, points: prof[dxi].points, color: COLORS.solar2, area: true, areaOpacity: 0.7, stack: "td" },
      ] });
    } else {
      tdCard.querySelector(".card-b").innerHTML = emptyState("No split in this range",
        rawOk ? "The split comes from GSO's Solar page, which publishes today only." : "Shorten the range to view the split.", "◌");
    }

    // ---- solar farms right now (GSO solar map)
    const farms = meta.series.filter((s) => s.dataset === "solar_farms" && s.kind === "actual");
    if (farms.length) {
      const capOf = Object.fromEntries(meta.series.filter((s) => s.dataset === "solar_farms" && s.kind === "capacity").map((s) => [s.key.replace(/_capacity$/, ""), s.latest_value]));
      const rows2 = farms.map((s) => {
        const m = s.name.match(/Solar farm (\S+) \(([^,]+), ([^,]+), ([^)]+)\)/) || [];
        const cap = capOf[s.key];
        return { code: m[1] || s.key, state: m[2] || "", region: m[3] || "", conn: m[4] || "", mw: s.latest_value, cap,
                 pct: cap && s.latest_value != null ? (100 * s.latest_value) / cap : null, last: s.last, key: s.key, lat: s.lat, lon: s.lon };
      }).sort((a, b) => (b.mw ?? -1) - (a.mw ?? -1));
      const totalMw = rows2.reduce((t, r) => t + (r.mw || 0), 0), totalCap = rows2.reduce((t, r) => t + (r.cap || 0), 0);
      const newest = rows2.map((r) => r.last).filter(Boolean).sort().pop();
      // GSO's solar map: each LSS farm at its place, coloured by how much of its capacity it is producing.
      const regions = ["North", "Central", "South", "East"].map((name) => {
        const rs = rows2.filter((r) => r.region === name);
        const mw = rs.reduce((t, r) => t + (r.mw || 0), 0), cap = rs.reduce((t, r) => t + (r.cap || 0), 0);
        return { name, n: rs.length, mw, cap };
      }).filter((r) => r.n);
      const mapCard = h(card({ title: "Solar Map (Peninsular Malaysia)", when: newest ? fmtLong(newest) : "",
        desc: "Each dot is one LSS solar farm on GSO's solar map, at its location. The colour shows how much of its capacity it is producing right now (grey = little or none, orange = close to full); bigger dots are bigger farms. Circles are grid-connected, diamonds distribution-connected. Drag or pinch to zoom.",
        body: `<div class="stat-row region-row">${regions.map((r) => `<span>${r.name} <b>${r.cap ? fmtNum((100 * r.mw) / r.cap, 0) : "—"}%</b> <small class="muted">${fmtNum(r.mw)} of ${fmtNum(r.cap)} MW</small></span>`).join("")}
          <span>All <b>${totalCap ? fmtNum((100 * totalMw) / totalCap, 0) : "—"}%</b> <small class="muted">${fmtNum(totalMw)} of ${fmtNum(totalCap)} MW, ${rows2.length} farms</small></span></div>
          <div class="chart map"></div>` }));
      body.appendChild(mapCard);
      if (!rows2.some((r) => r.lat != null)) mapCard.querySelector(".chart").innerHTML = emptyState("Farm locations not archived yet", "They are saved from GSO's solar map on the next collection.", "◌");
      else await solarMap(mapCard.querySelector(".chart"), { farms: rows2, demo }).catch((err) => { mapCard.querySelector(".chart").innerHTML = errorState(err); });
      const farmCard = h(card({ title: "LSS Solar Farms Now", desc: "Every solar farm on GSO's solar map, highest output first. \"Of capacity\" shows how hard each farm is working.",
        sub: `${rows2.length} farms · ${fmtNum(totalMw)} MW of ${fmtNum(totalCap)} MW capacity`,
        body: '<div class="tbl"></div>' }));
      body.appendChild(farmCard);
      renderTable(farmCard.querySelector(".tbl"), [
        { key: "code", label: "Farm", fmt: (v, r) => `<a class="mono" href="#/explorer?series=${encodeURIComponent(r.key)}">${esc(v)}</a>` },
        { key: "state", label: "State" }, { key: "region", label: "Region" }, { key: "conn", label: "Connected to" },
        { key: "mw", label: "Output (MW)", num: true, fmt: (v) => fmtNum(v) },
        { key: "cap", label: "Capacity (MW)", num: true, fmt: (v) => fmtNum(v) },
        { key: "pct", label: "Of capacity", num: true, fmt: (v) => (v == null ? "—" : `${fmtNum(v, 0)}%`) },
      ], rows2, 15);
    }

    body.appendChild(h(section("Deeper analysis", "How fast solar rises and falls, a typical day's shape, and totals by day, week, month or year.")));

    // ---- ramps & profiles
    const row3 = h('<div class="grid cols-2"></div>');
    body.appendChild(row3);
    const rampCard = h(card({ title: "Ramp Rate", desc: "Above zero: output rising (morning, clouds clearing). Below zero: falling (clouds, sunset). MW per minute.", body: '<div class="chart"></div>' }));
    row3.appendChild(rampCard);
    if (rampPts.some((x) => x[1] != null)) timeChart(rampCard.querySelector(".chart"), { series: [{ name: "Ramp", points: rampPts, color: COLORS.solar3, type: "bar", unit: "MW/min" }], yAxes: [{ name: "MW/min", digits: 1 }], demo, unit: "MW/min", digits: 2 });
    else rampCard.querySelector(".card-b").innerHTML = emptyState(rawOk ? "Not enough consecutive readings" : "Shorten the range to compute ramps");

    const profCard = h(card({ title: "Daily Profile", desc: "Solar generation by time of day. The darkest, thickest line is the most recent.", sub: days <= 10 ? "One line per day" : days <= 92 ? "One line per ISO week" : "One line per month", body: '<div class="chart"></div>' }));
    row3.appendChild(profCard);
    if (rawOk && points.some((x) => x[1] != null)) {
      const groupKey = days <= 10 ? (d) => d : days <= 92 ? (d) => { const r = rollup([{ date: d, count: 0, completeness: 0 }], "week"); return r[0].period; } : (d) => d.slice(0, 7);
      const groups = intradayProfiles(points, groupKey).slice(-12);
      const shades = groups.map((_, i) => `hsl(${35 - (groups.length - 1 - i) * 3}, ${60 + (i / Math.max(1, groups.length - 1)) * 35}%, ${68 - (i / Math.max(1, groups.length - 1)) * 28}%)`);
      profileChart(profCard.querySelector(".chart"), { groups: groups.map((g, i) => ({ name: g.key, data: g.data, color: shades[i], width: i === groups.length - 1 ? 2.4 : 1.3 })), demo });
    } else profCard.querySelector(".card-b").innerHTML = emptyState(rawOk ? "No readings" : "Shorten the range to see profiles");

    // ---- period comparison
    const cmp = h(card({ title: "Period Comparison", desc: "Pick a period to see its highest output (bars) and total energy (line).",
      right: '<div class="seg" role="group" aria-label="Period">' + ["day", "week", "month", "year"].map((x) => `<button type="button" data-period="${x}" aria-pressed="${x === (days > 120 ? "month" : days > 31 ? "week" : "day")}">${x[0].toUpperCase() + x.slice(1)}</button>`).join("") + "</div>",
      body: '<div class="chart short"></div><div class="tbl" style="margin-top:10px"></div>' }));
    body.appendChild(cmp);
    const defaultPeriod = days > 120 ? "month" : days > 31 ? "week" : "day";
    const drawCmp = (period) => {
      cmp.querySelectorAll("[data-period]").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.period === period)));
      const agg = rollup(rows, period);
      if (!agg.some((a) => a.max != null)) { cmp.querySelector(".chart").innerHTML = emptyState("No data"); return; }
      categoryChart(cmp.querySelector(".chart"), {
        categories: agg.map((a) => a.period), demo, zoom: agg.length > 60,
        yAxes: [{ name: "Peak MW" }, { name: "MWh" }],
        series: [
          { name: "Peak", data: agg.map((a) => a.max), color: COLORS.solar, unit: "MW" },
          { name: "Energy (derived)", type: "line", data: agg.map((a) => a.energy_mwh), color: COLORS.solar3, yAxisIndex: 1, unit: "MWh" },
        ],
      });
      renderTable(cmp.querySelector(".tbl"), [
        { key: "period", label: "Period" },
        { key: "max", label: "Peak (MW)", num: true, fmt: (v) => fmtNum(v) },
        { key: "max_time", label: "Peak time (MYT)", fmt: (v) => (v ? fmtDateTime(v) : "—") },
        { key: "mean_daily_peak", label: "Mean daily peak (MW)", num: true, fmt: (v) => fmtNum(v) },
        { key: "energy_mwh", label: "Energy (MWh, derived)", num: true, fmt: (v) => fmtNum(v) },
        { key: "days_with_data", label: "Days with data", num: true },
        { key: "completeness", label: "Completeness", num: true, fmt: (v) => `${fmtNum(v * 100, 1)}%` },
      ], agg.slice().reverse(), 12);
    };
    cmp.querySelectorAll("[data-period]").forEach((b) => b.addEventListener("click", () => {
      setParams({ period: b.dataset.period === defaultPeriod ? null : b.dataset.period });
      drawCmp(b.dataset.period);
    }));
    drawCmp(["day", "week", "month", "year"].includes(getParam("period")) ? getParam("period") : defaultPeriod);

    // ---- completeness + table
    const tbl = h(card({ title: "Daily Statistics", sub: "Malaysia time", desc: "One row per day. Darker cells in the strip mean more of that day's readings were collected.",
      right: `<button class="btn" data-act="dcsv">Download CSV</button>`,
      body: `<div class="strip" aria-label="Daily completeness">${rows.map((r) => `<span title="${r.date}: ${fmtNum(r.completeness * 100, 0)}% complete" style="background:${r.count ? `color-mix(in srgb, ${getComputedStyle(document.documentElement).getPropertyValue("--solar")} ${Math.round(25 + r.completeness * 75)}%, transparent)` : ""}"></span>`).join("")}</div>
             <p class="small muted">Each cell is one day; empty cells mean no archived readings (not zero output).</p><div class="tbl"></div>` }));
    body.appendChild(tbl);
    renderTable(tbl.querySelector(".tbl"), [
      { key: "date", label: "Date" },
      { key: "max", label: "Peak (MW)", num: true, fmt: (v) => fmtNum(v) },
      { key: "max_time", label: "Peak time", fmt: (v) => fmtTime(v) },
      { key: "mean", label: "Mean (MW)", num: true, fmt: (v) => fmtNum(v) },
      { key: "energy_mwh", label: "Energy (MWh, derived)", num: true, fmt: (v) => fmtNum(v) },
      { key: "count", label: "Readings", num: true },
      { key: "completeness", label: "Completeness", num: true, fmt: (v) => `${fmtNum(v * 100, 1)}%` },
    ], rows.slice().reverse(), 31);
    tbl.querySelector('[data-act="dcsv"]').addEventListener("click", () => {
      const head = "date,peak_mw,peak_time_utc,mean_mw,min_mw,energy_mwh_derived,readings,expected,completeness";
      const lines = rows.map((r) => [r.date, r.max ?? "", r.max_time ?? "", r.mean ?? "", r.min ?? "", r.energy_mwh ?? "", r.count, r.expected, r.completeness].join(","));
      downloadText(`solar_daily_${p.key}_${range.startDay}_${range.endDay}.csv`, [head, ...lines].join("\n") + "\n");
    });
  }

  await picker.start();
}
