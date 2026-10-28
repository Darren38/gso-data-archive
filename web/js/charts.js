// ECharts wrappers. Times are shifted by +8 h and rendered with useUTC so every
// axis label and tooltip is Malaysia time regardless of the viewer's timezone.
import { MYT_OFFSET_MS, clock, fmtNum } from "./ui.js";

// Colours follow GSO's own charts (gso.org.my Scripts/utils.js, Solar.v19.js, SolarLandingPage.v5.js), so the archive
// reads the same way as the source. Lines that would be too pale on white use a slightly darker shade of GSO's colour.
export const COLORS = {
  solar: "#f2ad00", solar2: "#FFC30F", solar3: "#e08a00",
  forecast: "#23AF4E", // GSO solar forecast
  demand: "#466799", demandLight: "#8fa6c9", gridDemand: "#000040",
  coal: "#464646", gas: "#428DF5", hydro: "#25D366", oil: "#FC5E55", cogen: "#A9206E", tieline: "#A2D878", otherRe: "#BA6581",
  dnSolar: "#FFED26", gridSolar: "#FFC30F",
  bessDischarge: "#00C853", bessCharge: "#FF1493",
  other: "#9aa5b1", egat: "#6aa84f", hvdc: "#2e8b57", pltg: "#3d6fb6", net: "#334155",
};

/** GSO Solar page series, bottom to top as GSO stacks them. */
export const SOLAR_PARTS = [
  { key: "solar_profile.grid", label: "Grid", color: "#FF956E" },
  { key: "solar_profile.distribution", label: "Distribution", color: "#FFAC54" },
  { key: "solar_profile.nem", label: "NEM", color: "#FFC78A" },
  { key: "solar_profile.fit", label: "FiT", color: "#F0DB7A" },
  { key: "solar_profile.selco", label: "SELCO", color: "#EEF56C" },
];

/** Generation sources with GSO's colours. */
export const FUELS = [
  { key: "generation_mix.coal", label: "Coal", color: COLORS.coal },
  { key: "generation_mix.gas", label: "Gas", color: COLORS.gas },
  { key: "generation_mix.hydro", label: "Hydro", color: COLORS.hydro },
  { key: "generation_mix.solar", label: "Transmission Solar", color: COLORS.gridSolar },
  { key: "genmix_live.distribution_solar", label: "Distribution Solar", color: COLORS.dnSolar },
  { key: "genmix_live.other_re", label: "Other RE", color: COLORS.otherRe },
  { key: "generation_mix.cogen", label: "Co-Gen", color: COLORS.cogen },
  { key: "generation_mix.oil", label: "Oil/DF", color: COLORS.oil },
];

const instances = new Set();
let observer = null;

function css(name) { return getComputedStyle(document.documentElement).getPropertyValue(name).trim(); }

function base(demo) {
  const text = css("--text-2"), grid = css("--border");
  return {
    useUTC: true,
    animation: false,
    textStyle: { fontFamily: css("--sans") || "system-ui", color: text, fontSize: 13 },
    grid: { left: 56, right: 24, top: 52, bottom: 56, containLabel: false },
    legend: { top: 0, left: 64, right: 72, type: "scroll", textStyle: { color: text, fontSize: 13 }, icon: "roundRect", itemWidth: 14, itemHeight: 10 },
    tooltip: {
      trigger: "axis", backgroundColor: css("--surface"), borderColor: grid, textStyle: { color: css("--text"), fontSize: 13 },
      confine: true,
    },
    _axis: { axisLine: { lineStyle: { color: grid } }, axisLabel: { color: css("--text-2"), hideOverlap: true, fontSize: 12.5 }, splitLine: { lineStyle: { color: grid, opacity: 0.6 } } },
    graphic: demo ? [{ type: "text", left: "center", top: "middle", silent: true, z: -1,
      style: { text: "DEMONSTRATION DATA", fontSize: 28, fontWeight: 700, fill: css("--demo"), opacity: 0.12 } }] : [],
  };
}

