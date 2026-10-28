// Generation mix page.
import { getDaily, getPoints, exportUrl } from "../data.js";
import { COLORS, categoryChart, pieChart, timeChart } from "../charts.js";
import { sumSeries } from "../analysis.js";
import { addDays, card, downloadText, emptyState, errorState, esc, fmtNum, fmtEnergy, h, loading, mytDayStart, pointsToCsv, rangePicker, verificationTag } from "../ui.js";

const COLOR_BY_FUEL = { coal: COLORS.coal, gas: COLORS.gas, hydro: COLORS.hydro, solar: COLORS.solar, oil: COLORS.oil, cogen: COLORS.cogen };

export async function render(main, { meta, isCurrent }) {
  const gen = meta.series.filter((s) => s.dataset === "generation_mix" && s.kind === "actual");
  const caps = meta.series.filter((s) => s.dataset === "power_station");
  if (!gen.length) {
    main.innerHTML = card({ title: "Generation", body: emptyState("No generation-mix readings archived yet") });
    return;
  }
  const bar = h("<div></div>"); main.appendChild(bar);
  const body = h('<div class="grid"></div>'); main.appendChild(body);
  const color = (s) => COLOR_BY_FUEL[s.key.split(".")[1]] || COLORS.other;
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
      const c1 = h(card({ title: "Generation by fuel", sub: `Stacked, MW as published ${verificationTag(gen[0].verification)}`,
        right: `<button class="btn" data-a="csv">CSV</button>${exportUrl(gen.map((s) => s.key), range.startDay, range.endDay, "xlsx") ? `<a class="btn" href="${esc(exportUrl(gen.map((s) => s.key), range.startDay, range.endDay, "xlsx"))}">Excel</a>` : ""}`,
        body: '<div class="chart tall"></div>' }));
      body.appendChild(c1);
      if (pts.some((p) => p.points.some((x) => x[1] != null))) {
        timeChart(c1.querySelector(".chart"), { demo: meta.is_demo, series: pts.map((p, i) => ({ name: gen[i].name.replace(" (as published in generation mix)", ""), points: p.points, color: color(gen[i]), area: true, areaOpacity: 0.6, stack: "mix", width: 0.8 })) });
      } else c1.querySelector(".card-b").innerHTML = emptyState("No readings in this range");
      c1.querySelector('[data-a="csv"]').addEventListener("click", () => downloadText(`generation_${range.startDay}_${range.endDay}.csv`, pointsToCsv(pts)));

      const row = h('<div class="grid cols-2"></div>'); body.appendChild(row);
      const energies = daily.map((d, i) => ({ name: gen[i].name.replace(" (as published in generation mix)", ""), value: d.rows.reduce((t, r) => t + (r.energy_mwh || 0), 0), color: color(gen[i]) })).filter((x) => x.value > 0);
      const c2 = h(card({ title: "Energy share in range", sub: "Derived from archived readings", body: '<div class="chart"></div>' }));
      const total = sumSeries(pts.map((p) => p.points));
      const c3 = h(card({ title: "Total generation (sum of published fuels)", sub: "Derived; a timestamp counts only if every fuel has a reading", body: '<div class="chart"></div>' }));
      row.append(c2, c3);
      if (energies.length) pieChart(c2.querySelector(".chart"), { items: energies, demo: meta.is_demo });
      else c2.querySelector(".card-b").innerHTML = emptyState("No energy to show");
      if (total.some((x) => x[1] != null)) timeChart(c3.querySelector(".chart"), { series: [{ name: "Total", points: total, color: COLORS.net, area: true }], demo: meta.is_demo });
      else c3.querySelector(".card-b").innerHTML = emptyState("No complete timestamps");
      const sumE = energies.reduce((t, e) => t + e.value, 0);
      c2.querySelector(".card-b").insertAdjacentHTML("beforeend", `<p class="small muted">Total ${fmtEnergy(sumE)} across ${energies.length} fuels.</p>`);

      const c4 = h(card({ title: "Installed capacity snapshot", sub: caps.length ? verificationTag(caps[0].verification) : "", body: '<div class="chart short"></div>' }));
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
