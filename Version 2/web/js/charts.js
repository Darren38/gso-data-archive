// ECharts wrappers. Times are shifted by +8 h and rendered with useUTC so every
// axis label and tooltip is Malaysia time regardless of the viewer's timezone.
import { MYT_OFFSET_MS, fmtNum } from "./ui.js";

export const COLORS = {
  solar: "#e39a0b", solar2: "#f6c453", solar3: "#b86e00", forecast: "#7a5af5",
  demand: "#2f6fd6", coal: "#5b6573", gas: "#3b82c4", hydro: "#13a1a1", oil: "#9c5b2e",
  cogen: "#8e6cc2", other: "#9aa5b1", egat: "#d0527a", hvdc: "#2aa876", pltg: "#d9822b", net: "#334155",
};

const instances = new Set();
let observer = null;

function css(name) { return getComputedStyle(document.documentElement).getPropertyValue(name).trim(); }

function base(demo) {
  const text = css("--text-2"), grid = css("--border");
  return {
    useUTC: true,
    animation: false,
    textStyle: { fontFamily: css("--sans") || "system-ui", color: text },
    grid: { left: 56, right: 24, top: 52, bottom: 56, containLabel: false },
    legend: { top: 0, left: 64, right: 72, type: "scroll", textStyle: { color: text }, icon: "roundRect", itemWidth: 12, itemHeight: 8 },
    tooltip: {
      trigger: "axis", backgroundColor: css("--surface"), borderColor: grid, textStyle: { color: css("--text") },
      confine: true,
    },
    _axis: { axisLine: { lineStyle: { color: grid } }, axisLabel: { color: css("--text-3"), hideOverlap: true }, splitLine: { lineStyle: { color: grid, opacity: 0.6 } } },
    graphic: demo ? [{ type: "text", left: "center", top: "middle", silent: true, z: -1,
      style: { text: "DEMONSTRATION DATA", fontSize: 28, fontWeight: 700, fill: css("--demo"), opacity: 0.12 } }] : [],
  };
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

export function disposeAll() {
  instances.forEach((c) => !c.isDisposed() && c.dispose());
  instances.clear();
}

const shift = (iso) => Date.parse(iso) + MYT_OFFSET_MS;
const tsLabel = (ms) => new Date(ms).toISOString().slice(0, 16).replace("T", " ");

/** Time-series line/area chart.
 * series: [{name, points:[[iso, v|null, q]], color, area, dashed, yAxisIndex, stack, step, type}]
 */
export function timeChart(el, { series, yAxes = [{ name: "MW" }], demo = false, zoom = true, unit = "MW", digits = 0, markNow = false }) {
  const b = base(demo);
  const option = {
    ...b,
    grid: { ...b.grid, bottom: zoom ? 64 : 30, right: yAxes.length > 1 ? 60 : 24 },
    xAxis: { type: "time", ...b._axis, splitLine: { show: false },
      axisLabel: { ...b._axis.axisLabel, formatter: { day: "{d} {MMM}", hour: "{HH}:{mm}", minute: "{HH}:{mm}", month: "{MMM} {yyyy}", year: "{yyyy}" } } },
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
  const option = {
    ...b,
    grid: { ...b.grid, bottom: zoom ? 64 : 40, right: yAxes.length > 1 ? 64 : 24 },
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

export function pieChart(el, { items, demo = false, unit = "MWh" }) {
  const b = base(demo);
  return mount(el, {
    ...b,
    tooltip: { trigger: "item", backgroundColor: css("--surface"), borderColor: css("--border"), textStyle: { color: css("--text") },
      formatter: (p) => `${p.marker}${p.name}: <b>${fmtNum(p.value, 0)} ${unit}</b> (${p.percent.toFixed(1)}%)` },
    legend: { ...b.legend, top: "bottom" },
    series: [{ type: "pie", radius: ["45%", "72%"], center: ["50%", "45%"], avoidLabelOverlap: true,
      itemStyle: { borderColor: css("--surface"), borderWidth: 2 }, label: { color: css("--text-2"), formatter: "{b}\n{d}%" },
      data: items.map((i) => ({ name: i.name, value: i.value, itemStyle: { color: i.color } })) }],
  });
}

/** Intraday profile: x = minutes since MYT midnight, one line per group. */
export function profileChart(el, { groups, demo = false, unit = "MW" }) {
  const b = base(demo);
  const label = (m) => `${String(Math.floor(m / 60)).padStart(2, "0")}:${String(m % 60).padStart(2, "0")}`;
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
