// Battery energy storage (BESS): discharge and charge from GSO's home page chart.
import { getDaily, getPoints, exportUrl } from "../data.js";
import { COLORS, categoryChart, timeChart } from "../charts.js";
import { sumSeries } from "../analysis.js";
import { addDays, card, shortForms, downloadText, emptyState, errorState, esc, fmtDateTime, fmtEnergy, fmtNum, h, kpi, loading, mytDayStart, pointsToCsv, rangePicker, verificationTag } from "../ui.js";

const BESS_GREEN = COLORS.bessDischarge, BESS_PINK = COLORS.bessCharge;

export async function render(main, { meta, isCurrent }) {
  const dis = meta.series.find((s) => s.key === "genmix_live.bess_discharge");
  const chg = meta.series.find((s) => s.key === "genmix_live.bess_charge");
  const avail = meta.series.find((s) => s.key === "availability.bess");
  if (!dis && !chg) {
    main.appendChild(h(card({ title: "Battery energy storage (BESS)", body: emptyState("No BESS readings archived yet",
      "BESS discharge and charge come from the chart on GSO's home page, which publishes today's values only. They appear here once collection has run.", "▭") })));
    return;
  }
  main.appendChild(h(`<div class="notice">GSO publishes battery readings for today only, so the history here starts when this archive began collecting.</div>`));
  const bar = h("<div></div>"); main.appendChild(bar);
  const body = h('<div class="grid"></div>'); main.appendChild(body);
  const picker = rangePicker(bar, { initial: "2d", presets: ["1d", "2d", "7d", "30d", "90d"], onChange: (r) => draw(r) });

  async function draw(range) {
    const start = mytDayStart(range.startDay), end = mytDayStart(addDays(range.endDay, 1));
    body.innerHTML = loading(120) + loading(360);
    try {
      const keys = [dis, chg].filter(Boolean);
      const [pts, daily] = await Promise.all([
        Promise.all(keys.map((s) => getPoints(s.key, start, end))),
        Promise.all(keys.map((s) => getDaily(s.key, range.startDay, range.endDay))),
      ]);
      if (!isCurrent()) return;
      const net = pts.length === 2 ? sumSeries(pts.map((p) => p.points)) : pts[0].points;
      const disDaily = dis ? daily[0].rows : [], chgDaily = chg ? daily[keys.indexOf(chg)].rows : [];
      const energyOut = disDaily.reduce((t, r) => t + (r.energy_mwh || 0), 0);
      const energyIn = Math.abs(chgDaily.reduce((t, r) => t + (r.energy_mwh || 0), 0));
      const latestNet = dis && chg && dis.latest_value != null && chg.latest_value != null ? dis.latest_value + chg.latest_value : null;
      body.innerHTML = "";
      body.appendChild(h(`<div class="grid kpis">
        ${kpi({ big: true, cls: "bess", icon: "battery", label: "Current BESS Status", value: latestNet != null ? fmtNum(Math.abs(latestNet)) : null, unit: "MW", meta: dis?.last ? `${latestNet > 0 ? "Discharging" : latestNet < 0 ? "Charging" : "Idle"} · ${fmtDateTime(dis.last)} MYT` : "" })}
        ${kpi({ icon: "battery", label: "BESS Discharge", value: dis && dis.latest_value != null ? fmtNum(dis.latest_value) : null, unit: "MW" })}
        ${kpi({ icon: "battery", label: "BESS Charge", value: chg && chg.latest_value != null ? fmtNum(Math.abs(chg.latest_value)) : null, unit: "MW" })}
        ${kpi({ icon: "plant", label: "BESS Availability", value: avail && avail.latest_value != null ? fmtNum(avail.latest_value) : null, unit: "MW", meta: avail?.last ? `${fmtDateTime(avail.last)} MYT` : "" })}
        ${kpi({ icon: "energy", label: "Energy Discharged", value: disDaily.some((r) => r.count) ? fmtEnergy(energyOut) : null, meta: "In this period" })}
        ${kpi({ icon: "energy", label: "Energy Charged", value: chgDaily.some((r) => r.count) ? fmtEnergy(energyIn) : null, meta: "In this period" })}
      </div>`));
      body.appendChild(h(shortForms(["BESS", "MW", "MWh", "MYT"])));
      const xl = exportUrl(keys.map((s) => s.key), range.startDay, range.endDay, "xlsx");
      const c1 = h(card({ title: "BESS Discharge & Charge", desc: "Green above zero: discharge (batteries supplying the grid). Pink below zero: charge. Dark line: Net, the two together.", sub: verificationTag(dis?.verification || chg?.verification),
        right: `<button class="btn" data-a="csv">CSV</button>${xl ? `<a class="btn" href="${esc(xl)}">Excel</a>` : ""}`, body: '<div class="chart tall"></div>' }));
      body.appendChild(c1);
      if (pts.some((p) => p.points.some((q) => q[1] != null))) {
        const series = [];
        if (dis) series.push({ name: "Discharge", points: pts[0].points, color: BESS_GREEN, area: true, areaOpacity: 0.45 });
        if (chg) series.push({ name: "Charge", points: pts[keys.indexOf(chg)].points, color: BESS_PINK, area: true, areaOpacity: 0.45 });
        if (pts.length === 2) series.push({ name: "Net", points: net, color: COLORS.net, width: 1.6 });
        timeChart(c1.querySelector(".chart"), { series, demo: meta.is_demo });
      } else c1.querySelector(".card-b").innerHTML = emptyState("No BESS readings in this range");
      c1.querySelector('[data-a="csv"]').addEventListener("click", () => downloadText(`bess_${range.startDay}_${range.endDay}.csv`, pointsToCsv(pts)));
      if (disDaily.length) {
        const c2 = h(card({ title: "Daily BESS Energy", desc: "Green: energy discharged each day. Pink: energy charged (MWh).", body: '<div class="chart short"></div>' }));
        body.appendChild(c2);
        if (disDaily.some((r) => r.count) || chgDaily.some((r) => r.count)) {
          categoryChart(c2.querySelector(".chart"), { categories: disDaily.map((r) => r.date.slice(5)), demo: meta.is_demo, yAxes: [{ name: "MWh" }],
            series: [
              { name: "Discharged", data: disDaily.map((r) => r.energy_mwh), color: BESS_GREEN, unit: "MWh" },
              { name: "Charged", data: chgDaily.map((r) => (r.energy_mwh == null ? null : Math.abs(r.energy_mwh))), color: BESS_PINK, unit: "MWh" },
            ] });
        } else c2.querySelector(".card-b").innerHTML = emptyState("No daily totals yet");
      }
    } catch (err) { body.innerHTML = errorState(err); }
  }
  await picker.start();
}
