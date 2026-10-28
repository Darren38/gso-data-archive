// Solar dashboard: the archive's primary page.
import { getDaily, getPoints, exportUrl, rollup } from "../data.js";
import { COLORS, categoryChart, profileChart, timeChart } from "../charts.js";
import { combine, extent, forecastError, intradayProfiles, ramps, sumSeries } from "../analysis.js";
import {
  addDays, card, downloadText, emptyState, errorState, esc, fmtDate, fmtDateTime, fmtEnergy, fmtNum, fmtTime,
  freshnessPill, getParam, h, kpi, loading, mytDayStart, pointsToCsv, rangePicker, renderTable, setParams, verificationTag,
} from "../ui.js";

const RAW_LIMIT_DAYS = 370;

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

  const primary = actuals.find((s) => s.key === getParam("primary")) || actuals.find((s) => s.key === "generation_mix.solar") || actuals[0];
  const demo = meta.is_demo;

  const toolbarSlot = h("<div></div>");
  main.appendChild(toolbarSlot);

  const sourceBar = h(`<div class="toolbar">
      <label class="inline">Primary solar series
        <select name="primary">${actuals.map((s) => `<option value="${esc(s.key)}" ${s.key === primary.key ? "selected" : ""}>${esc(s.name)}</option>`).join("")}</select></label>
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
    setParams({ primary: current.primaryKey === "generation_mix.solar" ? null : current.primaryKey });
    draw();
  });
  sourceBar.querySelector('[name="demand"]').addEventListener("change", (e) => {
    current.overlay = e.target.checked;
    setParams({ demand: current.overlay ? null : "0" });
    draw();
  });

  async function draw() {
    const p = meta.series.find((s) => s.key === current.primaryKey);
    sourceBar.querySelector("#solar-tags").innerHTML = `${verificationTag(p.verification)} ${p.auto_discovered ? '<span class="tag unverified">auto-discovered field</span>' : ""} ${freshnessPill(p.last, p.interval_s)}`;
    const start = mytDayStart(range.startDay), end = mytDayStart(addDays(range.endDay, 1));
    const days = Math.round((end - start) / 864e5);
    const rawOk = days <= RAW_LIMIT_DAYS;
    body.innerHTML = loading(120) + loading(400);
    try {
      const others = [];
      const [pts, daily, dem, fc, comps, prof] = await Promise.all([
        rawOk ? getPoints(p.key, start, end) : null,
        getDaily(p.key, range.startDay, range.endDay),
        rawOk && demand ? getPoints(demand.key, start, end) : null,
        rawOk ? Promise.all(forecasts.map((f) => getPoints(f.key, start, end))) : [],
        rawOk ? Promise.all(others.map((c) => getPoints(c.key, start, end))) : [],
        rawOk ? Promise.all(PROFILE.map((c) => getPoints(c.key, start, end))) : [],
      ]);
      if (!isCurrent()) return;
      layout({ p, pts, daily, dem, fc, comps, others, prof, rawOk, days });
    } catch (err) {
      body.innerHTML = errorState(err);
    }
  }

  function layout({ p, pts, daily, dem, fc, comps, others, prof, rawOk, days }) {
    const rows = daily.rows;
    const withData = rows.filter((r) => r.count);
    const points = pts ? pts.points : [];
    const peakDay = withData.reduce((b, r) => (b && b.max >= r.max ? b : r), null);
    const energy = withData.reduce((s, r) => s + (r.energy_mwh || 0), 0);
    const avgPeak = withData.length ? withData.reduce((s, r) => s + r.max, 0) / withData.length : null;
    const completeness = rows.length ? rows.reduce((s, r) => s + r.completeness, 0) / rows.length : 0;
    const rampPts = rawOk ? ramps(points, pts.interval_s || p.interval_s) : [];
    const rampExt = extent(rampPts);
    const share = rawOk && dem ? combine(points, dem.points, (s, d) => (d > 0 ? (100 * s) / d : null)) : [];
    const shareExt = extent(share);

    body.innerHTML = "";
    body.appendChild(h(`<div class="grid kpis">
      ${kpi({ label: "Latest reading", cls: "solar", value: p.latest_value != null ? fmtNum(p.latest_value) : null, unit: "MW",
        meta: p.last ? `Observed ${fmtDateTime(p.last)} MYT` : "No readings yet" })}
      ${kpi({ label: "Peak in range", cls: "solar", value: peakDay ? fmtNum(peakDay.max) : null, unit: "MW",
        meta: peakDay ? `${fmtDate(peakDay.max_time)} at ${fmtTime(peakDay.max_time)}` : "" })}
      ${kpi({ label: "Energy in range", cls: "solar", value: withData.length ? fmtEnergy(energy) : null,
        meta: "Derived: trapezoidal integral of archived readings" })}
      ${kpi({ label: "Average daily peak", value: avgPeak != null ? fmtNum(avgPeak) : null, unit: "MW", meta: `${withData.length} of ${rows.length} days with data` })}
      ${kpi({ label: "Steepest up-ramp", value: rampExt.max ? `+${fmtNum(rampExt.max[1], 1)}` : null, unit: "MW/min",
        meta: rampExt.min ? `Steepest fall ${fmtNum(rampExt.min[1], 1)} MW/min · derived` : rawOk ? "Not enough consecutive readings" : "Shorten the range to compute ramps" })}
      ${kpi({ label: "Peak share of demand", value: shareExt.max ? fmtNum(shareExt.max[1], 1) : null, unit: "%",
        meta: shareExt.max ? `${fmtDateTime(shareExt.max[0])} MYT · derived` : demand ? "Needs overlapping demand data" : "Demand not archived" })}
      ${kpi({ label: "Data completeness", value: fmtNum(completeness * 100, 1), unit: "%", meta: `Expected ${rows[0] ? rows[0].expected : "—"} readings/day` })}
    </div>`));

    // ---- main time-series
    const main1 = h(card({ title: "Solar generation", cls: "", sub: rawOk ? `${fmtNum(points.filter((x) => x[1] != null).length)} readings · gaps shown as breaks` : "",
      right: `<button class="btn" data-act="csv">CSV</button>${exportUrl([p.key], range.startDay, range.endDay, "xlsx") ? `<a class="btn" href="${esc(exportUrl([p.key, ...(demand ? [demand.key] : [])], range.startDay, range.endDay, "xlsx"))}">Excel</a>` : ""}`,
      body: rawOk ? '<div class="chart tall"></div>' : `<div class="notice">The selected range is ${days} days. Raw readings are charted for ranges up to ${RAW_LIMIT_DAYS} days; daily statistics are shown below.</div>` }));
    body.appendChild(main1);
    if (rawOk) {
      const series = [{ name: p.name, points, color: COLORS.solar, area: true, width: 2 }];
      const palette = [COLORS.solar3, COLORS.solar2, COLORS.cogen];
      comps.forEach((c, i) => series.push({ name: others[i].name, points: c.points, color: palette[i % palette.length], width: 1.4 }));
      // GSO's forecast is for total solar (incl. rooftop); it is compared with the matching total in the cards below.
      const yAxes = [{ name: "MW" }];
      if (current.overlay && dem) { series.push({ name: "System demand", points: dem.points, color: COLORS.demand, yAxisIndex: 1, width: 1.2 }); yAxes.push({ name: "Demand MW" }); }
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
    const dailyCard = h(card({ title: "Daily peak & energy", sub: "Energy is derived (MWh)", body: '<div class="chart"></div>' }));
    row2.appendChild(dailyCard);
    if (withData.length) {
      categoryChart(dailyCard.querySelector(".chart"), {
        categories: rows.map((r) => r.date.slice(5)), demo, zoom: rows.length > 45,
        yAxes: [{ name: "Peak MW" }, { name: "MWh" }],
        series: [
          { name: "Daily peak", data: rows.map((r) => r.max), color: COLORS.solar, unit: "MW" },
          { name: "Daily energy (derived)", type: "line", data: rows.map((r) => r.energy_mwh), color: COLORS.solar3, yAxisIndex: 1, unit: "MWh" },
        ],
        tooltipExtra: (i) => rows[i].max_time ? `Peak at ${fmtTime(rows[i].max_time)} MYT · completeness ${fmtNum(rows[i].completeness * 100, 0)}%` : "No readings",
      });
    } else dailyCard.querySelector(".card-b").innerHTML = emptyState("No daily statistics in this range");

    const shareCard = h(card({ title: "Solar share of system demand", sub: "Derived: solar ÷ demand at matching timestamps", body: '<div class="chart"></div>' }));
    row2.appendChild(shareCard);
    if (share.some((x) => x[1] != null)) timeChart(shareCard.querySelector(".chart"), { series: [{ name: "Solar share", points: share, color: COLORS.solar, area: true, unit: "%" }], yAxes: [{ name: "%", digits: 0 }], demo, unit: "%", digits: 1 });
    else shareCard.querySelector(".card-b").innerHTML = emptyState(rawOk ? "Not enough overlapping data" : "Range too long", demand ? "Needs solar and demand readings at the same timestamps." : "System demand has not been archived yet.");

    // ---- ramps & profiles
    const row3 = h('<div class="grid cols-2"></div>');
    body.appendChild(row3);
    const rampCard = h(card({ title: "Ramp rate", sub: "MW per minute between consecutive readings (derived)", body: '<div class="chart"></div>' }));
    row3.appendChild(rampCard);
    if (rampPts.some((x) => x[1] != null)) timeChart(rampCard.querySelector(".chart"), { series: [{ name: "Ramp", points: rampPts, color: COLORS.solar3, type: "bar", unit: "MW/min" }], yAxes: [{ name: "MW/min", digits: 1 }], demo, unit: "MW/min", digits: 2 });
    else rampCard.querySelector(".card-b").innerHTML = emptyState(rawOk ? "Not enough consecutive readings" : "Shorten the range to compute ramps");

    const profCard = h(card({ title: "Average intraday profile", sub: days <= 10 ? "One line per day" : days <= 92 ? "One line per ISO week" : "One line per month", body: '<div class="chart"></div>' }));
    row3.appendChild(profCard);
    if (rawOk && points.some((x) => x[1] != null)) {
      const groupKey = days <= 10 ? (d) => d : days <= 92 ? (d) => { const r = rollup([{ date: d, count: 0, completeness: 0 }], "week"); return r[0].period; } : (d) => d.slice(0, 7);
      const groups = intradayProfiles(points, groupKey).slice(-12);
      const shades = groups.map((_, i) => `hsl(${35 - (groups.length - 1 - i) * 3}, ${60 + (i / Math.max(1, groups.length - 1)) * 35}%, ${68 - (i / Math.max(1, groups.length - 1)) * 28}%)`);
      profileChart(profCard.querySelector(".chart"), { groups: groups.map((g, i) => ({ name: g.key, data: g.data, color: shades[i], width: i === groups.length - 1 ? 2.4 : 1.3 })), demo });
    } else profCard.querySelector(".card-b").innerHTML = emptyState(rawOk ? "No readings" : "Shorten the range to see profiles");

    // ---- period comparison
    const cmp = h(card({ title: "Period comparison", sub: "Peak and energy by period",
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

    // ---- GSO Solar page: solar by connection, with GSO's forecast
    const profileTotal = prof.length === 5 ? sumSeries(prof.map((x) => x.points)) : [];
    const gsoCard = h(card({ title: "Solar by connection (GSO Solar page)",
      sub: "Grid and distribution solar as measured; NEM, FiT and SELCO rooftop values are GSO's own estimates",
      body: '<div class="chart tall"></div>' }));
    body.appendChild(gsoCard);
    if (prof.length && prof.some((x) => x.points.some((q) => q[1] != null))) {
      const shades = [COLORS.solar3, COLORS.solar, COLORS.solar2, "#f3d27a", "#c9a227"];
      const series = prof.map((x, i) => ({ name: PROFILE[i].name, points: x.points, color: shades[i], area: true, areaOpacity: i > 1 ? 0.35 : 0.6, stack: "gso", width: 0.8 }));
      if (fc.length) series.push({ name: "GSO forecast (total)", points: fc[0].points, color: COLORS.forecast, dashed: true, width: 1.6 });
      timeChart(gsoCard.querySelector(".chart"), { series, demo });
    } else {
      gsoCard.querySelector(".card-b").innerHTML = emptyState(rawOk ? "No readings from GSO's Solar page in this range" : "Shorten the range",
        "GSO's Solar page only publishes today's values, so this archive has them from the day collection started.", "◌");
    }

    // ---- forecast vs actual & transmission vs distribution
    const row4 = h('<div class="grid cols-2"></div>');
    body.appendChild(row4);
    const actualForFc = profileTotal.some((q) => q[1] != null) ? profileTotal : points;
    const fcCard = h(card({ title: "Forecast vs actual", sub: actualForFc === profileTotal ? "Actual = total of GSO's five solar series (derived)" : "", body: '<div class="chart"></div><div class="stat-row fc-stats" style="margin-top:8px"></div>' }));
    row4.appendChild(fcCard);
    if (fc.length && fc[0].points.length) {
      timeChart(fcCard.querySelector(".chart"), { demo, series: [
        { name: "Actual", points: actualForFc, color: COLORS.solar, area: true },
        { name: "Forecast (latest issue)", points: fc[0].points, color: COLORS.forecast, dashed: true },
      ] });
      const err = forecastError(actualForFc, fc[0].points);
      fcCard.querySelector(".fc-stats").innerHTML = err
        ? `<span>Matched points <b>${fmtNum(err.n)}</b></span><span>MAE <b>${fmtNum(err.mae, 1)} MW</b></span><span>RMSE <b>${fmtNum(err.rmse, 1)} MW</b></span><span>Bias <b>${fmtNum(err.bias, 1)} MW</b></span>${fc[0].issue_time_inferred ? '<span class="muted">Issue time = archive collection time (GSO gives none)</span>' : ""}`
        : '<span class="muted">No overlapping timestamps to score.</span>';
    } else {
      fcCard.querySelector(".card-b").innerHTML = emptyState("No solar forecast in this range",
        "GSO's Solar page publishes today's forecast; the archive keeps each day's forecast from when collection started.", "◌");
    }

    const tdCard = h(card({ title: "Transmission vs distribution solar", body: '<div class="chart"></div>' }));
    row4.appendChild(tdCard);
    const txi = PROFILE.findIndex((s) => s.key === "solar_profile.grid"), dxi = PROFILE.findIndex((s) => s.key === "solar_profile.distribution");
    if (rawOk && txi >= 0 && dxi >= 0 && prof[txi].points.some((q) => q[1] != null)) {
      timeChart(tdCard.querySelector(".chart"), { demo, series: [
        { name: PROFILE[txi].name, points: prof[txi].points, color: COLORS.solar3, area: true, stack: "td" },
        { name: PROFILE[dxi].name, points: prof[dxi].points, color: COLORS.solar2, area: true, stack: "td" },
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
                 pct: cap ? (100 * s.latest_value) / cap : null, last: s.last, key: s.key };
      }).sort((a, b) => (b.mw ?? -1) - (a.mw ?? -1));
      const totalMw = rows2.reduce((t, r) => t + (r.mw || 0), 0), totalCap = rows2.reduce((t, r) => t + (r.cap || 0), 0);
      const farmCard = h(card({ title: "Solar farms right now (GSO solar map)",
        sub: `${rows2.length} farms · ${fmtNum(totalMw)} MW of ${fmtNum(totalCap)} MW capacity · ${rows2[0].last ? fmtDateTime(rows2[0].last) + " MYT" : ""}`,
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

    // ---- completeness + table
    const tbl = h(card({ title: "Daily statistics", sub: "Calendar days in MYT",
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
