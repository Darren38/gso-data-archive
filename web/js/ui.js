// Shared UI helpers: formatting (always MYT), states, KPI cards, tables, range picker, CSV.
import { ICONS } from "./icons.js";
export const MYT_OFFSET_MS = 8 * 3600e3;

const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
export { esc };

export function h(html) {
  const t = document.createElement("template");
  t.innerHTML = html.trim();
  return t.content.firstElementChild;
}

// 12-hour or 24-hour clock: the visitor's choice, remembered in this browser only.
let hour12 = false;
try { hour12 = localStorage.getItem("gso-clock") === "12"; } catch { /* storage unavailable */ }
export const isHour12 = () => hour12;
export function setHour12(on) {
  hour12 = !!on;
  try { localStorage.setItem("gso-clock", hour12 ? "12" : "24"); } catch { /* ignore */ }
}
/** "13:05" or "1:05 pm" from an hour (0–23) and minute. */
export function clock(h, m) {
  const mm = String(m).padStart(2, "0");
  return hour12 ? `${h % 12 || 12}:${mm} ${h < 12 ? "am" : "pm"}` : `${String(h).padStart(2, "0")}:${mm}`;
}

const MYT = "Asia/Kuala_Lumpur";
const mytDate = new Intl.DateTimeFormat("en-GB", { timeZone: MYT, year: "numeric", month: "short", day: "2-digit" });
const timeParts = (iso) => {
  const d = new Date(Date.parse(iso) + MYT_OFFSET_MS);
  return clock(d.getUTCHours(), d.getUTCMinutes());
};

export const fmtDateTime = (iso) => (iso ? `${mytDate.format(new Date(iso))}, ${timeParts(iso)}` : "—");
export const fmtDate = (iso) => (iso ? mytDate.format(new Date(iso.length === 10 ? `${iso}T12:00:00+08:00` : iso)) : "—");
export const fmtTime = (iso) => (iso ? timeParts(iso) : "—");

export function fmtNum(v, digits = 0) {
  if (v == null || Number.isNaN(v)) return "—";
  return Number(v).toLocaleString("en-GB", { minimumFractionDigits: digits, maximumFractionDigits: digits });
}
export function fmtEnergy(mwh) {
  if (mwh == null) return "—";
  if (Math.abs(mwh) >= 1e6) return `${fmtNum(mwh / 1e6, 2)} TWh`;
  if (Math.abs(mwh) >= 1e3) return `${fmtNum(mwh / 1e3, 1)} GWh`;
  return `${fmtNum(mwh, 0)} MWh`;
}
export function fmtAge(seconds) {
  if (seconds == null) return "never";
  if (seconds < 90) return `${Math.round(seconds)} s ago`;
  if (seconds < 5400) return `${Math.round(seconds / 60)} min ago`;
  if (seconds < 172800) return `${Math.round(seconds / 3600)} h ago`;
  return `${Math.round(seconds / 86400)} days ago`;
}
export const ageOf = (iso) => (iso ? (Date.now() - Date.parse(iso)) / 1000 : null);

/** YYYY-MM-DD of a Date in MYT. */
export function mytDay(d) { return new Date(d.getTime() + MYT_OFFSET_MS).toISOString().slice(0, 10); }
/** Start of a MYT day (YYYY-MM-DD) as a Date. */
export function mytDayStart(day) { return new Date(`${day}T00:00:00+08:00`); }
export function addDays(day, n) { const d = new Date(`${day}T00:00:00Z`); d.setUTCDate(d.getUTCDate() + n); return d.toISOString().slice(0, 10); }

export function loading(height = 320) { return `<div class="skeleton" style="height:${height}px" aria-busy="true" aria-label="Loading"></div>`; }

export function emptyState(title, body = "", icon = "○") {
  return `<div class="state" role="status"><div class="big" aria-hidden="true">${icon}</div><h3>${esc(title)}</h3>${body ? `<p>${body}</p>` : ""}</div>`;
}
export function errorState(err) {
  return `<div class="state error" role="alert"><div class="big" aria-hidden="true">!</div><h3>Could not load data</h3><p>${esc(err && err.message ? err.message : err)}</p><p class="muted">Previously archived data is unaffected. Try again shortly.</p></div>`;
}

/** A dashboard card. `desc` is a one-line, plain-words "how to read this" shown under the title. */
export function card({ title, sub = "", desc = "", right = "", body = "", cls = "" }) {
  return `<section class="card ${cls}"><div class="card-h"><h2>${esc(title)}</h2>${sub ? `<span class="sub">${sub}</span>` : ""}${right ? `<div class="right">${right}</div>` : ""}</div>${desc ? `<p class="desc">${desc}</p>` : ""}<div class="card-b">${body}</div></section>`;
}

