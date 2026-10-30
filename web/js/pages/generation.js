// Generation mix page.
import { getDaily, getPoints, getTable, exportUrl } from "../data.js";
import { COLORS, FUELS, categoryChart, pieChart, timeChart } from "../charts.js";
import { alignStack, sumSeries } from "../analysis.js";
import { drawProfile } from "../profile.js";
import { addDays, card, shortForms, downloadText, emptyState, errorState, esc, fmtDateTime, fmtLong, fmtNum, fmtEnergy, h, loading, mytDayStart, pointsToCsv, rangePicker, renderTable, verificationTag } from "../ui.js";

const FUEL = Object.fromEntries(FUELS.map((f) => [f.key, f]));
const AVAIL_COLOR = { coal: COLORS.coal, gas: COLORS.gas, cogen: COLORS.cogen, hydro: COLORS.hydro, transmission_solar: COLORS.gridSolar, distribution_solar: COLORS.dnSolar, bess: COLORS.bessDischarge };
const AVAIL_NAME = { coal: "Coal", gas: "Gas", cogen: "Co-Gen", hydro: "Hydro", transmission_solar: "Transmission Solar", distribution_solar: "Distribution Solar", bess: "BESS" };
const availColor = (key) => AVAIL_COLOR[key.split(".")[1]] || COLORS.other;