/** A legend that wraps onto more lines instead of hiding names behind "1/6" arrows, and the plot top that leaves room for it. */
function legendFor(el, names, legend, { left = 64, right = 72, room = 0.35 } = {}) {
  const avail = Math.max(120, (el.clientWidth || 600) - left - right);
  let rows = 1, x = 0;
  for (const n of names) {
    const w = String(n).length * 7.2 + 30;
    if (x && x + w > avail) { rows += 1; x = 0; }
    x += w;
  }
  if (rows > 6 || rows * 23 > (el.clientHeight || 330) * room) return { legend, rows: 1, top: 52 }; // very long lists keep the scrolling legend
  return { legend: { ...legend, type: "plain", left, right }, rows, top: 30 + rows * 23 };
}

function mount(el, option) {
  if (!window.echarts) { el.innerHTML = '<div class="state error"><h3>Chart library failed to load</h3></div>'; return null; }
  const existing = window.echarts.getInstanceByDom(el);
  if (existing) existing.dispose();
  const chart = window.echarts.init(el, null, { renderer: "canvas" });
  chart.setOption(option, true);
  instances.add(chart);
  if (!observer) {
    observer = new ResizeObserver(() => instances.forEach((c) => !c.isDisposed() && c.resize()));
    observer.observe(document.getElementById("main"));
  }
  return chart;
}

/** Dispose charts whose container has left the page (after a live refresh swapped the page). */
export function disposeDetached() {
  instances.forEach((c) => {
    if (c.isDisposed() || !c.getDom().isConnected) { if (!c.isDisposed()) c.dispose(); instances.delete(c); }
  });
}

export function disposeAll() {
  instances.forEach((c) => !c.isDisposed() && c.dispose());
  instances.clear();
}

const shift = (iso) => Date.parse(iso) + MYT_OFFSET_MS;
// Chart times are shifted to MYT and read as UTC, so getUTC* gives Malaysia time.
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const tsLabel = (ms) => { const d = new Date(ms); return `${d.toISOString().slice(0, 10)} ${clock(d.getUTCHours(), d.getUTCMinutes())}`; };
/** Time-axis label: a clock time, or the date at midnight (month or year on the 1st). */
function axisTime(ms) {
  const d = new Date(ms), h = d.getUTCHours(), m = d.getUTCMinutes();
  if (h || m) return clock(h, m);
  const day = d.getUTCDate(), mo = d.getUTCMonth(), y = d.getUTCFullYear();
  if (day === 1 && mo === 0) return String(y);
  return day === 1 ? `${MONTHS[mo]} ${y}` : `${day} ${MONTHS[mo]}`;
}

/** Time-series line/area chart.
 * series: [{name, points:[[iso, v|null, q]], color, area, dashed, yAxisIndex, stack, step, type}]
 */
