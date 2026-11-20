// Data access layer. Same interface in "api" mode (live read-only API) and
// "static" mode (pre-exported JSON on GitHub Pages).
import { forget, openBytes, storedKey } from "./lock.js";

const CFG = window.GSO_CONFIG || { mode: "api", apiBase: "", dataBase: "data" };
export const MODE = CFG.mode;
const cache = new Map();

async function getJSON(url) {
  if (cache.has(url)) return cache.get(url);
  const p = fetch(url, { headers: { Accept: "application/json" } }).then(async (r) => {
    if (r.status === 404 && MODE === "static") return null; // month file not exported → no data
    if (!r.ok) {
      let detail = "";
      try { detail = (await r.json()).detail || ""; } catch { /* not JSON */ }
      throw new Error(`HTTP ${r.status}${detail ? ` — ${detail}` : ""}`);
    }
    return r.json();
  });
  cache.set(url, p);
  p.catch(() => cache.delete(url));
  return p;
}

export function clearCache() { cache.clear(); }

// History files that are published trimmed to the newest days and in full locked (NAME.json.enc) when the owner has
// set a passphrase (gso_archive/export_static.py). With the key from lock.js the full copy is read instead.
const LOCKABLE = /^(points\/[^/]+\/\d{4}-\d{2}|daily\/[^/]+|farms\/[^/]+|tables\/[^/]+)\.json$/;

async function getData(path) {
  const raw = MODE === "static" && LOCKABLE.test(path) ? storedKey() : null;
  if (!raw) return getJSON(stat(path));
  const url = stat(`${path}.enc`);
  if (cache.has(url)) return cache.get(url);
  const p = (async () => {
    const r = await fetch(url);
    if (r.status === 404) return getJSON(stat(path)); // not locked (or not published): the plain file
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    try {
      return JSON.parse(new TextDecoder().decode(await openBytes(raw, await r.arrayBuffer())));
    } catch {
      forget(); // the passphrase was changed: back to the public files
      return getJSON(stat(path));
    }
  })();
  cache.set(url, p);
  p.catch(() => cache.delete(url));
  return p;
}

/** The history lock as the site publishes it ({public_days, public_from, history_from, ...} and whether this browser
 * holds the key), or null when the whole history is public. */
export async function historyLock() {
  if (MODE !== "static") return null;
  const lock = (await getMeta().catch(() => null))?.lock;
  return lock ? { ...lock, unlocked: !!storedKey() } : null;
}

const api = (path) => `${CFG.apiBase || ""}/api/v1${path}`;
const stat = (path) => `${CFG.dataBase || "data"}/${path}`;

export async function getMeta() {
  return MODE === "static" ? getJSON(stat("meta.json")) : getJSON(api("/meta"));
}

export async function getStatus() {
  return MODE === "static" ? getJSON(stat("status.json")) : getJSON(api("/status"));
}

function monthsBetween(start, end) {
  // Month tags in MYT covering [start, end).
  const toMyt = (d) => new Date(d.getTime() + 8 * 3600e3);
  const a = toMyt(start), b = toMyt(new Date(end.getTime() - 1));
  const out = [];
  let y = a.getUTCFullYear(), m = a.getUTCMonth();
  while (y < b.getUTCFullYear() || (y === b.getUTCFullYear() && m <= b.getUTCMonth())) {
    out.push(`${y}-${String(m + 1).padStart(2, "0")}`);
    m += 1; if (m === 12) { m = 0; y += 1; }
  }
  return out;
}

/** Points for one series in [start, end). Returns {points: [[isoUTC, value|null, quality]], unit, ...}. */
/** A figure GSO published from a stalled feed (quality "frozen", gso_archive/quality.py) is kept in the archive but
 * never drawn or counted: it becomes "no reading", and the tooltip says why. */
const unfreeze = (res) => (res && res.points ? { ...res, points: res.points.map((p) => (String(p[2] || "").includes("frozen") ? [p[0], null, "frozen"] : p)) } : res);

export async function getPoints(key, start, end) {
  return unfreeze(await fetchPoints(key, start, end));
}

