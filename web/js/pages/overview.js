// Overview: a dashboard of the grid right now and today. Only archived GSO readings are shown, with their times.
import { getPoints, getStatus } from "../data.js";
import { COLORS, SOLAR_PARTS, FUELS, pieChart, timeChart } from "../charts.js";
import { fuelIcon } from "../icons.js";
import { extent, sumSeries } from "../analysis.js";
import { card, clock, esc, fmtDate, fmtLong, shortForms, emptyState, errorState, fmtAge, fmtDateTime, fmtNum, fmtTime, h, kpi, ageOf, mytDay, mytDayStart } from "../ui.js";

// GSO's home page "Generation Mix" and "Generation Availability" donuts, with GSO's names and colours.
const MIX = [...FUELS.slice(0, 5), { key: "genmix_live.tie_line_total", label: "Tie-Line", color: COLORS.tieline }, ...FUELS.slice(5)];
const AVAIL = [
  ["coal", "Coal", COLORS.coal], ["cogen", "Co-Gen", COLORS.cogen], ["gas", "Gas", COLORS.gas], ["hydro", "Hydro", COLORS.hydro],
  ["transmission_solar", "Transmission Solar", COLORS.gridSolar], ["distribution_solar", "Distribution Solar", COLORS.dnSolar], ["bess", "BESS", COLORS.bessDischarge],
].map(([k, label, color]) => ({ key: `availability.${k}`, label, color }));

/** The newest time at which every series has a reading, so the donut shows one moment (as GSO's does). */
function latestCommon(seriesPoints) {
  const maps = seriesPoints.map((pts) => new Map(pts.filter((p) => p[1] != null).map((p) => [Date.parse(p[0]), p[1]])));
  const times = [...maps[0].keys()].filter((t) => maps.every((m) => m.has(t))).sort((a, b) => b - a);
  return times.length ? { t: new Date(times[0]).toISOString(), values: maps.map((m) => m.get(times[0])) } : null;
}

