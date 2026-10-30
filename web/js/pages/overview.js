// Overview: the grid right now and today, arranged like GSO's home page. Only archived GSO readings are shown, with their times.
import { getPoints, getStatus } from "../data.js";
import { COLORS, SOLAR_PARTS, FUELS, pieChart } from "../charts.js";
import { drawProfile } from "../profile.js";
import { card, esc, fmtDate, fmtLong, shortForms, emptyState, errorState, fmtAge, fmtDateTime, fmtNum, fmtTime, h, kpi, ageOf } from "../ui.js";

// GSO's home page "Generation Mix" and "Generation Availability" donuts, with GSO's names and colours.
const MIX = [...FUELS.slice(0, 5), { key: "genmix_live.tie_line_total", label: "Tie-Line", color: COLORS.tieline }, ...FUELS.slice(5)];
const AVAIL = [
  ["coal", "Coal", COLORS.coal], ["cogen", "Co-Gen", COLORS.cogen], ["gas", "Gas", COLORS.gas], ["hydro", "Hydro", COLORS.hydro],
  ["transmission_solar", "Transmission Solar", COLORS.gridSolar], ["distribution_solar", "Distribution Solar", COLORS.dnSolar], ["bess", "BESS", COLORS.bessDischarge],
].map(([k, label, color]) => ({ key: `availability.${k}`, label, color }));
const ORE_COLOR = { biogas: "#8d6e63", biomass: "#7cb342", mini_hydro: "#26a69a" };

/** The newest time at which every series has a reading, so the donut shows one moment (as GSO's does). */
function latestCommon(seriesPoints) {
  const maps = seriesPoints.map((pts) => new Map(pts.filter((p) => p[1] != null).map((p) => [Date.parse(p[0]), p[1]])));
  const times = [...maps[0].keys()].filter((t) => maps.every((m) => m.has(t))).sort((a, b) => b - a);
  return times.length ? { t: new Date(times[0]).toISOString(), values: maps.map((m) => m.get(times[0])) } : null;
}

// GSO's home page headline boxes, in GSO's order, with GSO's labels.
const HEADLINES = [
  ["current_grid_demand", "Current Grid Demand", "demand", "demand"], ["current_system_demand", "Current System Demand", "demand", "demand"],
  ["highest_grid_demand_recorded", "Highest Grid Demand Recorded", "peak", "demand"], ["highest_energy_recorded", "Highest Energy Recorded", "energy", ""],
  ["current_solar_generation", "Current Solar Generation", "solar", "solar"], ["current_bess", "Current BESS Status", "battery", "bess"],
  ["cross_border_exchange", "Cross-Border Power Exchange", "exchange", "tieline"],
];
const FRESH_S = 45 * 60; // a home-page figure older than this gives way to the same figure from GSO's own page