export function timeChart(el, { series, yAxes = [{ name: "MW" }], demo = false, zoom = true, unit = "MW", digits = 0, markNow = false, legendOrder = null }) {
  const b = base(demo);
  const narrow = el.clientWidth < 400;
  const lg = legendFor(el, legendOrder || series.map((s) => s.name), b.legend, narrow ? { left: 8, right: 8 } : undefined);
  if (legendOrder) lg.legend = { ...lg.legend, data: legendOrder };
  const option = {
    ...b,
    legend: lg.legend,
    grid: { ...b.grid, top: lg.top, bottom: zoom ? 64 : 30, left: el.clientWidth < 400 ? 46 : 56,
      right: yAxes.length > 1 ? (el.clientWidth < 400 ? 46 : 60) : 24 },
    xAxis: { type: "time", ...b._axis, splitLine: { show: false },
      // Narrow charts (phones) get fewer ticks so labels like "27 Oct" and "12:00" never run together.
      splitNumber: el.clientWidth < 400 ? 2 : el.clientWidth < 520 ? 3 : el.clientWidth < 760 ? 5 : undefined,
      axisLabel: { ...b._axis.axisLabel, fontSize: el.clientWidth < 400 ? 11 : 12.5, formatter: axisTime } },
    yAxis: yAxes.map((y, i) => ({ type: "value", name: y.name, nameTextStyle: { color: css("--text-3"), align: i ? "right" : "left" },
      position: i ? "right" : "left", scale: !!y.scale, min: y.min, max: y.max, ...b._axis, splitLine: i ? { show: false } : b._axis.splitLine,
      axisLabel: { ...b._axis.axisLabel, formatter: (v) => fmtNum(v, y.digits ?? 0) } })),
    tooltip: { ...b.tooltip,
      formatter: (params) => {
        if (!params.length) return "";
        const head = `<b>${tsLabel(params[0].value[0])} MYT</b>`;
        const lines = params.map((p) => {
          const v = p.value[1];
          const q = p.value[2] && p.value[2] !== "ok" ? ` <span style="opacity:.7">(${p.value[2]})</span>` : "";
          return `${p.marker}${p.seriesName}: <b>${v == null ? "no reading" : fmtNum(v, digits) + " " + (series[p.seriesIndex].unit || unit)}</b>${q}`;
        });
        return [head, ...lines].join("<br>");
      } },
    dataZoom: zoom ? [{ type: "inside", filterMode: "none" }, { type: "slider", height: 22, bottom: 8, filterMode: "none", borderColor: css("--border"), textStyle: { color: css("--text-3") }, labelFormatter: (v) => tsLabel(v) }] : [],
    series: series.map((s) => ({
      name: s.name, type: s.type || "line", yAxisIndex: s.yAxisIndex || 0, stack: s.stack, step: s.step,
      showSymbol: false, connectNulls: false, sampling: "lttb", smooth: false,
      lineStyle: { width: s.width || 1.8, type: s.dashed ? "dashed" : "solid", color: s.color },
      itemStyle: { color: s.color },
      areaStyle: s.area ? { opacity: s.areaOpacity ?? 0.18, color: s.color } : undefined,
      emphasis: { focus: "series" },
      data: s.points.map((p) => [shift(p[0]), p[1], p[2]]),
      markLine: markNow && s === series[0] ? { silent: true, symbol: "none", lineStyle: { color: css("--text-3"), type: "dotted" }, label: { formatter: "now", color: css("--text-3") }, data: [{ xAxis: Date.now() + MYT_OFFSET_MS }] } : undefined,
    })),
  };
  return mount(el, option);
}

/** Category (e.g. daily) bar/line combo chart. */
export function categoryChart(el, { categories, series, yAxes = [{ name: "MW" }], demo = false, zoom = false, tooltipExtra }) {
  const b = base(demo);
  const lg = legendFor(el, series.map((s) => s.name), b.legend, el.clientWidth < 400 ? { left: 8, right: 8 } : undefined);
  const option = {
    ...b,
    legend: lg.legend,
    grid: { ...b.grid, top: lg.top, bottom: zoom ? 64 : 40, right: yAxes.length > 1 ? 64 : 24 },
    xAxis: { type: "category", data: categories, ...b._axis, splitLine: { show: false } },
    yAxis: yAxes.map((y, i) => ({ type: "value", name: y.name, position: i ? "right" : "left", nameTextStyle: { color: css("--text-3") },
      ...b._axis, splitLine: i ? { show: false } : b._axis.splitLine, axisLabel: { ...b._axis.axisLabel, formatter: (v) => fmtNum(v, y.digits ?? 0) } })),
    tooltip: { ...b.tooltip, axisPointer: { type: "shadow" },
      formatter: (params) => {
        const head = `<b>${params[0].axisValue}</b>`;
        const lines = params.map((p) => `${p.marker}${p.seriesName}: <b>${p.value == null ? "no data" : fmtNum(p.value, series[p.seriesIndex].digits ?? 0) + " " + (series[p.seriesIndex].unit || "")}</b>`);
        const extra = tooltipExtra ? tooltipExtra(params[0].dataIndex) : "";
        return [head, ...lines].join("<br>") + (extra ? `<br>${extra}` : "");
      } },
    dataZoom: zoom ? [{ type: "inside" }, { type: "slider", height: 22, bottom: 8, borderColor: css("--border"), textStyle: { color: css("--text-3") } }] : [],
    series: series.map((s) => ({
      name: s.name, type: s.type || "bar", yAxisIndex: s.yAxisIndex || 0, stack: s.stack, data: s.data,
      itemStyle: { color: s.color, borderRadius: s.type === "line" ? 0 : [2, 2, 0, 0] }, lineStyle: { color: s.color, width: 2, type: s.dashed ? "dashed" : "solid" },
      showSymbol: s.type === "line" && s.data.length < 60, connectNulls: false, barMaxWidth: 26,
    })),
  };
  return mount(el, option);
}