export async function render(main, { meta, isCurrent }) {
  const gen = meta.series.filter((s) => s.dataset === "generation_mix" && s.kind === "actual");
  const caps = meta.series.filter((s) => s.dataset === "power_station");
  if (!gen.length) {
    main.innerHTML = card({ title: "Generation", body: emptyState("No generation-mix readings archived yet") });
    return;
  }
  const bar = h("<div></div>"); main.appendChild(bar);
  const body = h('<div class="grid"></div>'); main.appendChild(body);
  const color = (s) => FUEL[s.key]?.color || COLORS.other;
  const label = (s) => FUEL[s.key]?.label || s.name.replace(" (as published in generation mix)", "");
  const picker = rangePicker(bar, { initial: "2d", presets: ["1d", "2d", "7d", "30d", "90d"], onChange: (r) => draw(r) });

  async function draw(range) {
    const start = mytDayStart(range.startDay), end = mytDayStart(addDays(range.endDay, 1));
    body.innerHTML = loading(380);
    try {
      const [pts, daily] = await Promise.all([
        Promise.all(gen.map((s) => getPoints(s.key, start, end))),
        Promise.all(gen.map((s) => getDaily(s.key, range.startDay, range.endDay))),
      ]);
      if (!isCurrent()) return;
      body.innerHTML = "";
      body.appendChild(h(shortForms(["MW", "MWh", "Co-Gen", "Oil/DF", "BESS", "MYT"])));
      const c1 = h(card({ title: "Generation Mix", sub: verificationTag(gen[0].verification), desc: "Drawn like GSO's System Demand Profile: each colour is one source, stacked so the top edge is total generation, with System Demand (dashed) and, when GSO publishes it, GSO's Grid Demand (solid) on top. Grey: Coal, blue: Gas, green: Hydro, yellow: solar. Breaks mean a source had no reading at that time.",
        right: `<button class="btn" data-a="csv">CSV</button>${exportUrl(gen.map((s) => s.key), range.startDay, range.endDay, "xlsx") ? `<a class="btn" href="${esc(exportUrl(gen.map((s) => s.key), range.startDay, range.endDay, "xlsx"))}">Excel</a>` : ""}`,
        body: '<div class="chart tall"></div>' }));
      body.appendChild(c1);
      const profile = await drawProfile(c1.querySelector(".chart"), meta, start, end, { isCurrent });
      if (!isCurrent()) return;
      if (!profile) c1.querySelector(".card-b").innerHTML = emptyState("No readings in this range");
      c1.querySelector('[data-a="csv"]').addEventListener("click", () => downloadText(`generation_${range.startDay}_${range.endDay}.csv`, pointsToCsv(profile || pts)));

      const row = h('<div class="grid cols-2"></div>'); body.appendChild(row);
      const energies = daily.map((d, i) => ({ name: label(gen[i]), value: d.rows.reduce((t, r) => t + (r.energy_mwh || 0), 0), color: color(gen[i]) })).filter((x) => x.value > 0);
      const c2 = h(card({ title: "Energy Share by Fuel", desc: "How the electricity made in this period splits between fuels.", body: '<div class="chart"></div>' }));
      const total = sumSeries(pts.map((p) => p.points));
      const c3 = h(card({ title: "Total Generation", desc: "All fuels added together. Shown only at times when every fuel has a reading.", body: '<div class="chart"></div>' }));
      row.append(c2, c3);
      if (energies.length) pieChart(c2.querySelector(".chart"), { items: energies, total: true, demo: meta.is_demo });
      else c2.querySelector(".card-b").innerHTML = emptyState("No energy to show");
      if (total.some((x) => x[1] != null)) timeChart(c3.querySelector(".chart"), { series: [{ name: "Total", points: total, color: COLORS.net, area: true }], demo: meta.is_demo });
      else c3.querySelector(".card-b").innerHTML = emptyState("No complete timestamps");
      const sumE = energies.reduce((t, e) => t + e.value, 0);
      c2.querySelector(".card-b").insertAdjacentHTML("beforeend", `<p class="small muted">Total ${fmtEnergy(sumE)} across ${energies.length} fuels.</p>`);

      // Other renewables split, as GSO labels it on its home page (biogas, biomass, mini hydro).
      const ore = meta.series.filter((s) => s.dataset === "other_re" && s.count);
      if (ore.length) {
        const orePts = await Promise.all(ore.map((s) => getPoints(s.key, start, end)));
        if (!isCurrent()) return;
        const aligned = alignStack(orePts.map((p) => p.points));
        const cR = h(card({ title: "Other Renewables", sub: verificationTag(ore[0].verification),
          desc: "GSO's \"Other RE\" split as its home page labels it, stacked so the top edge is all other renewables. GSO gives no time with this split; it is filed at the time of the home page's newest Other RE reading, only when the two totals agree.",
          body: '<div class="chart"></div>' }));
        body.appendChild(cR);
        const oreColor = { biogas: "#8d6e63", biomass: "#7cb342", mini_hydro: "#26a69a" };
        if (aligned.some((pts) => pts.some((x) => x[1] != null))) {
          timeChart(cR.querySelector(".chart"), { demo: meta.is_demo, series: ore.map((s, i) => ({
            name: s.name.replace("Other renewables — ", ""), points: aligned[i], stack: "ore", area: true,
            color: oreColor[s.key.split(".")[1]] || COLORS.other })) });
        } else cR.querySelector(".card-b").innerHTML = emptyState("No readings in this range", "The split is kept from 30 October 2026.");
      }

      const av = meta.series.filter((s) => s.dataset === "availability" && s.latest_value != null);
      if (av.length) {
        const cA = h(card({ title: "Generation Availability", when: av[0].last ? fmtLong(av[0].last) : "", sub: verificationTag(av[0].verification), desc: "MW of each kind of plant available to the grid right now, as on GSO's home page.", body: '<div class="chart"></div>' }));
        body.appendChild(cA);
        pieChart(cA.querySelector(".chart"), { unit: "MW", total: true, demo: meta.is_demo,
          items: av.filter((s) => s.latest_value > 0).map((s) => ({ name: AVAIL_NAME[s.key.split(".")[1]] || s.name, value: s.latest_value, color: availColor(s.key) })) });
      }
      const c4 = h(card({ title: "Installed Capacity", desc: "The total size of all power stations of each fuel, whether running or not.", sub: caps.length ? verificationTag(caps[0].verification) : "", body: '<div class="chart short"></div>' }));
      body.appendChild(c4);
      const capSeries = caps.filter((c) => c.key !== "power_station.capacity_total" && c.latest_value != null);
      if (capSeries.length) {
        categoryChart(c4.querySelector(".chart"), { categories: capSeries.map((c) => c.name.replace("Installed capacity — ", "")), demo: meta.is_demo,
          series: [{ name: "Installed capacity", data: capSeries.map((c) => c.latest_value), color: COLORS.net, unit: "MW" }] });
        c4.querySelector(".card-b").insertAdjacentHTML("beforeend", `<p class="small muted">Sum of station capacities by fuel from the PowerStation page, archived daily. Snapshot taken ${esc(capSeries[0].last?.slice(0, 10) || "")}.</p>`);
      } else c4.querySelector(".card-b").innerHTML = emptyState("No capacity snapshot archived", "The <code>power_station</code> adapter archives installed capacity once a day when enabled.");

      // Every power station on GSO's Power Station Info, with the changes GSO has made since the archive began.
      const st = await getTable("power_station").catch(() => null);
      if (!isCurrent()) return;
      if (st && st.rows.length) {
        const listed = st.rows.filter((r) => r.listed !== false);
        const c5 = h(card({ title: "Power Stations", sub: caps.length ? verificationTag(caps[0].verification) : "",
          desc: `Every power station on GSO's Power Station Info: ${fmtNum(listed.length)} stations, ${fmtNum(listed.reduce((t, r) => t + (r.capacity_mw || 0), 0))} MW. PPA/SLA expiry is when the station's agreement ends, as GSO lists it.`,
          right: '<button class="btn" data-a="st-csv">CSV</button>',
          body: `<div class="tbl"></div><p class="small muted">Checked ${esc(fmtDateTime(st.checked_at))} MYT.</p><div class="changes"></div>` }));
        body.appendChild(c5);
        renderTable(c5.querySelector(".tbl"), [
          { key: "name", label: "Station", fmt: (v, r) => `${esc(v)}${r.listed === false ? ` <span class="pill warn" title="Last on GSO's list ${esc(fmtDateTime(r.last_seen))} MYT">no longer listed</span>` : ""}` },
          { key: "fuel", label: "Fuel" },
          { key: "type", label: "Type" },
          { key: "capacity_mw", label: "Capacity (MW)", num: true, fmt: (v) => fmtNum(v) },
          { key: "ppa_expiry_label", label: "PPA/SLA expiry", fmt: (v) => esc(v || "—") },
        ], st.rows, 20);
        const changes = st.changes || [];
        const what = (c) => c.change === "capacity_mw" ? `capacity ${fmtNum(c.old)} → ${fmtNum(c.new)} MW`
          : ["added", "no longer listed", "listed again"].includes(c.change) ? c.change : `${esc(c.change)}: ${esc(c.old ?? "—")} → ${esc(c.new ?? "—")}`;
        c5.querySelector(".changes").innerHTML = changes.length
          ? `<h3 class="small">Changes GSO made to this list</h3><ul class="small">${changes.slice(0, 30).map((c) => `<li>${esc(fmtDateTime(c.at))}: <b>${esc(c.name || c.id)}</b> ${what(c)}</li>`).join("")}</ul>`
          : '<p class="small muted">No changes to GSO\'s list since the archive began keeping it.</p>';
        const csvCell = (v) => (v == null ? "" : /[",\n]/.test(String(v)) ? `"${String(v).replace(/"/g, '""')}"` : String(v));
        c5.querySelector('[data-a="st-csv"]').addEventListener("click", () => downloadText("gso_power_stations.csv",
          ["id,name,fuel,type,capacity_mw,ppa_expiry,ppa_expiry_label,listed,first_seen,last_seen",
            ...st.rows.map((r) => [r.id, r.name, r.fuel, r.type, r.capacity_mw, r.ppa_expiry, r.ppa_expiry_label, r.listed !== false, r.first_seen, r.last_seen].map(csvCell).join(","))].join("\n")));
      }
    } catch (err) { body.innerHTML = errorState(err); }
  }
  await picker.start();
}
