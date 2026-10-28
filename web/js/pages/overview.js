// Overview: latest successfully archived readings with their source timestamps.
import { getPoints, getStatus } from "../data.js";
import { COLORS, timeChart } from "../charts.js";
import { card, emptyState, errorState, fmtAge, fmtDateTime, fmtNum, freshnessPill, h, kpi, ageOf } from "../ui.js";

const FUELS = [
  ["generation_mix.coal", "Coal", COLORS.coal], ["generation_mix.gas", "Gas", COLORS.gas],
  ["generation_mix.hydro", "Hydro", COLORS.hydro], ["generation_mix.solar", "Solar", COLORS.solar],
  ["generation_mix.cogen", "Co-gen", COLORS.cogen], ["generation_mix.oil", "Oil", COLORS.oil],
];

export async function render(main, { meta, isCurrent }) {
  const by = Object.fromEntries(meta.series.map((s) => [s.key, s]));
  const solar = by["generation_mix.solar"];
  const demand = by["system_demand.demand"];
  const genKeys = meta.series.filter((s) => s.dataset === "generation_mix" && s.kind === "actual");
  const totalGen = genKeys.length && genKeys.every((s) => s.last === genKeys[0].last)
    ? genKeys.reduce((t, s) => t + (s.latest_value || 0), 0) : null;
  const ties = meta.series.filter((s) => s.category === "tieline");
  // (solar farms and other per-unit series are summarised on their own pages)

  if (!meta.series.length) {
    main.innerHTML = card({ title: "Welcome", body: emptyState("Nothing archived yet",
      "The archive is empty. No live values are shown until the collector has successfully stored real GSO readings. " +
      "Check <a href=\"#/status\">Collection Status</a> to see whether collection is enabled and running.", "◧") });
    renderStatusSummary(main);
    return;
  }

  main.appendChild(h(`<div class="grid kpis">
    ${kpi({ label: "Solar generation", cls: "solar", value: solar && solar.latest_value != null ? fmtNum(solar.latest_value) : null, unit: "MW",
      meta: solar?.last ? `${fmtDateTime(solar.last)} MYT · ${fmtAge(ageOf(solar.last))}` : "No reading archived" })}
    ${kpi({ label: "System demand", cls: "demand", value: demand && demand.latest_value != null ? fmtNum(demand.latest_value) : null, unit: "MW",
      meta: demand?.last ? `${fmtDateTime(demand.last)} MYT · ${fmtAge(ageOf(demand.last))}` : "No reading archived" })}
    ${kpi({ label: "Solar share of generation", value: solar && totalGen ? fmtNum((100 * solar.latest_value) / totalGen, 1) : null, unit: "%",
      meta: totalGen ? `Derived from ${genKeys.length} fuel series at the same timestamp` : "Needs a complete generation-mix reading" })}
    ${kpi({ label: "Total generation (sum of fuels)", value: totalGen != null ? fmtNum(totalGen) : null, unit: "MW", meta: totalGen != null ? "Derived" : "" })}
    ${(() => {
      const prof = ["grid", "distribution", "nem", "fit", "selco"].map((k) => by[`solar_profile.${k}`]).filter(Boolean);
      const sameTime = prof.length === 5 && prof.every((s) => s.last === prof[0].last && s.latest_value != null);
      return kpi({ label: "All solar (GSO Solar page)", cls: "solar", value: sameTime ? fmtNum(prof.reduce((t, s) => t + s.latest_value, 0)) : null, unit: "MW",
        meta: sameTime ? `Grid + distribution + rooftop estimates · ${fmtDateTime(prof[0].last)} MYT` : "Appears once GSO's Solar page has been collected" });
    })()}
    ${(() => {
      const d = by["genmix_live.bess_discharge"], c = by["genmix_live.bess_charge"];
      const net = d && c && d.latest_value != null && c.latest_value != null ? d.latest_value + c.latest_value : null;
      return kpi({ label: "Battery storage (BESS) net", value: net != null ? fmtNum(net) : null, unit: "MW",
        meta: net != null ? `${net > 0 ? "Discharging" : net < 0 ? "Charging" : "Idle"} · ${fmtDateTime(d.last)} MYT` : "" });
    })()}
    ${kpi({ label: "Tie-line flows archived", value: ties.length ? String(ties.length) : null, meta: ties.length ? ties.map((t) => `${t.dataset.replace("tieline_", "").toUpperCase()} ${fmtNum(t.latest_value)} MW`).join(" · ") : "" })}
  </div>`));

  const now = new Date();
  const start = new Date(now.getTime() - 48 * 3600e3);
  const c1 = h(card({ title: "Solar vs demand — last 48 hours", sub: solar ? freshnessPill(solar.last, solar.interval_s) : "", body: '<div class="chart tall"></div>' }));
  main.appendChild(c1);
  const row = h('<div class="grid cols-2"></div>');
  main.appendChild(row);
  const c2 = h(card({ title: "Generation mix — last 48 hours", sub: "Stacked, as published", body: '<div class="chart"></div>' }));
  const c3 = h(card({ title: "Collection health", body: '<div class="health"></div>' }));
  row.append(c2, c3);

  try {
    const [sp, dp, ...fuels] = await Promise.all([
      solar ? getPoints(solar.key, start, now) : null,
      demand ? getPoints(demand.key, start, now) : null,
      ...FUELS.filter(([k]) => by[k]).map(([k]) => getPoints(k, start, now)),
    ]);
    if (!isCurrent()) return;
    const series = [];
    if (sp) series.push({ name: "Solar", points: sp.points, color: COLORS.solar, area: true, width: 2 });
    if (dp) series.push({ name: "System demand", points: dp.points, color: COLORS.demand, yAxisIndex: sp ? 1 : 0 });
    if (series.length && series.some((s) => s.points.some((p) => p[1] != null))) {
      timeChart(c1.querySelector(".chart"), { series, yAxes: sp && dp ? [{ name: "Solar MW" }, { name: "Demand MW" }] : [{ name: "MW" }], demo: meta.is_demo, markNow: true });
    } else {
      c1.querySelector(".card-b").innerHTML = emptyState("No readings in the last 48 hours",
        "The most recent archived data is older than 48 hours. Values are never extrapolated.");
    }
    const present = FUELS.filter(([k]) => by[k]);
    if (fuels.length && fuels.some((f) => f.points.length)) {
      timeChart(c2.querySelector(".chart"), { demo: meta.is_demo, series: fuels.map((f, i) => ({ name: present[i][1], points: f.points, color: present[i][2], area: true, areaOpacity: 0.55, stack: "mix", width: 0.8 })) });
    } else c2.querySelector(".card-b").innerHTML = emptyState("No generation-mix readings in the last 48 hours");
  } catch (err) {
    c1.querySelector(".card-b").innerHTML = errorState(err);
  }
  renderStatusSummary(c3.querySelector(".health"));
}

