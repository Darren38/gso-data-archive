// LSS solar farms at a chosen moment, or their capacity factor over a chosen period, from GSO's solar map as the
// archive collected it (one file per day: data/farms/<day>.json, gso_archive/analytics.py farms_day).
import { getFarmDays, getFarmsDay } from "./data.js";
import { solarMap } from "./charts.js";
import { capacityFactor, implausibleSolar, nearestMoment } from "./analysis.js";
import { emptyState, errorState, esc, fmtDate, fmtDateTime, fmtEnergy, fmtNum, getParam, h, renderTable, setParams } from "./ui.js";

const REGIONS = ["North", "Central", "South", "East"];
const MAX_DAYS = 31;
const isDay = (v) => /^\d{4}-\d{2}-\d{2}$/.test(v || "");
const isTime = (v) => /^\d{2}:\d{2}$/.test(v || "");
const addDay = (d, n) => new Date(Date.parse(`${d}T12:00:00+08:00`) + n * 864e5).toISOString().slice(0, 10);

/** Draws the explorer into `el` (a card body). Resolves once the first view is drawn (lesson 7). */
export async function lssExplorer(el, { demo = false } = {}) {
  const days = await getFarmDays().catch(() => []);
  if (!days.length) {
    el.innerHTML = emptyState("No solar farm readings archived yet", "They are kept from GSO's solar map at every collection.", "◌");
    return;
  }
  const newest = days[0], oldest = days[days.length - 1];
  // Settings live in the address (lesson 7) and are checked (lessons 8, 23): unknown values fall back to defaults.
  const clampDay = (d, fallback) => (isDay(d) && d >= oldest && d <= newest ? d : fallback);
  const state = {
    mode: getParam("lss") === "period" ? "period" : "moment",
    day: clampDay(getParam("lssday"), newest),
    time: isTime(getParam("lsstime")) ? getParam("lsstime") : "12:00",
    from: clampDay(getParam("lssfrom"), days[Math.min(6, days.length - 1)]),
    to: clampDay(getParam("lssto"), newest),
  };
  el.innerHTML = `
    <div class="toolbar" role="group" aria-label="LSS farms view">
      <div class="seg"><button type="button" data-mode="moment">At a moment</button><button type="button" data-mode="period">Capacity factor over a period</button></div>
      <span data-show="moment"><label class="inline">Date <input type="date" name="day" min="${oldest}" max="${newest}"></label>
        <label class="inline">Time <input type="time" name="time" step="600"></label></span>
      <span data-show="period"><label class="inline">From <input type="date" name="from" min="${oldest}" max="${newest}"></label>
        <label class="inline">To <input type="date" name="to" min="${oldest}" max="${newest}"></label></span>
      <span class="grow"></span><span class="small muted">MYT · archived from ${esc(fmtDate(oldest))}</span>
    </div>
    <div class="lss-out"></div>`;
  const out = el.querySelector(".lss-out");
  const input = (n) => el.querySelector(`input[name="${n}"]`);
  input("day").value = state.day; input("time").value = state.time; input("from").value = state.from; input("to").value = state.to;

  async function draw() {
    el.querySelectorAll("[data-mode]").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.mode === state.mode)));
    el.querySelectorAll("[data-show]").forEach((s) => { s.hidden = s.dataset.show !== state.mode; });
    setParams({ lss: state.mode === "period" ? "period" : null, lssday: state.day, lsstime: state.time, lssfrom: state.from, lssto: state.to });
    try {
      if (state.mode === "moment") await drawMoment(out, state, demo);
      else await drawPeriod(out, state, demo);
    } catch (err) { out.innerHTML = errorState(err); }
  }
  el.querySelectorAll("[data-mode]").forEach((b) => b.addEventListener("click", () => { state.mode = b.dataset.mode; draw(); }));
  for (const n of ["day", "time", "from", "to"]) {
    input(n).addEventListener("change", () => {
      const v = input(n).value;
      if (n === "time" ? isTime(v) : isDay(v)) { state[n] = v; draw(); }
    });
  }
  await draw();
}

