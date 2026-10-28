// Generation mix page.
import { getDaily, getPoints, exportUrl } from "../data.js";
import { COLORS, FUELS, categoryChart, pieChart, timeChart } from "../charts.js";
import { sumSeries } from "../analysis.js";
import { addDays, card, shortForms, downloadText, emptyState, errorState, esc, fmtDateTime, fmtNum, fmtEnergy, h, loading, mytDayStart, pointsToCsv, rangePicker, verificationTag } from "../ui.js";

const FUEL = Object.fromEntries(FUELS.map((f) => [f.key, f]));
const AVAIL_COLOR = { coal: COLORS.coal, gas: COLORS.gas, cogen: COLORS.cogen, hydro: COLORS.hydro, transmission_solar: COLORS.gridSolar, distribution_solar: COLORS.dnSolar, bess: COLORS.bessDischarge };
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
      const c1 = h(card({ title: "Generation Mix", sub: verificationTag(gen[0].verification), desc: "Each colour is one fuel, stacked so the top edge is total generation. Grey: Coal, blue: Gas, green: Hydro, yellow: Transmission Solar.",
        right: `<button class="btn" data-a="csv">CSV</button>${exportUrl(gen.map((s) => s.key), range.startDay, range.endDay, "xlsx") ? `<a class="btn" href="${esc(exportUrl(gen.map((s) => s.key), range.startDay, range.endDay, "xlsx"))}">Excel</a>` : ""}`,
        body: '<div class="chart tall"></div>' }));
      body.appendChild(c1);
      if (pts.some((p) => p.points.some((x) => x[1] != null))) {
        timeChart(c1.querySelector(".chart"), { demo: meta.is_demo, series: pts.map((p, i) => ({ name: label(gen[i]), points: p.points, color: color(gen[i]), area: true, areaOpacity: 0.85, stack: "mix", width: 0.8 })) });
      } else c1.querySelector(".card-b").innerHTML = emptyState("No readings in this range");
      c1.querySelector('[data-a="csv"]').addEventListener("click", () => downloadText(`generation_${range.startDay}_${range.endDay}.csv`, pointsToCsv(pts)));

      const row = h('<div class="grid cols-2"></div>'); body.appendChild(row);
      const energies = daily.map((d, i) => ({ name: label(gen[i]), value: d.rows.reduce((t, r) => t + (r.energy_mwh || 0), 0), color: color(gen[i]) })).filter((x) => x.value > 0);
      const c2 = h(card({ title: "Energy Share by Fuel", desc: "How the electricity made in this period splits between fuels.", body: '<div class="chart"></div>' }));
      const total = sumSeries(pts.map((p) => p.points));
      const c3 = h(card({ title: "Total Generation", desc: "All fuels added together. Shown only at times when every fuel has a reading.", body: '<div class="chart"></div>' }));
      row.append(c2, c3);
      if (energies.length) pieChart(c2.querySelector(".chart"), { items: energies, demo: meta.is_demo });
      else c2.querySelector(".card-b").innerHTML = emptyState("No energy to show");
      if (total.some((x) => x[1] != null)) timeChart(c3.querySelector(".chart"), { series: [{ name: "Total", points: total, color: COLORS.net, area: true }], demo: meta.is_demo });
      else c3.querySelector(".card-b").innerHTML = emptyState("No complete timestamps");
      const sumE = energies.reduce((t, e) => t + e.value, 0);
      c2.querySelector(".card-b").insertAdjacentHTML("beforeend", `<p class="small muted">Total ${fmtEnergy(sumE)} across ${energies.length} fuels.</p>`);

      const av = meta.series.filter((s) => s.dataset === "availability" && s.latest_value != null);
      if (av.length) {
        const cA = h(card({ title: "System Availability", sub: `${av[0].last ? fmtDateTime(av[0].last) + " MYT" : ""} ${verificationTag(av[0].verification)}`, desc: "MW of each kind of plant available to the grid right now, as on GSO's home page.", body: '<div class="chart short"></div>' }));
        body.appendChild(cA);
        categoryChart(cA.querySelector(".chart"), { categories: av.map((s) => s.name.replace("System availability — ", "")), demo: meta.is_demo,
          series: [{ name: "Available", unit: "MW", data: av.map((s) => ({ value: s.latest_value, itemStyle: { color: availColor(s.key) } })) }] });
      }
      const c4 = h(card({ title: "Installed Capacity", desc: "The total size of all power stations of each fuel, whether running or not.", sub: caps.length ? verificationTag(caps[0].verification) : "", body: '<div class="chart short"></div>' }));
      body.appendChild(c4);
      const capSeries = caps.filter((c) => c.key !== "power_station.capacity_total" && c.latest_value != null);
      if (capSeries.length) {
        categoryChart(c4.querySelector(".chart"), { categories: capSeries.map((c) => c.name.replace("Installed capacity — ", "")), demo: meta.is_demo,
          series: [{ name: "Installed capacity", data: capSeries.map((c) => c.latest_value), color: COLORS.net, unit: "MW" }] });
        c4.querySelector(".card-b").insertAdjacentHTML("beforeend", `<p class="small muted">Sum of station capacities by fuel from the PowerStation page, archived daily. Snapshot taken ${esc(capSeries[0].last?.slice(0, 10) || "")}.</p>`);
      } else c4.querySelector(".card-b").innerHTML = emptyState("No capacity snapshot archived", "The <code>power_station</code> adapter archives installed capacity once a day when enabled.");
    } catch (err) { body.innerHTML = errorState(err); }
  }
  await picker.start();
}