export function kpi({ label, value, unit = "", meta = "", cls = "", tag = "", big = false, icon = "" }) {
  const v = value == null || value === "—" ? `<span class="na">Not available</span>` : `${value}${unit ? `<small>${esc(unit)}</small>` : ""}`;
  return `<div class="card kpi ${cls} ${big ? "big" : ""}"><div class="label">${icon && ICONS[icon] ? `<span class="kpi-icon">${ICONS[icon]}</span>` : ""}<span>${esc(label)} ${tag}</span></div><div class="value">${v}</div><div class="meta">${meta}</div></div>`;
}

/** A section heading between groups of cards. */
export function section(title, text = "") {
  return `<div class="section-h"><h2>${esc(title)}</h2>${text ? `<p>${text}</p>` : ""}</div>`;
}

export function verificationTag(v) {
  const labels = { verified: "verified", third_party_documented: "3rd-party documented", unverified: "unverified source", demo: "DEMO" };
  return `<span class="tag ${esc(v)}" title="Source verification level">${esc(labels[v] || v || "unknown")}</span>`;
}

export function freshnessPill(iso, intervalS) {
  if (!iso) return `<span class="pill bad">No data</span>`;
  const age = ageOf(iso);
  const limit = Math.max(3 * (intervalS || 1800), 3600);
  const cls = age <= limit ? "ok" : age <= 4 * limit ? "warn" : "bad";
  return `<span class="pill ${cls}" title="Source observation time ${fmtDateTime(iso)} MYT">Observed ${fmtAge(age)}</span>`;
}

/** Paginated table. columns: [{key, label, num?, fmt?}] */
export function renderTable(container, columns, rows, pageSize = 50) {
  let page = 0;
  const pages = Math.max(1, Math.ceil(rows.length / pageSize));
  function draw() {
    const slice = rows.slice(page * pageSize, (page + 1) * pageSize);
    container.innerHTML = rows.length ? `
      <div class="table-wrap"><table><thead><tr>${columns.map((c) => `<th class="${c.num ? "num" : ""}" scope="col">${esc(c.label)}</th>`).join("")}</tr></thead>
      <tbody>${slice.map((r) => `<tr>${columns.map((c) => `<td class="${c.num ? "num" : ""}">${c.fmt ? c.fmt(r[c.key], r) : esc(r[c.key] ?? "—")}</td>`).join("")}</tr>`).join("")}</tbody></table></div>
      <div class="pager"><span>${fmtNum(rows.length)} rows</span>
        <button class="btn" data-p="-1" ${page === 0 ? "disabled" : ""}>‹ Prev</button>
        <span>Page ${page + 1} / ${pages}</span>
        <button class="btn" data-p="1" ${page >= pages - 1 ? "disabled" : ""}>Next ›</button></div>`
      : emptyState("No rows in this range");
    container.querySelectorAll("[data-p]").forEach((b) => b.addEventListener("click", () => { page += Number(b.dataset.p); draw(); }));
  }
  draw();
}

/** Page settings kept in the address after "?" (e.g. #/solar?range=30d), so a refresh, a theme switch or a shared
 * link shows the same view. */
export function getParam(name) {
  return new URLSearchParams(location.hash.split("?")[1] || "").get(name);
}

export function setParams(values) {
  const [path, query] = location.hash.split("?");
  const params = new URLSearchParams(query || "");
  for (const [k, v] of Object.entries(values)) {
    if (v == null || v === "") params.delete(k); else params.set(k, v);
  }
  const q = params.toString();
  history.replaceState(null, "", `${path || "#/overview"}${q ? `?${q}` : ""}`); // no hashchange: no re-render
}

const DAY_RE = /^\d{4}-\d{2}-\d{2}$/;