export async function render(main, { meta, isCurrent }) {
  const by = Object.fromEntries(meta.series.map((s) => [s.key, s]));
  if (!meta.series.length) {
    main.innerHTML = card({ title: "Welcome", body: emptyState("Nothing archived yet",
      "No live values are shown until the collector has stored real GSO readings. " +
      "<a href=\"#/status\">Collection Status</a> shows whether collection is running.", "◧") });
    return;
  }

  // ---- GSO's home page headline figures. Where GSO publishes the same figure on another page more often (Grid
  // Demand on its System Demand page, solar on its Solar page, BESS in its generation mix), that one stands in when the
  // home page's is missing or late, and the card says where it came from.
  const head = (k) => (by[`headlines.${k}`]?.latest_value != null ? by[`headlines.${k}`] : null);
  const fresh = (x) => x && ageOf(x.last) <= FRESH_S;
  const later = (a, b) => (Date.parse(a.last) >= Date.parse(b.last) ? a : b);
  const parts = SOLAR_PARTS.map((p) => by[p.key]).filter(Boolean);
  const partsNow = parts.length === SOLAR_PARTS.length && parts.every((s) => s.latest_value != null && s.last === parts[0].last);
  const solarOwn = partsNow ? { value: parts.reduce((t, s) => t + s.latest_value, 0), last: parts[0].last, from: "GSO's Solar page (Grid + Distribution + NEM + FiT + SELCO)" } : null;
  const dis = by["genmix_live.bess_discharge"], chg = by["genmix_live.bess_charge"];
  const bessOwn = dis && chg && dis.latest_value != null && chg.latest_value != null && dis.last === chg.last
    ? { value: dis.latest_value + chg.latest_value, last: dis.last, from: "GSO's home page generation mix" } : null;
  const demand = by["system_demand.demand"];
  const demandOwn = demand?.latest_value != null ? { value: demand.latest_value, last: demand.last, from: "GSO's System Demand page" } : null;
  const own = { current_grid_demand: demandOwn, current_solar_generation: solarOwn, current_bess: bessOwn };
  const pick = (k) => {
    const x = head(k), o = own[k];
    const hx = x && { value: x.latest_value, last: x.last, unit: x.unit, from: "GSO's home page" };
    if (k === "current_grid_demand" && hx && o) return { ...later(hx, o), unit: "MW" }; // the same figure on two GSO pages
    if (hx && (fresh(x) || !o || Date.parse(x.last) >= Date.parse(o.last))) return hx;
    return o ? { ...o, unit: "MW" } : hx;
  };
  const boxes = HEADLINES.map(([k, label, icon, cls]) => {
    const x = pick(k);
    const record = k.startsWith("highest");
    let when = "";
    if (x) when = k === "highest_energy_recorded" ? `on ${fmtDate(x.last)}` : `${record ? "on " : ""}${fmtDateTime(x.last)} MYT`;
    const note = k === "current_bess" && x ? (x.value > 0 ? "Discharging · " : x.value < 0 ? "Charging · " : "Idle · ") : "";
    const value = x == null ? null : fmtNum(k === "current_bess" ? Math.abs(x.value) : x.value);
    return kpi({ big: !record && k !== "cross_border_exchange", cls, icon, label, value, unit: x?.unit || (k === "highest_energy_recorded" ? "MWh" : "MW"),
      meta: x ? `${note}${when}${record ? "" : ` · from ${x.from}`}` : k === "current_grid_demand" ? "" : "Kept from 30 October 2026, when GSO's home page shows it" });
  });
  main.appendChild(h(`<div class="grid kpis hero heads">${boxes.join("")}</div>`));
  main.appendChild(h(`<p class="small muted" style="margin:0">As on GSO's home page. <b>Grid Demand</b> is the figure on GSO's System Demand page;
    <b>System Demand</b> is the larger figure GSO's home page shows next to it. Solar in detail is on the <a href="#/solar">Solar</a> page,
    and today's demand against yesterday's on the <a href="#/demand">Demand</a> page.</p>`));
  main.appendChild(h(shortForms(["MW", "MWh", "MYT", "BESS", "Co-Gen", "RE"])));

  // ---- as GSO's home page draws it. The last 24 hours rather than "today", so the chart is never empty after midnight.
  const now = new Date(), start = new Date(now.getTime() - 864e5);
  const mixSeries = MIX.filter((m) => by[m.key]);
  const avSeries = AVAIL.filter((a) => by[a.key] && by[a.key].latest_value != null);
  const ore = meta.series.filter((s) => s.dataset === "other_re" && s.latest_value != null);
  const profCard = h(card({ title: "System Demand Profile for Peninsular Malaysia", sub: "Last 24 hours",
    desc: "As on GSO's home page: each colour is a source of electricity, stacked, so the top edge is what the grid generates, with Grid Demand (solid) and System Demand (dashed) on top. Breaks mean a source had no reading at that time.",
    body: '<div class="chart tall"></div>' }));
  main.appendChild(profCard);
  const row = h('<div class="grid cols-2"></div>');
  main.appendChild(row);
  const mixCard = h(card({ title: "Generation Mix", desc: "Share of each fuel in the electricity being generated. The middle shows the total.",
    body: '<div class="chart"></div>' }));
  const avCard = h(card({ title: "Generation Availability", desc: "Share of each kind of plant ready to run. The middle shows the total available.",
    body: '<div class="chart"></div>' }));
  row.append(mixCard, avCard);
  const oreCard = ore.length ? h(card({ title: "Other Renewables", desc: "GSO's \"Other RE\" split, as its home page labels it. The middle shows the total.",
    body: '<div class="chart"></div>' })) : null;
  if (oreCard) main.appendChild(oreCard);

  try {
    const [profile, mixPts] = await Promise.all([
      drawProfile(profCard.querySelector(".chart"), meta, start, now, { isCurrent }),
      Promise.all(mixSeries.map((m) => getPoints(m.key, start, now))),
    ]);
    if (!isCurrent()) return;
    if (!profile) profCard.querySelector(".card-b").innerHTML = emptyState("No generation readings in the last 24 hours");

    // One moment for the whole mix, like GSO's chart (the fuels and the extras come from two GSO pages).
    const snap = mixSeries.length ? latestCommon(mixPts.map((p) => p.points)) : null;
    const slices = snap ? mixSeries.map((m, i) => ({ ...m, value: snap.values[i] })).filter((m) => m.value > 0) : [];
    if (slices.length) {
      mixCard.querySelector(".card-h").insertAdjacentHTML("afterend", `<p class="when">${fmtLong(snap.t)}</p>`);
      pieChart(mixCard.querySelector(".chart"), { unit: "MW", total: true, demo: meta.is_demo, items: slices.map((m) => ({ name: m.label, value: m.value, color: m.color })) });
    } else mixCard.querySelector(".card-b").innerHTML = emptyState("No complete Generation Mix yet", "Shown once every fuel has a reading for the same time.");

    if (avSeries.length) {
      avCard.querySelector(".card-h").insertAdjacentHTML("afterend", `<p class="when">${fmtLong(by[avSeries[0].key].last)}</p>`);
      pieChart(avCard.querySelector(".chart"), { unit: "MW", total: true, demo: meta.is_demo,
        items: avSeries.map((a) => ({ name: a.label, value: by[a.key].latest_value, color: a.color })).filter((a) => a.value > 0) });
    } else avCard.querySelector(".card-b").innerHTML = emptyState("No Generation Availability reading yet");

    if (oreCard) {
      // One moment: the split is filed together, so the newest reading of each part shares a time.
      const last = ore.map((s) => s.last).sort().pop();
      const items = ore.filter((s) => s.last === last && s.latest_value > 0)
        .map((s) => ({ name: s.name.replace("Other renewables — ", ""), value: s.latest_value, color: ORE_COLOR[s.key.split(".")[1]] || COLORS.other }));
      if (items.length) {
        oreCard.querySelector(".card-h").insertAdjacentHTML("afterend", `<p class="when">${fmtLong(last)}</p>`);
        pieChart(oreCard.querySelector(".chart"), { unit: "MW", total: true, demo: meta.is_demo, items });
      } else oreCard.querySelector(".card-b").innerHTML = emptyState("No Other Renewables reading yet");
    }
  } catch (err) {
    profCard.querySelector(".card-b").innerHTML = errorState(err);
  }

  // ---- health, one line, with the time of GSO's newest reading
  try {
    const st = await getStatus();
    if (!isCurrent()) return;
    const failing = st.adapters.filter((a) => a.enabled && a.consecutive_failures > 0);
    const newest = demand?.last;
    main.appendChild(h(`<p class="health-line">${st.live_enabled ? "🟢 Collecting from GSO automatically" : "⚪ Automatic collection is off"}
      · last run ${st.collector_heartbeat ? fmtAge(ageOf(st.collector_heartbeat.cycle_started_at)) : "never"}
      ${newest ? `· newest Grid Demand reading ${esc(fmtTime(newest))} MYT (${fmtAge(ageOf(newest))})` : ""}
      · ${failing.length ? `<b>${failing.length} source(s) failing</b>` : "all sources working"} · <a href="#/status">details</a></p>`));
  } catch { /* status is optional here */ }
}
