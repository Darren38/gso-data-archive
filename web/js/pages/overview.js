// Overview: a dashboard of the grid right now and today. Only archived GSO readings are shown, with their times.
import { getPoints, getStatus } from "../data.js";
import { COLORS, SOLAR_PARTS, FUELS, pieChart, timeChart } from "../charts.js";
import { extent, sumSeries } from "../analysis.js";
import { card, emptyState, errorState, fmtAge, fmtDateTime, fmtNum, fmtTime, h, kpi, ageOf, mytDay, mytDayStart } from "../ui.js";

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
  const share = solarNow != null && demand?.latest_value ? (100 * solarNow) / demand.latest_value : null;
  const dis = by["genmix_live.bess_discharge"], chg = by["genmix_live.bess_charge"];
  const bess = dis && chg && dis.latest_value != null && chg.latest_value != null ? dis.latest_value + chg.latest_value : null;
  const fuels = FUELS.map((f) => ({ ...f, s: by[f.key] })).filter((f) => f.s && f.s.latest_value != null && f.s.latest_value > 0);
  const fuelTotal = fuels.reduce((t, f) => t + f.s.latest_value, 0);
  const biggest = fuels.slice().sort((a, b) => b.s.latest_value - a.s.latest_value)[0];

  main.appendChild(h(`<div class="grid kpis hero">
    ${kpi({ big: true, cls: "solar", label: "☀ Solar right now", value: solarNow != null ? fmtNum(solarNow) : null, unit: "MW",
      meta: solarAt ? `${partsNow ? "All solar incl. rooftop" : "Transmission solar"} · ${fmtTime(solarAt)} MYT` : "" })}
    ${kpi({ big: true, cls: "demand", label: "⚡ Electricity demand", value: demand?.latest_value != null ? fmtNum(demand.latest_value) : null, unit: "MW",
      meta: demand?.last ? `Peninsular Malaysia · ${fmtTime(demand.last)} MYT` : "" })}
    ${kpi({ big: true, cls: "solar", label: "Solar covers", value: share != null ? fmtNum(share, 1) : null, unit: "%", meta: "of electricity demand right now" })}
    ${kpi({ big: true, cls: "bess", label: "🔋 Battery storage", value: bess != null ? fmtNum(Math.abs(bess)) : null, unit: "MW",
      meta: bess == null ? "" : bess > 0 ? "Supplying the grid" : bess < 0 ? "Charging from the grid" : "Idle" })}
  </div>`));
  const second = h('<div class="grid kpis"></div>');
  main.appendChild(second);

  // ---- today
  const today = mytDay(new Date());
  const start = mytDayStart(today), now = new Date();
  const chartToday = h(card({ title: "Solar today vs GSO's forecast",
    desc: "Each colour is one kind of solar, stacked so the top edge is all solar together. The dashed line is GSO's forecast for today.",
    body: '<div class="chart tall"></div>' }));
  main.appendChild(chartToday);
  const row = h('<div class="grid cols-2"></div>');
  main.appendChild(row);
  const mixCard = h(card({ title: "Where electricity comes from now", desc: "Share of each fuel in generation at the latest reading.",
    body: '<div class="chart"></div>' }));
  const demCard = h(card({ title: "Demand today vs yesterday", desc: "Solid line: today. Dashed line: the same hours yesterday.", body: '<div class="chart"></div>' }));
  row.append(mixCard, demCard);

  try {
    const fc = by["solar_forecast.total"];
    const [partPts, fcPts, solarPts, demToday, demYest] = await Promise.all([
      parts.length ? Promise.all(parts.map((s) => getPoints(s.key, start, now))) : [],
      fc ? getPoints(fc.key, start, new Date(start.getTime() + 864e5)) : null,
      by["generation_mix.solar"] ? getPoints("generation_mix.solar", start, now) : null,
      demand ? getPoints(demand.key, start, now) : null,
      demand ? getPoints(demand.key, new Date(start.getTime() - 864e5), start) : null,
    ]);
    if (!isCurrent()) return;

    const totalToday = partPts.length === SOLAR_PARTS.length ? sumSeries(partPts.map((p) => p.points)) : solarPts?.points || [];
    const peak = extent(totalToday).max;
    const fcPeak = fcPts ? extent(fcPts.points).max : null;
    second.innerHTML = [
      kpi({ cls: "solar", label: "Today's solar peak so far", value: peak ? fmtNum(peak[1]) : null, unit: "MW", meta: peak ? `at ${fmtTime(peak[0])} MYT` : "" }),
      kpi({ cls: "forecast", label: "GSO forecast peak today", value: fcPeak ? fmtNum(fcPeak[1]) : null, unit: "MW", meta: fcPeak ? `expected at ${fmtTime(fcPeak[0])} MYT` : "" }),
      kpi({ label: "Biggest source now", value: biggest ? biggest.label : null, meta: biggest ? `${fmtNum((100 * biggest.s.latest_value) / fuelTotal, 0)}% of generation · ${fmtNum(biggest.s.latest_value)} MW` : "" }),
      kpi({ label: "Data updated", value: solarAt ? fmtAge(ageOf(solarAt)) : null, meta: `Collected from GSO automatically · <a href="#/status">status</a>` }),
    ].join("");

    const series = partPts.map((p, i) => ({ name: SOLAR_PARTS[i].label, points: p.points, color: SOLAR_PARTS[i].color, area: true, areaOpacity: 0.85, stack: "solar", width: 0.6 }));
    if (!series.length && solarPts) series.push({ name: "Transmission solar", points: solarPts.points, color: COLORS.solar, area: true });
    if (fcPts) series.push({ name: "GSO forecast", points: fcPts.points, color: COLORS.forecast, dashed: true, width: 2 });
    if (series.some((s) => s.points.some((p) => p[1] != null))) timeChart(chartToday.querySelector(".chart"), { series, demo: meta.is_demo, markNow: true });
    else chartToday.querySelector(".card-b").innerHTML = emptyState("No solar readings yet today", "Solar starts after sunrise (about 7:00 MYT).", "☀");

    if (fuels.length) pieChart(mixCard.querySelector(".chart"), { unit: "MW", demo: meta.is_demo, items: fuels.map((f) => ({ name: f.label, value: f.s.latest_value, color: f.color })) });
    else mixCard.querySelector(".card-b").innerHTML = emptyState("No generation reading yet");

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