/** Range picker. Calls onChange({startDay, endDay, preset}) — inclusive MYT days — and returns its promise. */
export function rangePicker(container, { initial = "7d", onChange, presets = ["1d", "7d", "30d", "90d", "1y", "all"] }) {
  const labels = { "1d": "Today", "2d": "48 h", "7d": "7 days", "30d": "30 days", "90d": "90 days", "1y": "1 year", all: "All" };
  const today = mytDay(new Date());
  const state = { preset: initial, startDay: today, endDay: today };
  const fromUrl = getParam("range"), f = getParam("from"), t = getParam("to");
  if (fromUrl && presets.includes(fromUrl)) state.preset = fromUrl;
  else if (f && t && DAY_RE.test(f) && DAY_RE.test(t)) Object.assign(state, { preset: "custom", startDay: f <= t ? f : t, endDay: f <= t ? t : f });
  const el = h(`<div class="toolbar" role="group" aria-label="Date range">
      <div class="seg">${presets.map((p) => `<button type="button" data-preset="${p}" aria-pressed="false">${labels[p]}</button>`).join("")}</div>
      <label class="inline">From <input type="date" name="from"></label>
      <label class="inline">To <input type="date" name="to"></label>
      <span class="grow"></span><span class="small muted">Calendar days in MYT</span>
    </div>`);
  container.appendChild(el);
  const from = el.querySelector('[name="from"]'), to = el.querySelector('[name="to"]');
  function applyPreset(p, firstDay) {
    const now = mytDay(new Date());
    const days = { "1d": 0, "2d": 1, "7d": 6, "30d": 29, "90d": 89, "1y": 364 }[p];
    state.endDay = now;
    state.startDay = p === "all" ? (firstDay && firstDay <= now ? firstDay : addDays(now, -364)) : addDays(now, -days);
  }
  function emit() {
    from.value = state.startDay; to.value = state.endDay; from.max = to.max = mytDay(new Date());
    el.querySelectorAll("[data-preset]").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.preset === state.preset)));
    setParams(state.preset === "custom" ? { range: null, from: state.startDay, to: state.endDay } : { range: state.preset, from: null, to: null });
    return Promise.resolve(onChange({ ...state }));
  }
  el.querySelectorAll("[data-preset]").forEach((b) => b.addEventListener("click", () => { state.preset = b.dataset.preset; applyPreset(state.preset, picker.firstDay); emit(); }));
  [from, to].forEach((inp) => inp.addEventListener("change", () => {
    if (!DAY_RE.test(from.value) || !DAY_RE.test(to.value)) return;
    const max = mytDay(new Date());
    const a = from.value > max ? max : from.value, b = to.value > max ? max : to.value; // no future days
    state.preset = "custom";
    state.startDay = a <= b ? a : b;
    state.endDay = a <= b ? b : a;
    emit();
  }));
  const picker = {
    el, firstDay: null, state,
    start() { if (state.preset !== "custom") applyPreset(state.preset, picker.firstDay); return emit(); },
  };
  return picker;
}

export function downloadText(filename, text, type = "text/csv;charset=utf-8") {
  const blob = new Blob([text], { type });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob); a.download = filename; document.body.appendChild(a); a.click();
  setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 500);
}

/** CSV of point payloads; gaps are omitted (never written as 0). */
export function pointsToCsv(payloads) {
  const lines = ["series,obs_time_utc,obs_time_myt,value,unit,quality,is_demo"];
  const rows = [];
  for (const p of payloads) {
    for (const [t, v, q] of p.points) {
      if (v == null) continue;
      const myt = new Date(Date.parse(t) + MYT_OFFSET_MS).toISOString().replace("Z", "+08:00").replace(".000", "");
      rows.push([t, `${p.series},${t},${myt},${v},${p.unit},${q},${!!p.is_demo}`]);
    }
  }
  rows.sort((a, b) => (a[0] < b[0] ? -1 : a[0] > b[0] ? 1 : 0));
  return lines.concat(rows.map((r) => r[1])).join("\n") + "\n";
}

/** Short forms used on the pages (GSO's own terms), explained in a few words. */
export const SHORT_FORMS = {
  GSO: "Grid System Operator, which runs Peninsular Malaysia's grid",
  MW: "megawatt: power at one moment",
  MWh: "megawatt-hour: energy over time (1 GWh = 1,000 MWh; 1 TWh = 1,000 GWh)",
  "MW/min": "change in MW per minute",
  MYT: "Malaysia time (UTC+8)",
  Grid: "solar farms connected to the high-voltage transmission grid",
  Distribution: "solar connected to the local distribution network",
  NEM: "Net Energy Metering: rooftop solar that offsets the owner's bill (GSO estimate)",
  FiT: "Feed-in Tariff: solar sold to the grid at a fixed price (GSO estimate)",
  SELCO: "Self-Consumption: rooftop solar used on site (GSO estimate)",
  LSS: "Large Scale Solar: big solar farms on GSO's solar map",
  RE: "renewable energy; Other RE is biogas, biomass and mini hydro",
  "Co-Gen": "co-generation: plants that make electricity and heat together",
  "Oil/DF": "oil and distillate fuel",
  BESS: "Battery Energy Storage System",
  "Tie-Line": "power line linking Malaysia's grid with a neighbour's",
  EGAT: "link with the Electricity Generating Authority of Thailand",
  HVDC: "High-Voltage Direct Current link with Thailand",
  PLTG: "Plentong link with Singapore",
};

/** A small side note explaining the short forms a page uses. */
export function shortForms(keys) {
  const items = keys.filter((k) => SHORT_FORMS[k]).map((k) => `<span><b>${esc(k)}</b> ${esc(SHORT_FORMS[k])}</span>`);
  // A long list folds into a dropdown (press to expand) so the charts stay near the top.
  const open = items.length <= 3 ? " open" : "";
  return items.length ? `<details class="shortforms"${open}><summary>Short forms used on this page <span class="muted">(${items.length})</span></summary><div>${items.join("")}</div></details>` : "";
}