async function fetchPoints(key, start, end) {
  if (MODE !== "static") {
    const q = new URLSearchParams({ start: start.toISOString(), end: end.toISOString() });
    return getJSON(api(`/series/${encodeURIComponent(key)}/points?${q}`));
  }
  // Only the months this series has readings in: asking for earlier or later months just fetches missing files.
  const info = (await getMeta().catch(() => null))?.series?.find((x) => x.key === key);
  // Recent ranges (the Overview's 24 hours, "today") come from one small file of the newest 3 days, not whole months.
  if (info?.last && start.getTime() >= Date.parse(info.last) + 1000 - RECENT_DAYS * 864e5) {
    const recent = await getJSON(stat(`points/${key}/recent.json`)).catch(() => null);
    if (recent?.points) {
      const points = recent.points.filter((p) => { const t = Date.parse(p[0]); return t >= start.getTime() && t < end.getTime(); });
      return { series: key, unit: recent.unit, interval_s: recent.interval_s, kind: recent.kind, points, is_demo: !!recent.is_demo };
    }
  }
  const from = info?.first ? new Date(Math.max(start.getTime(), Date.parse(info.first))) : start;
  const to = info?.last ? new Date(Math.min(end.getTime(), Date.parse(info.last) + 1)) : end;
  const months = from < to ? monthsBetween(from, to) : [];
  const parts = await Promise.all(months.map((m) => getData(`points/${key}/${m}.json`)));
  const found = parts.filter(Boolean);
  const points = [];
  for (const part of found) {
    for (const p of part.points) {
      const t = Date.parse(p[0]);
      if (t >= start.getTime() && t < end.getTime()) points.push(p);
    }
  }
  const base = found[0] || { unit: "MW", interval_s: null, kind: "actual" };
  return { series: key, unit: base.unit, interval_s: base.interval_s, kind: base.kind, points, is_demo: !!base.is_demo };
}

/** Daily statistics rows for [startDay, endDay] (YYYY-MM-DD, MYT). */
export async function getDaily(key, startDay, endDay) {
  if (MODE !== "static") {
    const q = new URLSearchParams({ start: startDay, end: endDay });
    return getJSON(api(`/series/${encodeURIComponent(key)}/daily?${q}`));
  }
  const all = await getData(`daily/${key}.json`);
  if (!all) return { series: key, unit: "MW", rows: [] };
  const rows = all.rows.filter((r) => r.date >= startDay && r.date <= endDay);
  return { ...all, rows };
}

/** A list GSO publishes as rows (e.g. its power stations), with the changes the archive has seen. */
const RECENT_DAYS = 3; // gso_archive/export_static.py RECENT_DAYS

/** MYT days with LSS solar farm readings, newest first. */
export async function getFarmDays() {
  const res = MODE === "static" ? await getData("farms/index.json") : await getJSON(api("/farms"));
  return res?.days || [];
}

/** Every LSS farm's output at every collected moment of one MYT day ({date, times, farms: [{code, mw: [...], cap, ...}]}). */
export async function getFarmsDay(day) {
  return MODE === "static" ? getData(`farms/${day}.json`) : getJSON(api(`/farms/${day}`));
}

export async function getTable(key) {
  return MODE === "static" ? getData(`tables/${key}.json`) : getJSON(api(`/tables/${encodeURIComponent(key)}`));
}

export async function getRevisions(key, start, end) {
  if (MODE === "static") return { series: key, revisions: null };
  const q = new URLSearchParams({ start: start.toISOString(), end: end.toISOString() });
  return getJSON(api(`/series/${encodeURIComponent(key)}/revisions?${q}`));
}

/** Server-side export URL (API mode only). */
export function exportUrl(keys, startDay, endDay, format) {
  if (MODE === "static") return null;
  const q = new URLSearchParams({ series: keys.join(","), start: startDay, end: endDay, format });
  return api(`/export?${q}`);
}

/** Roll daily rows up to week/month/year (mirrors gso_archive.analytics.rollup). */
export function rollup(rows, period) {
  if (period === "day") return rows.map((r) => ({ ...r, period: r.date, days: 1, days_with_data: r.count ? 1 : 0, mean_daily_peak: r.max }));
  const buckets = new Map();
  for (const r of rows) {
    const d = new Date(`${r.date}T00:00:00Z`);
    let key;
    if (period === "week") {
      const t = new Date(d); const day = (t.getUTCDay() + 6) % 7; t.setUTCDate(t.getUTCDate() - day + 3);
      const firstThu = new Date(Date.UTC(t.getUTCFullYear(), 0, 4));
      const week = 1 + Math.round(((t - firstThu) / 864e5 - 3 + ((firstThu.getUTCDay() + 6) % 7)) / 7);
      key = `${t.getUTCFullYear()}-W${String(week).padStart(2, "0")}`;
    } else if (period === "month") key = r.date.slice(0, 7);
    else key = r.date.slice(0, 4);
    if (!buckets.has(key)) buckets.set(key, []);
    buckets.get(key).push(r);
  }
  return [...buckets.entries()].sort(([a], [b]) => (a < b ? -1 : 1)).map(([key, g]) => {
    const withData = g.filter((x) => x.count);
    const peak = withData.reduce((best, x) => (best && best.max >= x.max ? best : x), null);
    const energies = withData.map((x) => x.energy_mwh).filter((x) => x != null);
    return {
      period: key, days: g.length, days_with_data: withData.length,
      completeness: g.reduce((s, x) => s + x.completeness, 0) / g.length,
      max: peak ? peak.max : null, max_time: peak ? peak.max_time : null,
      mean_daily_peak: withData.length ? withData.reduce((s, x) => s + x.max, 0) / withData.length : null,
      energy_mwh: energies.length ? energies.reduce((s, x) => s + x, 0) : null,
    };
  });
}
