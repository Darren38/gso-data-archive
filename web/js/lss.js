// LSS solar farms from GSO's solar map as the archive collected it (one file per day: data/farms/<day>.json,
// gso_archive/analytics.py farms_day). Four views, the same filters for all, and a CSV of what is shown:
//   moment  every farm at one moment (output, % of capacity), on the map and in a table
//   period  each farm's capacity factor over a period
//   daily   the selected farms' energy and capacity factor day by day
//   day     the selected farms' output through one day
// Every setting lives in the address (CLAUDE.md lesson 7) and is checked before use (lessons 8, 23).
import { getFarmDays, getFarmsDay } from "./data.js";
import { COLORS, categoryChart, solarMap, timeChart } from "./charts.js";
import { capacityFactor, implausibleSolar, nearestMoment } from "./analysis.js";
import { downloadText, emptyState, errorState, esc, fmtDate, fmtDateTime, fmtEnergy, fmtNum, getParam, renderTable, setParams } from "./ui.js";

const REGIONS = ["North", "Central", "South", "East"];
const CONNS = { grid: "Grid (transmission)", distribution: "Distribution" };
const MODES = { moment: "At a moment", period: "Capacity factor over a period", daily: "Day by day", day: "Through a day" };
const MAX_DAYS = 92;
const MYT = 8 * 3600e3;
const isDay = (v) => /^\d{4}-\d{2}-\d{2}$/.test(v || "");
const isTime = (v) => /^([01]\d|2[0-3]):[0-5]\d$/.test(v || "");
const addDay = (d, n) => new Date(Date.parse(`${d}T12:00:00+08:00`) + n * 864e5).toISOString().slice(0, 10);
const dayOf = (ms) => new Date(ms + MYT).toISOString().slice(0, 10);
const minuteOf = (ms) => { const d = new Date(ms + MYT); return d.getUTCHours() * 60 + d.getUTCMinutes(); };
const mytIso = (ms) => new Date(ms + MYT).toISOString().replace(".000Z", "+08:00");
const pct = (v, d = 0) => (v == null ? "—" : `${fmtNum(v, d)}%`);

