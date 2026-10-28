// Historical Explorer: any series, any range, table + exports + revision history.
import { exportUrl, getPoints, getRevisions, MODE } from "../data.js";
import { COLORS, timeChart } from "../charts.js";
import { addDays, card, getParam, setParams, downloadText, emptyState, errorState, esc, fmtDateTime, fmtNum, h, loading, mytDayStart, pointsToCsv, rangePicker, renderTable, verificationTag } from "../ui.js";

const PALETTE = [COLORS.solar, COLORS.demand, COLORS.gas, COLORS.hydro, COLORS.coal, COLORS.egat, COLORS.hvdc, COLORS.pltg, COLORS.cogen, COLORS.oil, COLORS.forecast, COLORS.net];

export async function render(main, { meta, isCurrent }) {
  if (!meta.series.length) {
    main.innerHTML = card({ title: "Historical Explorer", body: emptyState("No series archived yet") });
    return;
  }
  const groups = {};
  for (const s of meta.series) (groups[s.dataset] = groups[s.dataset] || []).push(s);
  const known = new Set(meta.series.map((s) => s.key));
  const pre = (getParam("series") || "").split(",").filter((k) => known.has(k)).slice(0, 12); // ignore unknown keys in links
  const selected = new Set(pre.length ? pre : [meta.series.find((s) => s.key === "generation_mix.solar")?.key || meta.series[0].key]);

  const pick = h(card({ title: "Series", sub: "Select up to 12", body: `<div class="series-pick">${Object.entries(groups).map(([ds, list]) => `
      <fieldset><legend>${esc(ds)}</legend>${list.map((s) => `<label><input type="checkbox" value="${esc(s.key)}" ${selected.has(s.key) ? "checked" : ""}>
        ${esc(s.name)} <span class="muted small">(${esc(s.unit)}${s.kind !== "actual" ? `, ${esc(s.kind)}` : ""})</span></label>`).join("")}</fieldset>`).join("")}</div>` }));
  main.appendChild(pick);
  const bar = h("<div></div>"); main.appendChild(bar);
  const body = h('<div class="grid"></div>'); main.appendChild(body);
  let range = null;
  pick.querySelectorAll("input[type=checkbox]").forEach((cb) => cb.addEventListener("change", () => {
    if (cb.checked) { if (selected.size >= 12) { cb.checked = false; return; } selected.add(cb.value); } else selected.delete(cb.value);
    setParams({ series: [...selected].join(",") || null });
    draw();
  }));
  const picker = rangePicker(bar, { initial: "7d", presets: ["1d", "7d", "30d", "90d", "1y"], onChange: (r) => { range = r; return draw(); } });

  async function draw() {
    const keys = [...selected];
    if (!keys.length) { body.innerHTML = card({ title: "Chart", body: emptyState("Select at least one series") }); return; }
    const start = mytDayStart(range.startDay), end = mytDayStart(addDays(range.endDay, 1));
    body.innerHTML = loading(380);
    try {
      const pts = await Promise.all(keys.map((k) => getPoints(k, start, end)));
      if (!isCurrent()) return;
      const infos = keys.map((k) => meta.series.find((s) => s.key === k));
      const units = [...new Set(infos.map((s) => s.unit))];
      body.innerHTML = "";
      const xlsx = exportUrl(keys, range.startDay, range.endDay, "xlsx");
      const c1 = h(card({ title: "Chart", desc: "Every series you ticked, over the dates you chose. Breaks mean no reading, never zero.", sub: units.length > 1 ? "Mixed units — second unit on right axis" : "",
        right: `<button class="btn" data-a="csv">CSV</button>${xlsx ? `<a class="btn primary" href="${esc(xlsx)}">Excel</a>` : '<span class="small muted">Excel export requires API mode</span>'}`,
        body: '<div class="chart tall"></div>' }));
      body.appendChild(c1);
      if (pts.some((p) => p.points.some((x) => x[1] != null))) {
        timeChart(c1.querySelector(".chart"), { demo: meta.is_demo,
          yAxes: units.slice(0, 2).map((u) => ({ name: u, scale: true })),
          series: pts.map((p, i) => ({ name: infos[i].name, unit: infos[i].unit, points: p.points, color: PALETTE[i % PALETTE.length], dashed: infos[i].kind === "forecast", yAxisIndex: Math.min(1, units.indexOf(infos[i].unit)) })) });
      } else c1.querySelector(".card-b").innerHTML = emptyState("No readings in this range", "Absent readings are shown as gaps and exported as absent rows, never as zero.");
      c1.querySelector('[data-a="csv"]').addEventListener("click", () => downloadText(`gso_export_${range.startDay}_${range.endDay}.csv`, pointsToCsv(pts)));

      const flat = [];
      pts.forEach((p, i) => p.points.forEach(([t, v, q]) => { if (v != null) flat.push({ series: infos[i].key, t, v, unit: infos[i].unit, q }); }));
      flat.sort((a, b) => (a.t < b.t ? 1 : -1));
      const c2 = h(card({ title: "Readings", sub: infos.map((s) => `${verificationTag(s.verification)}`).filter((v, i, a) => a.indexOf(v) === i).join(" "), body: '<div class="tbl"></div>' }));
      body.appendChild(c2);
      renderTable(c2.querySelector(".tbl"), [
        { key: "t", label: "Observation time (MYT)", fmt: (v) => fmtDateTime(v) },
        { key: "t", label: "UTC", fmt: (v) => `<span class="mono">${esc(v)}</span>` },
        { key: "series", label: "Series", fmt: (v) => `<span class="mono">${esc(v)}</span>` },
        { key: "v", label: "Value", num: true, fmt: (v) => fmtNum(v, 1) },
        { key: "unit", label: "Unit" },
        { key: "q", label: "Quality" },
      ], flat, 100);

      const c3 = h(card({ title: "Revision history", sub: "Readings the source changed after first collection", body: '<div class="tbl"></div>' }));
      body.appendChild(c3);
      if (MODE === "static") { c3.querySelector(".tbl").innerHTML = '<p class="muted small">Revision history is available in API mode.</p>'; return; }
      const revs = await Promise.all(keys.map((k) => getRevisions(k, start, end)));
      const rows = revs.flatMap((r) => r.revisions.map((x) => ({ ...x, series: r.series })));
      if (!rows.length) c3.querySelector(".tbl").innerHTML = emptyState("No revisions in this range", "Every value seen so far has stayed the same after first collection.");
      else renderTable(c3.querySelector(".tbl"), [
        { key: "obs_time", label: "Observation (MYT)", fmt: (v) => fmtDateTime(v) },
        { key: "series", label: "Series", fmt: (v) => `<span class="mono">${esc(v)}</span>` },
        { key: "previous_value", label: "Previous", num: true, fmt: (v) => fmtNum(v, 1) },
        { key: "value", label: "Revised to", num: true, fmt: (v) => fmtNum(v, 1) },
        { key: "revised_at", label: "Revised at (MYT)", fmt: (v) => fmtDateTime(v) },
      ], rows, 50);
    } catch (err) { body.innerHTML = errorState(err); }
  }
  await picker.start();
}
