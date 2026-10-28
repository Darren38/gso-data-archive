// Client-side derived metrics. Everything here is DERIVED from archived readings
// and is labelled as such in the UI.

/** Map iso → value (non-null only). */
export function toMap(points) {
  const m = new Map();
  for (const [t, v] of points) if (v != null) m.set(t, v);
  return m;
}

/** Combine two aligned series with fn(a, b); timestamps missing in either become gaps. */
export function combine(aPoints, bPoints, fn) {
  const b = toMap(bPoints);
  return aPoints.map(([t, v]) => {
    const w = b.get(t);
    return [t, v == null || w == null ? null : fn(v, w), "derived"];
  });
}

/** Sum several series at shared timestamps; a timestamp is kept only if every series has it. */
export function sumSeries(list) {
  if (!list.length) return [];
  const maps = list.map(toMap);
  return list[0].map(([t]) => {
    let total = 0;
    for (const m of maps) {
      const v = m.get(t);
      if (v == null) return [t, null, "gap"];
      total += v;
    }
    return [t, total, "derived"];
  });
}

/** Ramp rate in MW/min between consecutive readings; gaps break the ramp. */
export function ramps(points, intervalS) {
  const out = [];
  const limit = 1.5 * (intervalS || 1800) * 1000;
  for (let i = 1; i < points.length; i += 1) {
    const [t0, v0] = points[i - 1], [t1, v1] = points[i];
    const dt = Date.parse(t1) - Date.parse(t0);
    if (v0 == null || v1 == null || dt <= 0 || dt > limit) { out.push([t1, null, "gap"]); continue; }
    out.push([t1, (v1 - v0) / (dt / 60000), "derived"]);
  }
  return out;
}

/** Mean intraday profile (minutes since MYT midnight → mean value), grouped by key(isoDayMYT). */
export function intradayProfiles(points, groupKey) {
  const groups = new Map();
  for (const [t, v] of points) {
    if (v == null) continue;
    const local = new Date(Date.parse(t) + 8 * 3600e3);
    const minute = local.getUTCHours() * 60 + local.getUTCMinutes();
    const key = groupKey(local.toISOString().slice(0, 10));
    if (!groups.has(key)) groups.set(key, new Map());
    const g = groups.get(key);
    const cell = g.get(minute) || [0, 0];
    cell[0] += v; cell[1] += 1; g.set(minute, cell);
  }
  return [...groups.entries()].sort(([a], [b]) => (a < b ? -1 : 1)).map(([key, g]) => ({
    key, data: [...g.entries()].sort((a, b) => a[0] - b[0]).map(([m, [s, n]]) => [m, s / n]),
  }));
}

/** Forecast-vs-actual error stats at matching timestamps. */
export function forecastError(actual, forecast) {
  const f = toMap(forecast);
  let n = 0, abs = 0, bias = 0, sq = 0;
  for (const [t, v] of actual) {
    const w = f.get(t);
    if (v == null || w == null) continue;
    const e = w - v; n += 1; abs += Math.abs(e); bias += e; sq += e * e;
  }
  return n ? { n, mae: abs / n, bias: bias / n, rmse: Math.sqrt(sq / n) } : null;
}

export function extent(points) {
  let max = null, min = null;
  for (const p of points) {
    if (p[1] == null) continue;
    if (!max || p[1] > max[1]) max = p;
    if (!min || p[1] < min[1]) min = p;
  }
  return { max, min };
}

export function latest(points) {
  for (let i = points.length - 1; i >= 0; i -= 1) if (points[i][1] != null) return points[i];
  return null;
}