/** CSV text: a header row, then rows; text with commas or quotes is quoted. Missing values stay empty, never 0. */
function csv(header, rows) {
  const cell = (v) => (v == null ? "" : /[",\n]/.test(String(v)) ? `"${String(v).replace(/"/g, '""')}"` : String(v));
  return [header, ...rows].map((r) => r.map(cell).join(",")).join("\n") + "\n";
}
const SOURCE_NOTE = "# Source: GSO solar map (gso.org.my) as collected by GSO Grid Archive. Times in MYT (UTC+8). Empty = no reading.";

/** Capacity factor over the readings inside the chosen hours: only slices whose both ends fall inside the window and
 * are at most 30 minutes apart count (time without readings is left out, never guessed). */
function cfInWindow(points, cap, win) {
  if (win.all) return capacityFactor(points, cap);
  const inside = (ms) => { const m = minuteOf(ms); return m >= win.from && m <= win.to; };
  let energy = 0, ms = 0;
  for (let i = 1; i < points.length; i += 1) {
    const [t0, a] = points[i - 1], [t1, b] = points[i];
    const dt = t1 - t0;
    if (a == null || b == null || dt <= 0 || dt > 30 * 60e3 || !inside(t0) || !inside(t1)) continue;
    energy += ((a + b) / 2) * (dt / 3600e3); ms += dt;
  }
  return cap > 0 && ms > 0 ? { cf: energy / (cap * (ms / 3600e3)), energyMwh: energy, hours: ms / 3600e3 } : null;
}

/** Draws the explorer into `el` (a card body). Resolves once the first view is drawn (lesson 7). */
export async function lssExplorer(el, { demo = false } = {}) {
  const days = await getFarmDays().catch(() => []);
  if (!days.length) {
    el.innerHTML = emptyState("No solar farm readings archived yet", "They are kept from GSO's solar map at every collection.", "◌");
    return;
  }
  const newest = days[0], oldest = days[days.length - 1];
  const newestFile = await getFarmsDay(newest).catch(() => null);
  const codes = [...new Set((newestFile?.farms || []).map((f) => f.code))].sort();
  const clampDay = (d, fallback) => (isDay(d) && d >= oldest && d <= newest ? d : fallback);
  const hours = String(getParam("lssh") || "").match(/^(\d{1,2})-(\d{1,2})$/);
  const state = {
    mode: MODES[getParam("lss")] ? getParam("lss") : "moment",
    day: clampDay(getParam("lssday"), newest),
    time: isTime(getParam("lsstime")) ? getParam("lsstime") : "12:00",
    from: clampDay(getParam("lssfrom"), days[Math.min(6, days.length - 1)]),
    to: clampDay(getParam("lssto"), newest),
    region: REGIONS.includes(getParam("lssreg")) ? getParam("lssreg") : "",
    conn: CONNS[getParam("lssconn")] ? getParam("lssconn") : "",
    farm: codes.includes(getParam("lssfarm")) ? getParam("lssfarm") : "",
    h0: hours && +hours[1] < +hours[2] && +hours[2] <= 24 ? +hours[1] : 0,
    h1: hours && +hours[1] < +hours[2] && +hours[2] <= 24 ? +hours[2] : 24,
    bad: getParam("lssbad") === "1",
  };
  const hourOpts = (sel, max) => Array.from({ length: 25 }, (_, h) => h).filter((h) => (max ? h > 0 : h < 24))
    .map((h) => `<option value="${h}"${h === sel ? " selected" : ""}>${String(h).padStart(2, "0")}:00</option>`).join("");
  el.innerHTML = `
    <div class="toolbar" role="group" aria-label="LSS farms view">
      <div class="seg">${Object.entries(MODES).map(([k, v]) => `<button type="button" data-mode="${k}">${v}</button>`).join("")}</div>
    </div>
    <div class="toolbar lss-when" role="group" aria-label="When">
      <span data-show="moment day"><label class="inline">Date <input type="date" name="day" min="${oldest}" max="${newest}"></label></span>
      <span data-show="moment"><label class="inline">Time <input type="time" name="time" step="600"></label>
        <button type="button" class="btn" data-step="-1" title="Previous reading" aria-label="Previous reading">◀</button>
        <button type="button" class="btn" data-step="1" title="Next reading" aria-label="Next reading">▶</button>
        <button type="button" class="btn" data-newest>Newest</button></span>
      <span data-show="period daily"><label class="inline">From <input type="date" name="from" min="${oldest}" max="${newest}"></label>
        <label class="inline">To <input type="date" name="to" min="${oldest}" max="${newest}"></label>
        <span class="seg">${[["7", "7 days"], ["30", "30 days"], ["month", "This month"], ["all", "All"]].map(([k, v]) => `<button type="button" data-quick="${k}">${v}</button>`).join("")}</span></span>
    </div>
    <div class="toolbar lss-filter" role="group" aria-label="Which farms">
      <label class="inline">Region <select name="region"><option value="">All regions</option>${REGIONS.map((r) => `<option${r === state.region ? " selected" : ""}>${r}</option>`).join("")}</select></label>
      <label class="inline">Connected to <select name="conn"><option value="">Grid and distribution</option>${Object.entries(CONNS).map(([k, v]) => `<option value="${k}"${k === state.conn ? " selected" : ""}>${v}</option>`).join("")}</select></label>
      <label class="inline">Farm <select name="farm"><option value="">All farms</option>${codes.map((c) => `<option${c === state.farm ? " selected" : ""}>${esc(c)}</option>`).join("")}</select></label>
      <span data-show="period daily"><label class="inline">Hours <select name="h0">${hourOpts(state.h0)}</select></label>
        <label class="inline">to <select name="h1">${hourOpts(state.h1, true)}</select></label></span>
      <label class="inline"><input type="checkbox" name="bad"${state.bad ? " checked" : ""}> Include farms marked "GSO figures look wrong"</label>
    </div>
    <p class="small muted lss-span">MYT · archived from ${esc(fmtDate(oldest))} to ${esc(fmtDate(newest))}</p>
    <div class="lss-out"></div>`;
  const out = el.querySelector(".lss-out");
  const input = (n) => el.querySelector(`[name="${n}"]`);
  const sync = () => { input("day").value = state.day; input("time").value = state.time; input("from").value = state.from; input("to").value = state.to; };
  sync();

  async function draw() {
    el.querySelectorAll("[data-mode]").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.mode === state.mode)));
    el.querySelectorAll("[data-show]").forEach((s) => { s.hidden = !s.dataset.show.split(" ").includes(state.mode); });
    setParams({ lss: state.mode === "moment" ? null : state.mode, lssday: state.day, lsstime: state.time, lssfrom: state.from, lssto: state.to,
      lssreg: state.region || null, lssconn: state.conn || null, lssfarm: state.farm || null,
      lssh: state.h0 === 0 && state.h1 === 24 ? null : `${state.h0}-${state.h1}`, lssbad: state.bad ? "1" : null });
    try {
      await VIEWS[state.mode](out, state, { demo, days, oldest, newest, jump });
    } catch (err) { out.innerHTML = errorState(err); }
  }
  // Moves the moment view to another reading (◀ ▶, also across days) and redraws.
  function jump(day, time) { state.day = day; state.time = time; sync(); draw(); }
  el.querySelectorAll("[data-mode]").forEach((b) => b.addEventListener("click", () => { state.mode = b.dataset.mode; draw(); }));
  for (const n of ["day", "time", "from", "to"]) {
    input(n).addEventListener("change", () => {
      const v = input(n).value;
      if (n === "time" ? isTime(v) : isDay(v) && v >= oldest && v <= newest) { state[n] = v; draw(); }
    });
  }
  for (const n of ["region", "conn", "farm"]) input(n).addEventListener("change", () => { state[n] = input(n).value; draw(); });
  for (const n of ["h0", "h1"]) {
    input(n).addEventListener("change", () => {
      const a = +input("h0").value, b = +input("h1").value;
      if (a < b) { state.h0 = a; state.h1 = b; draw(); } else { input("h0").value = state.h0; input("h1").value = state.h1; }
    });
  }
  input("bad").addEventListener("change", () => { state.bad = input("bad").checked; draw(); });
  el.querySelectorAll("[data-quick]").forEach((b) => b.addEventListener("click", () => {
    const k = b.dataset.quick;
    state.to = newest;
    state.from = k === "all" ? (addDay(newest, -(MAX_DAYS - 1)) > oldest ? addDay(newest, -(MAX_DAYS - 1)) : oldest)
      : k === "month" ? (`${newest.slice(0, 8)}01` > oldest ? `${newest.slice(0, 8)}01` : oldest)
      : (addDay(newest, -(+k - 1)) > oldest ? addDay(newest, -(+k - 1)) : oldest);
    sync(); draw();
  }));
  el.querySelectorAll("[data-step]").forEach((b) => b.addEventListener("click", () => stepMoment(state, +b.dataset.step, days, jump)));
  el.querySelector("[data-newest]").addEventListener("click", async () => {
    const f = await getFarmsDay(newest).catch(() => null);
    const t = f?.times?.length ? f.times[f.times.length - 1] : null;
    if (t) jump(newest, new Date(Date.parse(t) + MYT).toISOString().slice(11, 16));
  });
  await draw();
}

/** The previous or next reading from the chosen moment, looking into the days before or after when needed. */
async function stepMoment(state, dir, days, jump) {
  const want = Date.parse(`${state.day}T${state.time}:00+08:00`);
  let day = state.day;
  for (let tries = 0; tries < 10 && day; tries += 1) {
    const f = await getFarmsDay(day).catch(() => null);
    const times = (f?.times || []).map((t) => Date.parse(t));
    const next = dir > 0 ? times.find((t) => t > want + 60e3) : [...times].reverse().find((t) => t < want - 60e3);
    if (next != null) { jump(dayOf(next), new Date(next + MYT).toISOString().slice(11, 16)); return; }
    const i = days.indexOf(day); // newest first
    day = dir > 0 ? days[i - 1] : days[i + 1];
  }
}

/** The farms the filters select, each with its readings as [ms, MW] and whether GSO's figures look wrong. */
function select(file, state) {
  const times = file.times.map((t) => Date.parse(t));
  return file.farms
    .filter((f) => (!state.region || f.region === state.region) && (!state.conn || f.conn === state.conn) && (!state.farm || f.code === state.farm))
    .map((f) => ({ ...f, pts: f.mw.map((v, j) => [times[j], v]) }))
    .map((f) => ({ ...f, bad: implausibleSolar(f.pts, f.cap) }));
}
const counted = (rows, state) => rows.filter((r) => state.bad || !r.bad);
const describe = (state, hours = false) => [state.farm || (state.region ? `${state.region} region` : "All regions"),
  !state.farm && state.conn ? CONNS[state.conn].toLowerCase() : "", !hours || (state.h0 === 0 && state.h1 === 24) ? "" : `${String(state.h0).padStart(2, "0")}:00-${String(state.h1).padStart(2, "0")}:00`]
  .filter(Boolean).join(", ");
const slug = (state) => [state.farm || state.region || "all", state.conn].filter(Boolean).join("_").toLowerCase();
const window_ = (state) => ({ all: state.h0 === 0 && state.h1 === 24, from: state.h0 * 60, to: state.h1 * 60 });

const FLAG = '<span class="pill warn" title="GSO\'s solar map shows this farm at half its capacity or more when the sun is down or barely up (before 07:30 or after 18:45): its figures can\'t be real solar output">GSO figures look wrong</span>';
function flagNote(rows, state) {
  const n = rows.filter((r) => r.bad).length;
  if (!n) return "";
  return `<p class="small muted">${n} farm${n > 1 ? "s" : ""} marked "GSO figures look wrong" (output at half capacity or more with the sun down or barely up)
    ${state.bad ? `${n > 1 ? "are" : "is"} included, as you chose.` : `${n > 1 ? "are" : "is"} listed as GSO published ${n > 1 ? "them" : "it"} but left out of the map and the totals. Tick "Include farms marked…" to count ${n > 1 ? "them" : "it"}.`}</p>`;
}
function regionRow(rows, value) {
  const parts = REGIONS.map((name) => { const rs = rows.filter((r) => r.region === name); return rs.length ? `<span>${name} <b>${value(rs)}</b></span>` : ""; });
  return `<div class="stat-row region-row">${parts.filter(Boolean).length > 1 ? parts.join("") : ""}<span>All selected <b>${value(rows)}</b> <small class="muted">${rows.length} farm${rows.length === 1 ? "" : "s"}</small></span></div>`;
}
function csvButtons(out, items) {
  const bar = document.createElement("div");
  bar.className = "toolbar lss-dl";
  bar.innerHTML = `<span class="small muted">Download:</span>${items.map((it, i) => `<button type="button" class="btn" data-dl="${i}" title="${esc(it.title || "")}">${esc(it.label)}</button>`).join("")}`;
  bar.querySelectorAll("[data-dl]").forEach((b) => b.addEventListener("click", () => { const it = items[+b.dataset.dl]; downloadText(it.file, it.text()); }));
  out.appendChild(bar);
}
const farmCols = [
  { key: "code", label: "Farm", fmt: (v, r) => `<a class="mono" href="#/explorer?series=${encodeURIComponent(r.key)}">${esc(v)}</a>${r.bad ? ` ${FLAG}` : ""}` },
  { key: "state", label: "State" }, { key: "region", label: "Region" }, { key: "conn", label: "Connected to", fmt: (v) => esc(CONNS[v] || v || "—") },
];

async function loadPeriod(state) {
  let { from, to } = state;
  if (from > to) [from, to] = [to, from];
  const list = [];
  for (let d = from; d <= to && list.length < MAX_DAYS; d = addDay(d, 1)) list.push(d);
  const files = (await Promise.all(list.map((d) => getFarmsDay(d).catch(() => null)))).filter((f) => f?.times?.length);
  const cut = list.length < Math.round((Date.parse(to) - Date.parse(from)) / 864e5) + 1;
  return { from, to: list[list.length - 1], list, files, cut };
}

/** Readings of the same farm across several day files, joined in time order. */
function joinFarms(files, state) {
  const byKey = new Map();
  for (const f of files) {
    for (const farm of select(f, state)) {
      const e = byKey.get(farm.key) || { ...farm, pts: [] };
      if (farm.cap) e.cap = farm.cap;
      e.pts.push(...farm.pts);
      byKey.set(farm.key, e);
    }
  }
  return [...byKey.values()].map((f) => { f.pts.sort((a, b) => a[0] - b[0]); return { ...f, bad: implausibleSolar(f.pts, f.cap) }; });
}

/** The selected farms' summed output at each moment, when at least 90% of them have a reading then (else no reading). */
function fleetSeries(farms) {
  const byT = new Map();
  for (const f of farms) for (const [t, v] of f.pts) { const e = byT.get(t) || { n: 0, mw: 0 }; if (v != null) { e.n += 1; e.mw += v; } byT.set(t, e); }
  const cap = farms.reduce((s, f) => s + (f.cap || 0), 0);
  return { cap, pts: [...byT.entries()].sort((a, b) => a[0] - b[0]).map(([t, e]) => [t, farms.length && e.n >= 0.9 * farms.length ? e.mw : null]) };
}

const VIEWS = {
  async moment(out, state, { demo }) {
    out.innerHTML = '<div class="skeleton" style="height:420px"></div>';
    const data = await getFarmsDay(state.day);
    if (!data?.times?.length) { out.innerHTML = emptyState("No solar map readings on this day"); return; }
    const want = Date.parse(`${state.day}T${state.time}:00+08:00`);
    const i = nearestMoment(data.times, want);
    if (i < 0) {
      const near = data.times.map((t) => Math.abs(Date.parse(t) - want)).reduce((a, b) => Math.min(a, b), Infinity);
      out.innerHTML = emptyState("No solar map reading near that time",
        `The nearest one this day is ${fmtNum(near / 60e3)} minutes away. Use ◀ ▶ to step to the readings there are.`, "◌");
      return;
    }
    const rows = select(data, state).map((f) => ({ ...f, mwNow: f.mw[i], pct: f.cap && f.mw[i] != null ? (100 * f.mw[i]) / f.cap : null }))
      .filter((f) => f.mwNow != null).sort((a, b) => (a.bad - b.bad) || (b.pct ?? -1) - (a.pct ?? -1));
    const use = counted(rows, state);
    const pctOf = (rs) => {
      const cap = rs.reduce((t, r) => t + (r.cap || 0), 0), mw = rs.reduce((t, r) => t + (r.mwNow || 0), 0);
      return cap ? `${fmtNum((100 * mw) / cap, 0)}% <small class="muted">${fmtNum(mw)} of ${fmtNum(cap)} MW</small>` : "—";
    };
    const when = data.times[i];
    out.innerHTML = `<p class="small"><b>${esc(fmtDateTime(when))} MYT</b> (${esc(describe(state))}): the reading of GSO's solar map nearest to your time.
      Each farm's output as a share of its capacity.</p>${rows.length ? regionRow(use, pctOf) : ""}<div class="chart map"></div><div class="tbl"></div>${flagNote(rows, state)}`;
    if (!rows.length) { out.querySelector(".chart").outerHTML = emptyState("No farm matches these choices at this moment"); return; }
    await solarMap(out.querySelector(".chart"), { farms: use.map((r) => ({ ...r, mw: r.mwNow })), demo });
    renderTable(out.querySelector(".tbl"), [...farmCols,
      { key: "mwNow", label: "Output (MW)", num: true, fmt: (v) => fmtNum(v, 1) },
      { key: "cap", label: "Capacity (MW)", num: true, fmt: (v) => fmtNum(v) },
      { key: "pct", label: "Of capacity", num: true, fmt: (v) => pct(v) }], rows, 15);
    const stamp = mytIso(Date.parse(when)).slice(0, 16).replace(":", "");
    csvButtons(out, [{ label: "This moment (CSV)", file: `lss_moment_${stamp}_${slug(state)}.csv`,
      text: () => SOURCE_NOTE + "\n" + csv(["time_myt", "farm", "state", "region", "connection", "output_mw", "capacity_mw", "percent_of_capacity", "gso_figures_look_wrong"],
        rows.map((r) => [mytIso(Date.parse(when)), r.code, r.state, r.region, r.conn, r.mwNow, r.cap, r.pct == null ? null : +r.pct.toFixed(2), r.bad ? "yes" : "no"])) }]);
  },

  async period(out, state, { demo }) {
    out.innerHTML = '<div class="skeleton" style="height:420px"></div>';
    const p = await loadPeriod(state);
    if (!p.files.length) { out.innerHTML = emptyState("No solar map readings in this period"); return; }
    const win = window_(state);
    const farms = joinFarms(p.files, state);
    const rows = farms.map((f) => {
      const r = cfInWindow(f.pts, f.cap, win);
      return { ...f, cfPct: r ? 100 * r.cf : null, energy: r?.energyMwh ?? null, hours: r?.hours ?? null, mw: r ? r.cf * f.cap : null, pct: r ? 100 * r.cf : null };
    }).sort((a, b) => (a.bad - b.bad) || (b.cfPct ?? -1) - (a.cfPct ?? -1));
    const use = counted(rows, state);
    const cfOf = (rs) => {
      const e = rs.reduce((t, r) => t + (r.energy || 0), 0), capH = rs.reduce((t, r) => t + (r.hours ? r.cap * r.hours : 0), 0);
      return capH ? pct((100 * e) / capH, 1) : "—";
    };
    const hoursAll = Math.max(0, ...rows.map((r) => r.hours || 0));
    const hoursIn = p.list.length * (state.h1 - state.h0);
    out.innerHTML = `<p class="small"><b>${esc(fmtDate(p.from))} to ${esc(fmtDate(p.to))}</b>${p.cut ? ` (the first ${MAX_DAYS} days)` : ""}, ${esc(describe(state, true))}.
        Capacity factor = energy produced ÷ (capacity × time). Worked out from the readings of GSO's solar map the archive has:
        time between readings more than 30 minutes apart is left out, not guessed. Readings cover about ${fmtNum(hoursAll)} of the ${fmtNum(hoursIn)} hours chosen,
        so this is the capacity factor over the covered time.</p>
      ${rows.length ? regionRow(use, cfOf) : ""}<div class="chart map"></div><div class="tbl"></div>${flagNote(rows, state)}`;
    if (!rows.length) { out.querySelector(".chart").outerHTML = emptyState("No farm matches these choices"); return; }
    await solarMap(out.querySelector(".chart"), { farms: use, demo, metric: "cf" });
    renderTable(out.querySelector(".tbl"), [...farmCols,
      { key: "cap", label: "Capacity (MW)", num: true, fmt: (v) => fmtNum(v) },
      { key: "energy", label: "Energy (covered time)", num: true, fmt: (v) => (v == null ? "—" : fmtEnergy(v)) },
      { key: "hours", label: "Hours covered", num: true, fmt: (v) => (v == null ? "—" : fmtNum(v)) },
      { key: "cfPct", label: "Capacity factor", num: true, fmt: (v) => pct(v, 1) }], rows, 15);
    const name = `${p.from}_to_${p.to}_${slug(state)}${win.all ? "" : `_${state.h0}-${state.h1}h`}`;
    csvButtons(out, [
      { label: "Per farm (CSV)", file: `lss_capacity_factor_${name}.csv`,
        text: () => SOURCE_NOTE + `\n# Period ${p.from} to ${p.to}, hours ${state.h0}:00-${state.h1}:00 MYT.\n` + csv(
          ["farm", "state", "region", "connection", "capacity_mw", "energy_mwh_covered", "hours_covered", "capacity_factor_percent", "gso_figures_look_wrong"],
          rows.map((r) => [r.code, r.state, r.region, r.conn, r.cap, r.energy == null ? null : +r.energy.toFixed(3), r.hours == null ? null : +r.hours.toFixed(2), r.cfPct == null ? null : +r.cfPct.toFixed(2), r.bad ? "yes" : "no"])) },
      { label: "Every reading (CSV)", title: "Every farm's output at every collected moment of the period (long format, for spreadsheets)", file: `lss_readings_${name}.csv`,
        text: () => SOURCE_NOTE + "\n" + csv(["time_myt", "farm", "state", "region", "connection", "output_mw", "capacity_mw"],
          rows.flatMap((r) => r.pts.filter(([t]) => win.all || (minuteOf(t) >= win.from && minuteOf(t) <= win.to)).map(([t, v]) => [mytIso(t), r.code, r.state, r.region, r.conn, v, r.cap]))
            .sort((a, b) => (a[0] < b[0] ? -1 : a[0] > b[0] ? 1 : a[1] < b[1] ? -1 : 1))) },
    ]);
  },

  async daily(out, state, { demo }) {
    out.innerHTML = '<div class="skeleton" style="height:360px"></div>';
    const p = await loadPeriod(state);
    if (!p.files.length) { out.innerHTML = emptyState("No solar map readings in this period"); return; }
    const win = window_(state);
    const rows = p.files.map((f) => {
      const farms = counted(select(f, state), state);
      let energy = 0, capH = 0;
      for (const farm of farms) { const r = cfInWindow(farm.pts, farm.cap, win); if (r) { energy += r.energyMwh; capH += farm.cap * r.hours; } }
      const fl = fleetSeries(farms);
      const inWin = fl.pts.filter(([t, v]) => v != null && (win.all || (minuteOf(t) >= win.from && minuteOf(t) <= win.to)));
      const peak = inWin.reduce((m, x) => (m && m[1] >= x[1] ? m : x), null);
      return { date: f.date, farms: farms.length, cap: fl.cap, energy: capH ? energy : null, cf: capH ? (100 * energy) / capH : null,
        hours: fl.cap ? capH / fl.cap : null, peak: peak ? peak[1] : null, peakAt: peak ? peak[0] : null, readings: f.times.length };
    });
    out.innerHTML = `<p class="small"><b>${esc(fmtDate(p.from))} to ${esc(fmtDate(p.to))}</b>${p.cut ? ` (the first ${MAX_DAYS} days)` : ""}, ${esc(describe(state, true))}.
      Each day's energy and capacity factor over the time GSO's solar map was collected (gaps over 30 minutes left out). The peak is the highest total
      at a moment when at least 90% of the selected farms had a reading.</p><div class="chart short"></div><div class="tbl"></div>`;
    categoryChart(out.querySelector(".chart"), { categories: rows.map((r) => r.date.slice(5)), demo, yAxes: [{ name: "MWh" }, { name: "%", digits: 0 }],
      series: [{ name: "Energy (covered time)", data: rows.map((r) => r.energy), color: COLORS.solar, unit: "MWh" },
        { name: "Capacity factor", type: "line", yAxisIndex: 1, data: rows.map((r) => (r.cf == null ? null : +r.cf.toFixed(1))), color: COLORS.forecast, unit: "%", digits: 1 }] });
    renderTable(out.querySelector(".tbl"), [
      { key: "date", label: "Day", fmt: (v) => esc(fmtDate(v)) },
      { key: "farms", label: "Farms", num: true, fmt: (v) => fmtNum(v) },
      { key: "cap", label: "Capacity (MW)", num: true, fmt: (v) => fmtNum(v) },
      { key: "energy", label: "Energy (covered time)", num: true, fmt: (v) => (v == null ? "—" : fmtEnergy(v)) },
      { key: "hours", label: "Hours covered", num: true, fmt: (v) => (v == null ? "—" : fmtNum(v, 1)) },
      { key: "cf", label: "Capacity factor", num: true, fmt: (v) => pct(v, 1) },
      { key: "peak", label: "Peak (MW)", num: true, fmt: (v, r) => (v == null ? "—" : `${fmtNum(v)} <small class="muted">${esc(new Date(r.peakAt + MYT).toISOString().slice(11, 16))}</small>`) },
    ], rows.slice().reverse(), 31);
    csvButtons(out, [{ label: "Per day (CSV)", file: `lss_daily_${p.from}_to_${p.to}_${slug(state)}${win.all ? "" : `_${state.h0}-${state.h1}h`}.csv`,
      text: () => SOURCE_NOTE + `\n# ${describe(state)}; hours ${state.h0}:00-${state.h1}:00 MYT.\n` + csv(
        ["date", "farms", "capacity_mw", "energy_mwh_covered", "hours_covered", "capacity_factor_percent", "peak_mw", "peak_time_myt", "solar_map_readings"],
        rows.map((r) => [r.date, r.farms, r.cap, r.energy == null ? null : +r.energy.toFixed(3), r.hours == null ? null : +r.hours.toFixed(2),
          r.cf == null ? null : +r.cf.toFixed(2), r.peak, r.peakAt == null ? null : mytIso(r.peakAt), r.readings])) }]);
  },

  async day(out, state, { demo }) {
    out.innerHTML = '<div class="skeleton" style="height:360px"></div>';
    const data = await getFarmsDay(state.day);
    if (!data?.times?.length) { out.innerHTML = emptyState("No solar map readings on this day"); return; }
    const all = select(data, state);
    const farms = counted(all, state);
    if (!farms.length) { out.innerHTML = emptyState("No farm matches these choices on this day"); return; }
    const fl = fleetSeries(farms);
    const energy = farms.reduce((s, f) => s + (capacityFactor(f.pts, f.cap)?.energyMwh || 0), 0);
    const peak = fl.pts.filter((x) => x[1] != null).reduce((m, x) => (m && m[1] >= x[1] ? m : x), null);
    out.innerHTML = `<p class="small"><b>${esc(fmtDate(state.day))}</b>, ${esc(describe(state))}: the selected farms' total output at each moment GSO's solar map was
      collected (a moment where fewer than 90% of them have a reading is left blank). ${farms.length} farm${farms.length === 1 ? "" : "s"}, ${fmtNum(fl.cap)} MW.</p>
      <div class="stat-row region-row"><span>Energy <b>${fmtEnergy(energy)}</b></span><span>Peak <b>${peak ? `${fmtNum(peak[1])} MW` : "—"}</b>
      ${peak ? `<small class="muted">${esc(new Date(peak[0] + MYT).toISOString().slice(11, 16))}, ${pct((100 * peak[1]) / fl.cap)} of capacity</small>` : ""}</span>
      <span>Readings <b>${fmtNum(data.times.length)}</b></span></div><div class="chart"></div>${flagNote(all, state)}`;
    timeChart(out.querySelector(".chart"), { demo, yAxes: [{ name: "MW", min: 0 }, { name: "%", min: 0, max: 100 }],
      series: [{ name: "Output", color: COLORS.solar, area: true, areaOpacity: 0.3, unit: "MW", points: fl.pts.map(([t, v]) => [new Date(t).toISOString(), v, "ok"]) },
        { name: "Share of capacity", color: COLORS.forecast, yAxisIndex: 1, unit: "%", width: 1.4,
          points: fl.pts.map(([t, v]) => [new Date(t).toISOString(), v == null || !fl.cap ? null : +((100 * v) / fl.cap).toFixed(1), "derived"]) }] });
    csvButtons(out, [
      { label: "Total at each moment (CSV)", file: `lss_day_${state.day}_${slug(state)}.csv`,
        text: () => SOURCE_NOTE + `\n# ${describe(state)}; ${farms.length} farms, ${fl.cap} MW.\n` + csv(["time_myt", "output_mw", "capacity_mw", "percent_of_capacity"],
          fl.pts.map(([t, v]) => [mytIso(t), v, fl.cap, v == null || !fl.cap ? null : +((100 * v) / fl.cap).toFixed(2)])) },
      { label: "Each farm at each moment (CSV)", title: "One column per farm (wide format)", file: `lss_day_${state.day}_${slug(state)}_by_farm.csv`,
        text: () => SOURCE_NOTE + "\n" + csv(["time_myt", ...farms.map((f) => `${f.code}_mw`)],
          data.times.map((t, j) => [mytIso(Date.parse(t)), ...farms.map((f) => f.mw[j])])) },
    ]);
  },
};
