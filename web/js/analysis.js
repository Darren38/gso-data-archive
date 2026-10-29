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

/** Put several series on shared time slots (GSO publishes every 10 minutes) so they can be stacked.
 * A stacking chart counts a missing lower value as zero and draws everything above it too low, so a slot
 * where any series has no reading becomes a gap for all of them. Returns aligned point lists in input order. */
export function alignStack(list, slotMs = 600e3) {
  const maps = list.map((points) => {
    const m = new Map();
    for (const [t, v] of points) if (v != null) m.set(Math.round(Date.parse(t) / slotMs) * slotMs, v);
    return m;
  });
  const slots = [...new Set(maps.flatMap((m) => [...m.keys()]))].sort((a, b) => a - b);
  const complete = slots.map((k) => maps.every((m) => m.has(k)));
  return maps.map((m) => slots.map((k, i) => [new Date(k).toISOString(), complete[i] ? m.get(k) : null, complete[i] ? "ok" : "gap"]));
}

/** Per-MYT-day statistics from raw points, the same way the archive's daily files are made (gso_archive/analytics.py
 * `daily`): energy only between readings at most 1.5 intervals apart, and today expects only the readings so far. */
export function dailyFromPoints(points, intervalS, startDay, endDay, unit = "MW") {
  const MYT = 8 * 3600e3, interval = intervalS || 600;
  const byDay = new Map();
  for (const [t, v] of points) {
    if (v == null) continue;
    const day = new Date(Date.parse(t) + MYT).toISOString().slice(0, 10);
    if (!byDay.has(day)) byDay.set(day, []);
    byDay.get(day).push([Date.parse(t), v, t]);
  }
  // Energy per day across all readings, splitting a slice that crosses midnight so no day loses its last slice.
  const all = points.filter((p) => p[1] != null).map(([t, v]) => [Date.parse(t), v]).sort((a, b) => a[0] - b[0]);
  const energyByDay = new Map();
  const dayOf = (ms) => new Date(ms + MYT).toISOString().slice(0, 10);
  const add = (day, mwh) => energyByDay.set(day, (energyByDay.get(day) || 0) + mwh);
  for (let i = 1; i < all.length; i += 1) {
    const [t0, v0] = all[i - 1], [t1, v1] = all[i], dt = (t1 - t0) / 1000;
    if (dt <= 0 || dt > 1.5 * interval) continue;
    const d0 = dayOf(t0), d1 = dayOf(t1), midnight = Date.parse(`${d1}T00:00:00+08:00`);
    if (d0 === d1 || t1 === midnight) { add(d0, ((v0 + v1) / 2) * dt / 3600); continue; }
    const a = (midnight - t0) / 1000, vm = v0 + ((v1 - v0) * a) / dt;
    add(d0, ((v0 + vm) / 2) * a / 3600); add(d1, ((vm + v1) / 2) * (dt - a) / 3600);
  }
  const now = Date.now(), today = new Date(now + MYT).toISOString().slice(0, 10);
  const full = Math.max(1, Math.round(86400 / interval));
  const rows = [];
  for (let d = new Date(`${startDay}T00:00:00Z`); d.toISOString().slice(0, 10) <= endDay; d.setUTCDate(d.getUTCDate() + 1)) {
    const day = d.toISOString().slice(0, 10);
    const expected = day === today ? Math.max(1, Math.floor((now - Date.parse(`${day}T00:00:00+08:00`)) / 1000 / interval)) : full;
    const pts = (byDay.get(day) || []).sort((a, b) => a[0] - b[0]);
    if (!pts.length) { rows.push({ date: day, count: 0, expected, completeness: 0, max: null, max_time: null, min: null, min_time: null, mean: null, energy_mwh: null }); continue; }
    let peak = pts[0], low = pts[0], sum = 0;
    pts.forEach((p) => {
      if (p[1] > peak[1]) peak = p;
      if (p[1] < low[1]) low = p;
      sum += p[1];
    });
    const energy = energyByDay.get(day) || 0;
    rows.push({ date: day, count: pts.length, expected, completeness: Math.min(1, pts.length / expected), max: peak[1], max_time: peak[2],
      min: low[1], min_time: low[2], mean: sum / pts.length, energy_mwh: unit === "MW" ? energy : null });
  }
  return { rows };
}