const FLAG = '<span class="pill warn" title="GSO\'s solar map shows this farm at half its capacity or more when the sun is down or barely up (before 07:30 or after 18:45): its figures can\'t be real solar output, so it is left out of the totals">GSO figures look wrong</span>';
const flagNote = (n) => (n ? `<p class="small muted">${n} farm${n > 1 ? "s" : ""} marked "GSO figures look wrong" (output at half capacity or more with the sun down or barely up) ${n > 1 ? "are" : "is"} listed as GSO published ${n > 1 ? "them" : "it"} but left out of the map, the region and the total figures.</p>` : "");

function regionRow(rows, value) {
  rows = rows.filter((r) => !r.bad);
  return `<div class="stat-row region-row">${REGIONS.map((name) => {
    const rs = rows.filter((r) => r.region === name);
    if (!rs.length) return "";
    return `<span>${name} <b>${value(rs)}</b></span>`;
  }).join("")}<span>All <b>${value(rows)}</b> <small class="muted">${rows.length} farms</small></span></div>`;
}

async function drawMoment(out, state, demo) {
  out.innerHTML = '<div class="skeleton" style="height:420px"></div>';
  const data = await getFarmsDay(state.day);
  if (!data?.times?.length) { out.innerHTML = emptyState("No solar map readings on this day"); return; }
  const want = Date.parse(`${state.day}T${state.time}:00+08:00`);
  const i = nearestMoment(data.times, want);
  if (i < 0) {
    const near = data.times.map((t) => Math.abs(Date.parse(t) - want)).reduce((a, b) => Math.min(a, b), Infinity);
    out.innerHTML = emptyState("No solar map reading near that time",
      `The nearest one this day is ${fmtNum(near / 60e3)} minutes away. GSO's solar map was collected at ${data.times.length} moments this day; pick another time.`, "◌");
    return;
  }
  const times = data.times.map((t) => Date.parse(t));
  const rows = data.farms.map((f) => ({ ...f, bad: implausibleSolar(f.mw.map((v, j) => [times[j], v]), f.cap),
    mw: f.mw[i], pct: f.cap && f.mw[i] != null ? (100 * f.mw[i]) / f.cap : null }))
    .filter((f) => f.mw != null).sort((a, b) => (a.bad - b.bad) || (b.pct ?? -1) - (a.pct ?? -1));
  const pctOf = (rs) => {
    const cap = rs.reduce((t, r) => t + (r.cap || 0), 0), mw = rs.reduce((t, r) => t + (r.mw || 0), 0);
    return cap ? `${fmtNum((100 * mw) / cap, 0)}%` : "—";
  };
  out.innerHTML = `<p class="small"><b>${esc(fmtDateTime(data.times[i]))} MYT</b>: the reading of GSO's solar map nearest to your time.
      Each farm's output as a share of its capacity.</p>${regionRow(rows, pctOf)}<div class="chart map"></div><div class="tbl"></div>${flagNote(rows.filter((r) => r.bad).length)}`;
  await solarMap(out.querySelector(".chart"), { farms: rows.filter((r) => !r.bad), demo });
  renderTable(out.querySelector(".tbl"), [
    { key: "code", label: "Farm", fmt: (v, r) => `<a class="mono" href="#/explorer?series=${encodeURIComponent(r.key)}">${esc(v)}</a>${r.bad ? ` ${FLAG}` : ""}` },
    { key: "state", label: "State" }, { key: "region", label: "Region" }, { key: "conn", label: "Connected to" },
    { key: "mw", label: "Output (MW)", num: true, fmt: (v) => fmtNum(v, 1) },
    { key: "cap", label: "Capacity (MW)", num: true, fmt: (v) => fmtNum(v) },
    { key: "pct", label: "Of capacity", num: true, fmt: (v) => (v == null ? "—" : `${fmtNum(v, 0)}%`) },
  ], rows, 15);
}

