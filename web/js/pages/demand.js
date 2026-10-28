// Demand page.
import { getDaily, getPoints, exportUrl, rollup } from "../data.js";
import { COLORS, categoryChart, profileChart, timeChart } from "../charts.js";
import { intradayProfiles } from "../analysis.js";
import { addDays, card, downloadText, emptyState, errorState, esc, fmtDateTime, fmtNum, fmtEnergy, fmtTime, h, kpi, loading, mytDayStart, pointsToCsv, rangePicker, renderTable, freshnessPill } from "../ui.js";

export async function render(main, { meta, isCurrent }) {
  const demandSeries = meta.series.filter((s) => s.category === "demand" && s.kind === "actual");
  if (!demandSeries.length) {
    main.innerHTML = card({ title: "Demand", body: emptyState("No demand readings archived yet", "System demand appears here once the <code>system_demand</code> adapter has collected data.") });
    return;
  }
  const s = demandSeries[0];
  const bar = h("<div></div>"); main.appendChild(bar);
  const body = h('<div class="grid"></div>'); main.appendChild(body);
  const picker = rangePicker(bar, { initial: "7d", onChange: (r) => draw(r) });
  picker.firstDay = s.first ? new Date(Date.parse(s.first) + 8 * 3600e3).toISOString().slice(0, 10) : null;

  async function draw(range) {
    const start = mytDayStart(range.startDay), end = mytDayStart(addDays(range.endDay, 1));
    const days = Math.round((end - start) / 864e5);
    body.innerHTML = loading(120) + loading(360);
    try {
      const [pts, daily] = await Promise.all([days <= 370 ? getPoints(s.key, start, end) : null, getDaily(s.key, range.startDay, range.endDay)]);
      if (!isCurrent()) return;
      const rows = daily.rows, wd = rows.filter((r) => r.count);
      const peak = wd.reduce((b, r) => (b && b.max >= r.max ? b : r), null);
      const low = wd.reduce((b, r) => (b && b.min <= r.min ? b : r), null);
      const energy = wd.reduce((t, r) => t + (r.energy_mwh || 0), 0);
      body.innerHTML = "";
      body.appendChild(h(`<div class="grid kpis">
        ${kpi({ big: true, label: "⚡ Demand now", cls: "demand", value: s.latest_value != null ? fmtNum(s.latest_value) : null, unit: "MW", meta: s.last ? `${fmtDateTime(s.last)} MYT` : "" })}
        ${kpi({ big: true, label: "Highest in this period", cls: "demand", value: peak ? fmtNum(peak.max) : null, unit: "MW", meta: peak ? `${fmtDateTime(peak.max_time)} MYT` : "" })}
        ${kpi({ label: "Lowest in this period", value: low ? fmtNum(low.min) : null, unit: "MW", meta: low ? low.date : "" })}
        ${kpi({ label: "Electricity used", value: wd.length ? fmtEnergy(energy) : null, meta: `${wd.length}/${rows.length} days with data` })}
      </div>`));
      const c1 = h(card({ title: "Electricity demand", sub: freshnessPill(s.last, s.interval_s), desc: "How much electricity Peninsular Malaysia is using, in MW. It usually peaks in the afternoon and is lowest before dawn. Breaks mean no reading.",
        right: `<button class="btn" data-a="csv" ${pts ? "" : "disabled"}>CSV</button>${exportUrl([s.key], range.startDay, range.endDay, "xlsx") ? `<a class="btn" href="${esc(exportUrl([s.key], range.startDay, range.endDay, "xlsx"))}">Excel</a>` : ""}`,
        body: pts ? '<div class="chart tall"></div>' : '<div class="notice">Range too long for raw readings; see daily statistics.</div>' }));
      body.appendChild(c1);
      if (pts) {
        if (pts.points.some((p) => p[1] != null)) timeChart(c1.querySelector(".chart"), { series: [{ name: "Electricity demand", points: pts.points, color: COLORS.demand, area: true, width: 2 }], demo: meta.is_demo });
        else c1.querySelector(".card-b").innerHTML = emptyState("No readings in this range");
        c1.querySelector('[data-a="csv"]').addEventListener("click", () => downloadText(`demand_${range.startDay}_${range.endDay}.csv`, pointsToCsv([pts])));
      }
      const row = h('<div class="grid cols-2"></div>'); body.appendChild(row);
      const c2 = h(card({ title: "Each day's highest and lowest", desc: "Blue bars: the day's highest demand. Orange line: the day's lowest.", body: '<div class="chart"></div>' }));
      const c3 = h(card({ title: "Shape of the day", sub: days > 92 ? "One line per month" : "One line per week", desc: "Average demand by time of day. The darkest, thickest line is the most recent.", body: '<div class="chart"></div>' }));
      row.append(c2, c3);
      if (wd.length) categoryChart(c2.querySelector(".chart"), { categories: rows.map((r) => r.date.slice(5)), demo: meta.is_demo, zoom: rows.length > 45,
        series: [{ name: "Daily peak", data: rows.map((r) => r.max), color: COLORS.demand, unit: "MW" }, { name: "Daily minimum", type: "line", data: rows.map((r) => r.min), color: COLORS.solar3, unit: "MW" }] });
      else c2.querySelector(".card-b").innerHTML = emptyState("No data");
      if (pts && pts.points.some((p) => p[1] != null)) {
        const key = days > 92 ? (d) => d.slice(0, 7) : (d) => rollup([{ date: d, count: 0, completeness: 0 }], "week")[0].period;
        const groups = intradayProfiles(pts.points, key).slice(-12);
        profileChart(c3.querySelector(".chart"), { demo: meta.is_demo, groups: groups.map((g, i) => ({ name: g.key, data: g.data, color: `hsl(217, ${50 + i * 4}%, ${72 - i * 3.5}%)`, width: i === groups.length - 1 ? 2.4 : 1.3 })) });
      } else c3.querySelector(".card-b").innerHTML = emptyState("Shorten the range to see profiles");

      const monthly = rollup(rows, days > 120 ? "month" : "week");
      const c4 = h(card({ title: days > 120 ? "Highest demand each month" : "Highest demand each week", desc: "The record for each period and when it happened.", body: '<div class="tbl"></div>' }));
      body.appendChild(c4);
      renderTable(c4.querySelector(".tbl"), [
        { key: "period", label: "Period" }, { key: "max", label: "Peak (MW)", num: true, fmt: (v) => fmtNum(v) },
        { key: "max_time", label: "Peak time (MYT)", fmt: (v) => (v ? fmtDateTime(v) : "—") },
        { key: "mean_daily_peak", label: "Mean daily peak (MW)", num: true, fmt: (v) => fmtNum(v) },
        { key: "completeness", label: "Completeness", num: true, fmt: (v) => `${fmtNum(v * 100, 1)}%` },
      ], monthly.reverse(), 12);
    } catch (err) { body.innerHTML = errorState(err); }
  }
  await picker.start();
}