export async function render(main, { meta, isCurrent }) {
  const by = Object.fromEntries(meta.series.map((s) => [s.key, s]));
  if (!meta.series.length) {
    main.innerHTML = card({ title: "Welcome", body: emptyState("Nothing archived yet",
      "No live values are shown until the collector has stored real GSO readings. " +
      "<a href=\"#/status\">Collection Status</a> shows whether collection is running.", "◧") });
    return;
  }

  // ---- right now
  const parts = SOLAR_PARTS.map((p) => by[p.key]).filter(Boolean);
  const partsNow = parts.length === SOLAR_PARTS.length && parts.every((s) => s.latest_value != null && s.last === parts[0].last);
  const solarNow = partsNow ? parts.reduce((t, s) => t + s.latest_value, 0) : by["generation_mix.solar"]?.latest_value ?? null;
  const solarAt = partsNow ? parts[0].last : by["generation_mix.solar"]?.last;
  const demand = by["system_demand.demand"];
  // Solar ÷ demand only for readings taken at the same moment (the two come from different GSO pages).
  const shareAt = (demandMw) => (solarNow != null && demandMw > 0 ? (100 * solarNow) / demandMw : null);
  const share = demand?.last === solarAt ? shareAt(demand.latest_value) : null;
  const shareKpi = (v) => kpi({ cls: "solar", icon: "share", label: "Solar Share of Demand", value: v != null ? fmtNum(v, 1) : null, unit: "%",
    meta: v != null ? `Current Solar Generation ÷ Grid Demand at ${fmtTime(solarAt)} MYT` : "Needs solar and demand readings for the same time" });
  // GSO's home page opens with "Current Grid Demand" and "Current System Demand" side by side. The first is the figure
  // on GSO's System Demand page (system_demand.demand, every 10 minutes); the second, larger, only on the home page.
  const sysDem = by["headlines.current_system_demand"];
  const dis = by["genmix_live.bess_discharge"], chg = by["genmix_live.bess_charge"];
  const bess = dis && chg && dis.latest_value != null && chg.latest_value != null ? dis.latest_value + chg.latest_value : null;
  const mixSeries = MIX.filter((m) => by[m.key]);
  const avSeries = AVAIL.filter((a) => by[a.key] && by[a.key].latest_value != null);

  main.appendChild(h(`<div class="grid kpis hero">
    ${kpi({ big: true, cls: "demand", icon: "demand", label: "Current Grid Demand", value: demand?.latest_value != null ? fmtNum(demand.latest_value) : null, unit: "MW",
      meta: demand?.last ? `${fmtDateTime(demand.last)} MYT · from GSO's System Demand page` : "" })}
    ${kpi({ big: true, cls: "demand", icon: "demand", label: "Current System Demand", value: sysDem?.latest_value != null ? fmtNum(sysDem.latest_value) : null, unit: "MW",
      meta: sysDem?.last ? `${fmtDateTime(sysDem.last)} MYT · from GSO's home page` : "Kept from 30 October 2026, when GSO's home page shows it" })}
    ${kpi({ big: true, cls: "solar", icon: "solar", label: "Current Solar Generation", value: solarNow != null ? fmtNum(solarNow) : null, unit: "MW",
      meta: solarAt ? `${partsNow ? "Grid + Distribution + NEM + FiT + SELCO" : "Transmission Solar"} · ${fmtTime(solarAt)} MYT` : "" })}
    ${kpi({ big: true, cls: "bess", icon: "battery", label: "Current BESS Status", value: bess != null ? fmtNum(Math.abs(bess)) : null, unit: "MW",
      meta: bess == null ? "" : bess > 0 ? "Discharging to the grid" : bess < 0 ? "Charging from the grid" : "Idle" })}
  </div>`));
  const second = h('<div class="grid kpis"></div>');
  main.appendChild(second);
  main.appendChild(h(shortForms(["MW", "MYT", "Grid", "Distribution", "NEM", "FiT", "SELCO", "BESS", "Co-Gen", "RE"])));

  // ---- today
  const today = mytDay(new Date());
  const start = mytDayStart(today), now = new Date();
  const chartToday = h(card({ title: "Solar Profile vs Forecast (today)",
    desc: "Each colour is one kind of solar (Grid, Distribution, NEM, FiT, SELCO), stacked so the top edge is total solar. Dashed green line: GSO's Forecast.",
    body: '<div class="chart tall"></div>' }));
  main.appendChild(chartToday);
  const row = h('<div class="grid cols-2"></div>');
  main.appendChild(row);
  const mixCard = h(card({ title: "Generation Mix", desc: "Share of each fuel in the electricity being generated. The middle shows the total.",
    body: '<div class="chart"></div>' }));
  const avCard = h(card({ title: "Generation Availability", desc: "Share of each kind of plant ready to run. The middle shows the total available.",
    body: '<div class="chart"></div>' }));
  const demCard = h(card({ title: "Grid Demand: Today vs Yesterday", desc: "The figure on GSO's System Demand page (GSO's home page calls it Current Grid Demand). Solid line: today. Dashed line: the same hours yesterday.", body: '<div class="chart"></div>' }));
  row.append(mixCard, avCard);
  main.appendChild(demCard);

  try {
    const fc = by["solar_forecast.total"];
    const [partPts, fcPts, solarPts, demToday, demYest, mixPts] = await Promise.all([
      parts.length ? Promise.all(parts.map((s) => getPoints(s.key, start, now))) : [],
      fc ? getPoints(fc.key, start, new Date(start.getTime() + 864e5)) : null,
      by["generation_mix.solar"] ? getPoints("generation_mix.solar", start, now) : null,
      demand ? getPoints(demand.key, start, now) : null,
      demand ? getPoints(demand.key, new Date(start.getTime() - 864e5), start) : null,
      Promise.all(mixSeries.map((m) => getPoints(m.key, new Date(start.getTime() - 864e5), now))),
    ]);
    if (!isCurrent()) return;

    let shareNow = share;
    if (shareNow == null && solarAt && demToday) {
      // The newest demand reading may be newer or older than the newest solar one: use demand at the solar reading's time.
      const d = [...(demYest?.points || []), ...demToday.points].find((p) => p[0] === solarAt || Date.parse(p[0]) === Date.parse(solarAt));
      if (d && d[1] != null) shareNow = shareAt(d[1]);
    }
    const totalToday = partPts.length === SOLAR_PARTS.length ? sumSeries(partPts.map((p) => p.points)) : solarPts?.points || [];
    const peak = extent(totalToday).max;
    const fcPeak = fcPts ? extent(fcPts.points).max : null;
    // One moment for the whole mix, like GSO's chart (the fuels and the extras come from two GSO pages).
    const snap = mixSeries.length ? latestCommon(mixPts.map((p) => p.points)) : null;
    const slices = snap ? mixSeries.map((m, i) => ({ ...m, value: snap.values[i] })).filter((m) => m.value > 0) : [];
    const mixTotal = slices.reduce((t, m) => t + m.value, 0);
    const biggest = slices.slice().sort((a, b) => b.value - a.value)[0];
    second.innerHTML = [
      shareKpi(shareNow),
      kpi({ cls: "solar", icon: "peak", label: "Today's Solar Peak", value: peak ? fmtNum(peak[1]) : null, unit: "MW", meta: peak ? `at ${fmtTime(peak[0])} MYT` : "" }),
      kpi({ cls: "forecast", icon: "forecast", label: "Solar Forecast Peak", value: fcPeak ? fmtNum(fcPeak[1]) : null, unit: "MW", meta: fcPeak ? `expected at ${fmtTime(fcPeak[0])} MYT` : "" }),
      kpi({ icon: biggest ? fuelIcon(biggest.key) : "plant", label: "Largest Source Now", value: biggest ? biggest.label : null, meta: biggest ? `${fmtNum((100 * biggest.value) / mixTotal, 0)}% of the Generation Mix · ${fmtNum(biggest.value)} MW` : "" }),
      kpi({ icon: "clock", label: "Latest GSO Reading", value: solarAt ? fmtTime(solarAt) : null,
        meta: solarAt ? `${fmtAge(ageOf(solarAt))}. GSO adds a reading every 10 minutes${meta.generated_at ? `; this site last checked GSO ${fmtAge(ageOf(meta.generated_at))}` : ""} · <a href="#/status">status</a>` : "" }),
    ].join("");

    const series = partPts.map((p, i) => ({ name: SOLAR_PARTS[i].label, points: p.points, color: SOLAR_PARTS[i].color, area: true, areaOpacity: 0.85, stack: "solar", width: 0.6 }));
    if (!series.length && solarPts) series.push({ name: "Transmission Solar", points: solarPts.points, color: COLORS.solar, area: true });
    if (fcPts) series.push({ name: "Forecast", points: fcPts.points, color: COLORS.forecast, dashed: true, width: 2 });
    if (series.some((s) => s.points.some((p) => p[1] != null))) timeChart(chartToday.querySelector(".chart"), { series, demo: meta.is_demo, markNow: true });
    else chartToday.querySelector(".card-b").innerHTML = emptyState("No solar readings yet today", `Solar starts after sunrise (about ${clock(7, 0)} MYT).`, "☀");

    if (slices.length) {
      mixCard.querySelector(".card-h").insertAdjacentHTML("afterend", `<p class="when">${fmtLong(snap.t)}</p>`);
      pieChart(mixCard.querySelector(".chart"), { unit: "MW", total: true, demo: meta.is_demo, items: slices.map((m) => ({ name: m.label, value: m.value, color: m.color })) });
    } else mixCard.querySelector(".card-b").innerHTML = emptyState("No complete Generation Mix yet", "Shown once every fuel has a reading for the same time.");

    if (avSeries.length) {
      avCard.querySelector(".card-h").insertAdjacentHTML("afterend", `<p class="when">${fmtLong(by[avSeries[0].key].last)}</p>`);
      pieChart(avCard.querySelector(".chart"), { unit: "MW", total: true, demo: meta.is_demo,
        items: avSeries.map((a) => ({ name: a.label, value: by[a.key].latest_value, color: a.color })).filter((a) => a.value > 0) });
    } else avCard.querySelector(".card-b").innerHTML = emptyState("No Generation Availability reading yet");

    if (demToday && demToday.points.some((p) => p[1] != null)) {
      const shifted = (demYest?.points || []).map(([t, v, q]) => [new Date(Date.parse(t) + 864e5).toISOString(), v, q]);
      timeChart(demCard.querySelector(".chart"), { demo: meta.is_demo, zoom: false, series: [
        { name: "Today", points: demToday.points, color: COLORS.demand, width: 2.4 },
        { name: "Yesterday", points: shifted, color: COLORS.demandLight, dashed: true, width: 1.6 },
      ] });
    } else demCard.querySelector(".card-b").innerHTML = emptyState("No demand readings yet today");
  } catch (err) {
    chartToday.querySelector(".card-b").innerHTML = errorState(err);
  }

  // ---- GSO's home page headline figures, under GSO's own labels and times
  const HEAD = [["current_grid_demand", "Current Grid Demand"], ["current_system_demand", "Current System Demand"],
    ["highest_grid_demand_recorded", "Highest Grid Demand Recorded"], ["highest_energy_recorded", "Highest Energy Recorded"],
    ["current_solar_generation", "Current Solar Generation"],
    ["current_bess", "Current BESS Status"], ["cross_border_exchange", "Cross-Border Power Exchange"]];
  const heads = HEAD.map(([k, label]) => [meta.series.find((x) => x.key === `headlines.${k}`), label, k]).filter(([x]) => x && x.latest_value != null);
  if (heads.length) {
    const bess = (v) => (v > 0 ? " (discharging)" : v < 0 ? " (charging)" : " (idle)");
    main.appendChild(h(card({ title: "GSO Home Page Figures", desc: "The figures at the top of GSO's home page, with GSO's own labels and times. GSO uses \"system demand\" for a larger figure than its System Demand page, which its home page calls \"grid demand\".",
      body: `<div class="table-wrap"><table><tbody>${heads.map(([x, label, k]) => `<tr><th scope="row" style="white-space:normal">${esc(label)}</th>
        <td class="num" style="white-space:normal"><b>${fmtNum(x.latest_value)} ${esc(x.unit)}</b>${k === "current_bess" ? bess(x.latest_value) : ""}<br><span class="small muted">${k === "highest_energy_recorded" ? esc(fmtDate(x.last)) : `${esc(fmtDateTime(x.last))} MYT`}</span></td></tr>`).join("")}</tbody></table></div>
        <p class="small muted"><a href="#/explorer?series=${heads.map(([x]) => x.key).filter((key) => !key.includes("highest")).join(",")}">See them over time in the Explorer</a></p>` })));
  }

  // ---- health, one line
  try {
    const st = await getStatus();
    if (!isCurrent()) return;
    const failing = st.adapters.filter((a) => a.enabled && a.consecutive_failures > 0);
    main.appendChild(h(`<p class="health-line">${st.live_enabled ? "🟢 Collecting from GSO automatically" : "⚪ Automatic collection is off"}
      · last run ${st.collector_heartbeat ? fmtAge(ageOf(st.collector_heartbeat.cycle_started_at)) : "never"}
      · ${failing.length ? `<b>${failing.length} source(s) failing</b>` : "all sources working"} · <a href="#/status">details</a></p>`));
  } catch { /* status is optional here */ }
}