async function drawPeriod(out, state, demo) {
  let { from, to } = state;
  if (from > to) [from, to] = [to, from];
  const list = [];
  for (let d = from; d <= to && list.length < MAX_DAYS; d = addDay(d, 1)) list.push(d);
  out.innerHTML = '<div class="skeleton" style="height:420px"></div>';
  const files = (await Promise.all(list.map((d) => getFarmsDay(d).catch(() => null)))).filter((f) => f?.times?.length);
  if (!files.length) { out.innerHTML = emptyState("No solar map readings in this period"); return; }
  // Each farm's readings across the period, in time order, with its capacity (the newest within the period).
  const byKey = new Map();
  for (const f of files) {
    const times = f.times.map((t) => Date.parse(t));
    for (const farm of f.farms) {
      const e = byKey.get(farm.key) || { ...farm, pts: [] };
      if (farm.cap) e.cap = farm.cap;
      farm.mw.forEach((v, j) => e.pts.push([times[j], v]));
      byKey.set(farm.key, e);
    }
  }
  const rows = [...byKey.values()].map((f) => {
    f.pts.sort((a, b) => a[0] - b[0]);
    const r = capacityFactor(f.pts, f.cap);
    return { ...f, bad: implausibleSolar(f.pts, f.cap), pts: undefined, cfPct: r ? 100 * r.cf : null, energy: r?.energyMwh ?? null, hours: r?.hours ?? null,
      pct: r ? 100 * r.cf : null, mw: r ? r.cf * f.cap : null };
  }).sort((a, b) => (a.bad - b.bad) || (b.cfPct ?? -1) - (a.cfPct ?? -1));
  const cfOf = (rs) => {
    const e = rs.reduce((t, r) => t + (r.energy || 0), 0), capH = rs.reduce((t, r) => t + (r.hours ? r.cap * r.hours : 0), 0);
    return capH ? `${fmtNum((100 * e) / capH, 1)}%` : "—";
  };
  const hoursAll = Math.max(0, ...rows.map((r) => r.hours || 0)), hoursIn = list.length * 24;
  out.innerHTML = `<p class="small"><b>${esc(fmtDate(from))} to ${esc(fmtDate(list[list.length - 1]))}</b>${list.length < (Date.parse(to) - Date.parse(from)) / 864e5 + 1 ? ` (the first ${MAX_DAYS} days)` : ""}.
      Capacity factor = energy produced ÷ (capacity × time). Worked out from the readings of GSO's solar map the archive has:
      time between readings more than 30 minutes apart is left out, not guessed. Readings cover about ${fmtNum(hoursAll)} of the ${fmtNum(hoursIn)} hours,
      day and night, so this is the capacity factor over the covered time.</p>
    ${regionRow(rows, cfOf)}<div class="chart map"></div><div class="tbl"></div>${flagNote(rows.filter((r) => r.bad).length)}`;
  await solarMap(out.querySelector(".chart"), { farms: rows.filter((r) => !r.bad), demo, metric: "cf" });
  renderTable(out.querySelector(".tbl"), [
    { key: "code", label: "Farm", fmt: (v, r) => `<a class="mono" href="#/explorer?series=${encodeURIComponent(r.key)}">${esc(v)}</a>${r.bad ? ` ${FLAG}` : ""}` },
    { key: "state", label: "State" }, { key: "region", label: "Region" }, { key: "conn", label: "Connected to" },
    { key: "cap", label: "Capacity (MW)", num: true, fmt: (v) => fmtNum(v) },
    { key: "energy", label: "Energy (covered time)", num: true, fmt: (v) => (v == null ? "—" : fmtEnergy(v)) },
    { key: "hours", label: "Hours covered", num: true, fmt: (v) => (v == null ? "—" : fmtNum(v)) },
    { key: "cfPct", label: "Capacity factor", num: true, fmt: (v) => (v == null ? "—" : `${fmtNum(v, 1)}%`) },
  ], rows, 15);
}
