// Tie-line flows.
import { getPoints, exportUrl } from "../data.js";
import { COLORS, timeChart } from "../charts.js";
import { sumSeries, extent } from "../analysis.js";
import { addDays, card, downloadText, emptyState, errorState, esc, fmtDateTime, fmtNum, h, kpi, loading, mytDayStart, pointsToCsv, rangePicker } from "../ui.js";

const LINE_COLOR = { tieline_egat: COLORS.egat, tieline_hvdc: COLORS.hvdc, tieline_pltg: COLORS.pltg };

export async function render(main, { meta, isCurrent }) {
  const lines = meta.series.filter((s) => s.category === "tieline");
  main.appendChild(h(`<div class="notice"><b>Sign convention:</b> values are stored exactly as GSO publishes them. GSO's sign convention has not been
    confirmed from a verified GSO document. The Electricity Maps project interprets positive values as flow <i>out of</i> Peninsular Malaysia (export).
    Treat direction labels as provisional.</div>`));
  if (!lines.length) {
    main.appendChild(h(card({ title: "Tie-lines", body: emptyState("No tie-line readings archived yet") })));
    return;
  }
  const bar = h("<div></div>"); main.appendChild(bar);
  const body = h('<div class="grid"></div>'); main.appendChild(body);
  const picker = rangePicker(bar, { initial: "7d", presets: ["1d", "2d", "7d", "30d", "90d"], onChange: (r) => draw(r) });

  async function draw(range) {
    const start = mytDayStart(range.startDay), end = mytDayStart(addDays(range.endDay, 1));
    body.innerHTML = loading(360);
    try {
      const pts = await Promise.all(lines.map((s) => getPoints(s.key, start, end)));
      if (!isCurrent()) return;
      body.innerHTML = "";
      body.appendChild(h(`<div class="grid kpis">${lines.map((s, i) => {
        const e = extent(pts[i].points);
        return kpi({ label: s.dataset.replace("tieline_", "").toUpperCase(), value: s.latest_value != null ? fmtNum(s.latest_value) : null, unit: "MW",
          meta: `${s.last ? fmtDateTime(s.last) + " MYT" : ""}${e.max ? ` · range ${fmtNum(e.min[1])} to ${fmtNum(e.max[1])} MW` : ""}` });
      }).join("")}</div>`));
      const c1 = h(card({ title: "Power lines to neighbours", sub: "MW as published", desc: "Flow on the links to Thailand (EGAT, HVDC) and Singapore (PLTG). GSO publishes a reading every 30 minutes.",
        right: `<button class="btn" data-a="csv">CSV</button>${exportUrl(lines.map((s) => s.key), range.startDay, range.endDay, "xlsx") ? `<a class="btn" href="${esc(exportUrl(lines.map((s) => s.key), range.startDay, range.endDay, "xlsx"))}">Excel</a>` : ""}`,
        body: '<div class="chart tall"></div>' }));
      body.appendChild(c1);
      if (pts.some((p) => p.points.some((x) => x[1] != null))) {
        timeChart(c1.querySelector(".chart"), { demo: meta.is_demo, series: pts.map((p, i) => ({ name: lines[i].name, points: p.points, color: LINE_COLOR[lines[i].dataset] || COLORS.other })) });
      } else c1.querySelector(".card-b").innerHTML = emptyState("No readings in this range");
      c1.querySelector('[data-a="csv"]').addEventListener("click", () => downloadText(`tieline_${range.startDay}_${range.endDay}.csv`, pointsToCsv(pts)));

      const th = lines.map((s, i) => [s, pts[i]]).filter(([s]) => s.dataset === "tieline_egat" || s.dataset === "tieline_hvdc");
      const c2 = h(card({ title: "Total flow with Thailand", desc: "The two Thailand links added together (EGAT + HVDC).", body: '<div class="chart"></div>' }));
      body.appendChild(c2);
      if (th.length === 2) timeChart(c2.querySelector(".chart"), { demo: meta.is_demo, series: [{ name: "Net (EGAT + HVDC)", points: sumSeries(th.map(([, p]) => p.points)), color: COLORS.net, area: true }] });
      else c2.querySelector(".card-b").innerHTML = emptyState("Needs both EGAT and HVDC readings");
    } catch (err) { body.innerHTML = errorState(err); }
  }
  await picker.start();
}