const energyText = (mwh) => (mwh >= 1e6 ? `${fmtNum(mwh / 1e6, 2)} TWh` : mwh >= 1e3 ? `${fmtNum(mwh / 1e3, 1)} GWh` : `${fmtNum(mwh, 0)} MWh`);

/** Donut in GSO's style: "Gas: 36.5%" labels, round legend dots, and the total in the middle. */
export function pieChart(el, { items, demo = false, unit = "MWh", total = false }) {
  const b = base(demo);
  const lg = legendFor(el, items.map((i) => i.name), { ...b.legend, icon: "circle", itemWidth: 12, itemHeight: 12 }, { left: 8, right: 8, room: 0.5 });
  const roomy = lg.rows <= 1;
  const cy = roomy ? 45 : 45 - lg.rows * 3;
  const sum = items.reduce((t, i) => t + (i.value || 0), 0);
  const wide = el.clientWidth >= 480;
  return mount(el, {
    ...b,
    tooltip: { trigger: "item", backgroundColor: css("--surface"), borderColor: css("--border"), textStyle: { color: css("--text") },
      formatter: (p) => `${p.marker}${p.name}: <b>${fmtNum(p.value, 0)} ${unit}</b> (${p.percent.toFixed(1)}%)` },
    legend: { ...lg.legend, top: "bottom" },
    title: total ? { text: unit === "MWh" ? energyText(sum) : `${fmtNum(sum, 0)} ${unit}`, left: "center", top: `${cy}%`, textVerticalAlign: "middle",
      textStyle: { color: css("--gso-green"), fontSize: wide ? 24 : 17, fontWeight: 600 } } : undefined,
    series: [{ type: "pie", radius: roomy ? ["50%", "72%"] : ["44%", "64%"], center: ["50%", `${cy}%`], avoidLabelOverlap: true,
      itemStyle: { borderColor: css("--surface"), borderWidth: 1.5 },
      // Slice labels only where they fit; on phones the legend and tooltip name the slices.
      label: { show: wide, color: css("--text"), fontWeight: 500, lineHeight: 15, overflow: "break", width: 96,
        formatter: (p) => `${p.name}: ${p.percent.toFixed(1)}%` }, labelLine: { show: wide, length: 10, length2: 8 },
      data: items.map((i) => ({ name: i.name, value: i.value, itemStyle: { color: i.color } })) }],
  });
}

/** Intraday profile: x = minutes since MYT midnight, one line per group. */
export function profileChart(el, { groups, demo = false, unit = "MW" }) {
  const b = base(demo);
  const label = (m) => clock(Math.floor(m / 60) % 24, m % 60);
  return mount(el, {
    ...b,
    xAxis: { type: "value", min: 0, max: 1440, interval: 180, ...b._axis, splitLine: { show: false }, axisLabel: { ...b._axis.axisLabel, formatter: label } },
    yAxis: { type: "value", name: unit, ...b._axis, axisLabel: { ...b._axis.axisLabel, formatter: (v) => fmtNum(v) } },
    tooltip: { ...b.tooltip, formatter: (ps) => [`<b>${label(ps[0].value[0])} MYT</b>`, ...ps.map((p) => `${p.marker}${p.seriesName}: <b>${fmtNum(p.value[1])} ${unit}</b>`)].join("<br>") },
    series: groups.map((g) => ({ name: g.name, type: "line", showSymbol: false, data: g.data, connectNulls: false, lineStyle: { width: g.width || 1.6, color: g.color }, itemStyle: { color: g.color } })),
  });
}

