// GSO's "System Demand Profile for Peninsular Malaysia" chart: generation stacked by source in GSO's order,
// with GSO's Grid Demand line (total generation) and the System Demand line drawn on top.
import { getPoints } from "./data.js";
import { COLORS, timeChart } from "./charts.js";
import { alignStack } from "./analysis.js";

/** Stacked sources, bottom to top as GSO draws them. GSO's legend lists them top first. */
export const PROFILE_STACK = [
  { key: "generation_mix.coal", label: "Coal", color: COLORS.coal },
  { key: "generation_mix.gas", label: "Gas", color: COLORS.gas },
  { key: "generation_mix.cogen", label: "Co-Gen", color: COLORS.cogen },
  { key: "generation_mix.oil", label: "Oil/DF", color: COLORS.oil },
  { key: "genmix_live.tie_line_total", label: "Tie-Line", color: COLORS.tieline },
  { key: "generation_mix.hydro", label: "Hydro", color: COLORS.hydro },
  { key: "genmix_live.bess_discharge", label: "BESS", color: COLORS.bessDischarge },
  { key: "generation_mix.solar", label: "Transmission Solar", color: COLORS.gridSolar },
  { key: "genmix_live.distribution_solar", label: "Distribution Solar", color: COLORS.dnSolar },
  { key: "genmix_live.other_re", label: "Other RE", color: COLORS.otherRe },
];
export const GRID_DEMAND = { key: "genmix_live.total_generation", label: "Grid Demand", color: COLORS.gridDemand };
export const SYSTEM_DEMAND = { key: "system_demand.demand", label: "System Demand", color: COLORS.demand };

/** Draws the profile into el. Sources with no reading in the range are left out, and a moment where any
 * remaining source has no reading is a gap. Returns the raw payloads (for CSV), or null when there is nothing to draw. */
export async function drawProfile(el, meta, start, end, { isCurrent = () => true } = {}) {
  const have = new Set(meta.series.map((s) => s.key));
  const stack = PROFILE_STACK.filter((s) => have.has(s.key));
  const lines = [GRID_DEMAND, SYSTEM_DEMAND].filter((s) => have.has(s.key));
  if (!stack.length) return null;
  const payloads = await Promise.all([...stack, ...lines].map((s) => getPoints(s.key, start, end)));
  if (!isCurrent()) return null;
  const stackPts = payloads.slice(0, stack.length);
  const used = stack.map((s, i) => [s, stackPts[i]]).filter(([, p]) => p.points.some((x) => x[1] != null));
  if (!used.length) return null;
  const aligned = alignStack(used.map(([, p]) => p.points));
  const series = used.map(([s], i) => ({ name: s.label, points: aligned[i], color: s.color, area: true, areaOpacity: 0.9, stack: "supply", width: 0.6 }));
  lines.forEach((s, i) => {
    const p = payloads[stack.length + i];
    if (p.points.some((x) => x[1] != null)) {
      series.push({ name: s.label, points: p.points, color: s.color, width: s === GRID_DEMAND ? 1.6 : 1.8, dashed: s === SYSTEM_DEMAND });
    }
  });
  // GSO's legend reads top to bottom the way the chart stacks: the top layer first, then the two lines
  const order = series.filter((s) => s.stack).map((s) => s.name).reverse().concat(series.filter((s) => !s.stack).map((s) => s.name));
  timeChart(el, { series, demo: meta.is_demo, legendOrder: order });
  return payloads.filter((p) => p.points.some((x) => x[1] != null));
}
