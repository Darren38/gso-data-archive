// Tie-line flows.
import { getPoints, exportUrl } from "../data.js";
import { COLORS, timeChart } from "../charts.js";
import { alignStack, sumSeries, extent } from "../analysis.js";
import { addDays, card, shortForms, downloadText, emptyState, errorState, esc, fmtDateTime, fmtNum, h, kpi, loading, mytDayStart, pointsToCsv, rangePicker } from "../ui.js";

const LINE_COLOR = { tieline_egat: COLORS.egat, tieline_hvdc: COLORS.hvdc, tieline_pltg: COLORS.pltg };
const LINE_NAME = { tieline_egat: "EGAT (Thailand)", tieline_hvdc: "HVDC (Thailand)", tieline_pltg: "PLTG (Singapore)" };

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
        return kpi({ icon: "exchange", label: LINE_NAME[s.dataset] || s.dataset.replace("tieline_", "").toUpperCase(), value: s.latest_value != null ? fmtNum(s.latest_value) : null, unit: "MW",
          meta: `${s.last ? fmtDateTime(s.last) + " MYT" : ""}${e.max ? ` · range ${fmtNum(e.min[1])} to ${fmtNum(e.max[1])} MW` : ""}` });
      }).join("")}</div>`));
      body.appendChild(h(shortForms(["Tie-Line", "EGAT", "HVDC", "PLTG", "MW", "MYT"])));
      const c1 = h(card({ title: "Tie-Line Flows", sub: "MW as published", desc: "Power on the links to Thailand (EGAT, HVDC) and Singapore (PLTG). GSO publishes a reading every 30 minutes.",
        right: `<button class="btn" data-a="csv">CSV</button>${exportUrl(lines.map((s) => s.key), range.startDay, range.endDay, "xlsx") ? `<a class="btn" href="${esc(exportUrl(lines.map((s) => s.key), range.startDay, range.endDay, "xlsx"))}">Excel</a>` : ""}`,
        body: '<div class="chart tall"></div>' }));
      body.appendChild(c1);
      if (pts.some((p) => p.points.some((x) => x[1] != null))) {
        timeChart(c1.querySelector(".chart"), { demo: meta.is_demo, series: pts.map((p, i) => ({ name: LINE_NAME[lines[i].dataset] || lines[i].name, points: p.points, color: LINE_COLOR[lines[i].dataset] || COLORS.other })) });
      } else c1.querySelector(".card-b").innerHTML = emptyState("No readings in this range");
      c1.querySelector('[data-a="csv"]').addEventListener("click", () => downloadText(`tieline_${range.startDay}_${range.endDay}.csv`, pointsToCsv(pts)));

      const th = lines.map((s, i) => [s, pts[i]]).filter(([s]) => s.dataset === "tieline_egat" || s.dataset === "tieline_hvdc");
      const c2 = h(card({ title: "Net Exchange with Thailand", desc: "The two Thailand links added together (EGAT + HVDC).", body: '<div class="chart"></div>' }));
      body.appendChild(c2);
      if (th.length === 2) timeChart(c2.querySelector(".chart"), { demo: meta.is_demo, series: [{ name: "Net (EGAT + HVDC)", points: sumSeries(th.map(([, p]) => p.points)), color: COLORS.net, area: true }] });
      else c2.querySelector(".card-b").innerHTML = emptyState("Needs both EGAT and HVDC readings");

      // GSO's Cross-Border Power Exchange page ("Transaction Flow"), drawn as GSO draws it: stacked steps, GSO's
      // colours and order (CBESRE, MSBI, LTMS), every 30 minutes, MW as published.
      const CBPE = [["cbpe.cbesre", "#57A773"], ["cbpe.msbi", "#08B2E3"], ["cbpe.ltms", "#484D6D"]];
      const trades = CBPE.map(([key, color]) => [meta.series.find((x) => x.key === key), color]).filter(([x]) => x);
      if (trades.length) {
        const tp = await Promise.all(trades.map(([x]) => getPoints(x.key, start, end)));
        if (!isCurrent()) return;
        const aligned = alignStack(tp.map((p) => p.points), 1800e3);
        const c3 = h(card({ title: "Cross-Border Power Exchange", sub: "MW as published",
          desc: "From GSO's Cross-Border Power Exchange page (its \"Transaction Flow\" chart), every 30 minutes: CBESRE (ENEGEM), the Malaysia-Singapore Bilateral (MSBI) and LTMS 2.0 (Laos-Thailand-Malaysia-Singapore), stacked as GSO draws them. GSO doesn't say which direction a positive value means. Breaks mean GSO published no value.",
          body: '<div class="chart"></div>' }));
        body.appendChild(c3);
        if (aligned.some((pts) => pts.some((x) => x[1] != null))) {
          timeChart(c3.querySelector(".chart"), { demo: meta.is_demo, series: trades.map(([x, color], i) => ({
            name: x.name, points: aligned[i], color, stack: "cbpe", area: true, step: "end" })) });
        } else c3.querySelector(".card-b").innerHTML = emptyState("No readings in this range", "Kept from 30 October 2026.");
      }
    } catch (err) { body.innerHTML = errorState(err); }
  }
  await picker.start();
}