/** Re-render hook for theme switches. */
export function onThemeChange(fn) { document.addEventListener("gso-theme", fn); }

let mapReady = null;
/** Peninsular Malaysia outline (Natural Earth, see vendor/peninsular-malaysia.geo.LICENSE), loaded once. */
function loadMap() {
  if (!mapReady) {
    mapReady = fetch("vendor/peninsular-malaysia.geo.json").then((r) => {
      if (!r.ok) throw new Error(`map outline: HTTP ${r.status}`);
      return r.json();
    }).then((geo) => { window.echarts.registerMap("peninsular", geo); }).catch((e) => { mapReady = null; throw e; });
  }
  return mapReady;
}

/** Solar map like GSO's: every LSS farm at its place, coloured by output as a % of its capacity, sized by capacity.
 * farms: [{code, state, region, conn, mw, cap, pct, lat, lon}] */
export async function solarMap(el, { farms, demo = false }) {
  if (!window.echarts) { el.innerHTML = '<div class="state error"><h3>Chart library failed to load</h3></div>'; return null; }
  await loadMap();
  const b = base(demo);
  const narrow = el.clientWidth < 480;
  const maxCap = Math.max(1, ...farms.map((f) => f.cap || 0));
  const point = (f) => ({ name: f.code, value: [f.lon, f.lat, f.pct], farm: f,
    symbol: f.conn === "distribution" ? "diamond" : "circle",
    symbolSize: (narrow ? 7 : 9) + (narrow ? 12 : 18) * Math.sqrt((f.cap || 0) / maxCap) });
  return mount(el, {
    ...b,
    tooltip: { trigger: "item", backgroundColor: css("--surface"), borderColor: css("--border"), textStyle: { color: css("--text"), fontSize: 13 },
      formatter: (p) => {
        const f = p.data?.farm;
        if (!f) return "";
        return `<b>${f.code}</b> · ${f.state}, ${f.region}<br>${f.conn === "distribution" ? "Distribution" : "Grid"} connected<br>` +
          `<b>${fmtNum(f.mw, 1)} MW</b> of ${fmtNum(f.cap)} MW` + (f.pct == null ? "" : ` (<b>${fmtNum(f.pct, 0)}%</b> of capacity)`);
      } },
    geo: { map: "peninsular", roam: true, scaleLimit: { min: 1, max: 8 }, boundingCoords: [[99.6, 6.8], [104.4, 1.2]],
      // keep the true shape: near the equator a degree east is about as long as a degree north (aspectScale 1)
      aspectScale: 1, layoutCenter: ["50%", "46%"], layoutSize: "90%",
      itemStyle: { areaColor: css("--surface-2"), borderColor: css("--border"), borderWidth: 0.8 },
      regions: [{ name: "Malaysia", itemStyle: { areaColor: "rgba(31, 166, 74, 0.10)", borderColor: css("--text-3"), borderWidth: 1 } }],
      emphasis: { disabled: true }, select: { disabled: true }, tooltip: { show: false }, silent: true },
    visualMap: { type: "continuous", min: 0, max: 100, dimension: 2, calculable: false, orient: "horizontal",
      left: "center", bottom: 4, itemWidth: 12, itemHeight: narrow ? 160 : 220, text: ["100% of capacity", "0%"],
      textStyle: { color: css("--text-2"), fontSize: 12 },
      inRange: { color: ["#9aa5b1", "#FFE066", "#F2AD00", "#E06D00"] }, outOfRange: { color: "#9aa5b1" } },
    series: [{ type: "scatter", coordinateSystem: "geo", data: farms.filter((f) => f.lat != null && f.lon != null).map(point),
      itemStyle: { borderColor: css("--surface"), borderWidth: 1, opacity: 0.95 },
      emphasis: { scale: 1.3, label: { show: true, formatter: "{b}", position: "top", color: css("--text"), fontWeight: 600 } } }],
  });
}