async function renderStatusSummary(el) {
  try {
    const st = await getStatus();
    const enabled = st.adapters.filter((a) => a.enabled);
    const failing = enabled.filter((a) => a.consecutive_failures > 0);
    const stale = st.freshness.filter((f) => f.stale);
    const hb = st.collector_heartbeat;
    const html = `<div class="stat-row" style="flex-direction:column;gap:8px">
      <span>Live GSO collection: <b>${st.live_enabled ? "enabled" : "disabled"}</b>${st.live_enabled ? "" : ' <span class="muted">(GSO_LIVE_ENABLED=false — see About)</span>'}</span>
      <span>Last collector cycle: <b>${hb ? fmtDateTime(hb.cycle_started_at) + " MYT" : "never"}</b>${hb && hb.skipped_reason ? ` <span class="muted">— ${hb.skipped_reason}</span>` : ""}</span>
      <span>Adapters failing: <b>${failing.length}</b> of ${enabled.length} enabled</span>
      <span>Stale series: <b>${stale.length}</b> of ${st.freshness.length}</span>
      <span>Archived observations: <b>${fmtNum(st.totals.observations)}</b> · revisions tracked: <b>${fmtNum(st.totals.revisions)}</b></span>
      <a href="#/status">Full collection status →</a></div>`;
    if (el.classList && el.classList.contains("health")) el.innerHTML = html;
    else el.appendChild(h(card({ title: "Collection health", body: html })));
  } catch (err) {
    el.innerHTML = errorState(err);
  }
}
