// Shared UI helpers: formatting (always MYT), states, KPI cards, tables, range picker, CSV.
export const MYT_OFFSET_MS = 8 * 3600e3;

const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
export { esc };

export function h(html) {
  const t = document.createElement("template");
  t.innerHTML = html.trim();
  return t.content.firstElementChild;
}

const mytFmt = new Intl.DateTimeFormat("en-GB", { timeZone: "Asia/Kuala_Lumpur", year: "numeric", month: "short", day: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false });
const mytDate = new Intl.DateTimeFormat("en-GB", { timeZone: "Asia/Kuala_Lumpur", year: "numeric", month: "short", day: "2-digit" });
const mytTime = new Intl.DateTimeFormat("en-GB", { timeZone: "Asia/Kuala_Lumpur", hour: "2-digit", minute: "2-digit", hour12: false });

export const fmtDateTime = (iso) => (iso ? `${mytFmt.format(new Date(iso))}` : "—");
export const fmtDate = (iso) => (iso ? mytDate.format(new Date(iso.length === 10 ? `${iso}T12:00:00+08:00` : iso)) : "—");
export const fmtTime = (iso) => (iso ? mytTime.format(new Date(iso)) : "—");

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

export function card({ title, sub = "", right = "", body = "", cls = "" }) {
  return `<section class="card ${cls}"><div class="card-h"><h2>${esc(title)}</h2>${sub ? `<span class="sub">${sub}</span>` : ""}${right ? `<div class="right">${right}</div>` : ""}</div><div class="card-b">${body}</div></section>`;
}

export function kpi({ label, value, unit = "", meta = "", cls = "", tag = "" }) {
  const v = value == null || value === "—" ? `<span class="na">Not available</span>` : `${value}${unit ? `<small>${esc(unit)}</small>` : ""}`;
  return `<div class="card kpi ${cls}"><div class="label">${esc(label)} ${tag}</div><div class="value">${v}</div><div class="meta">${meta}</div></div>`;
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

/** Range picker. Calls onChange({startDay, endDay, preset}) — inclusive MYT days. */
export function rangePicker(container, { initial = "7d", onChange, presets = ["1d", "7d", "30d", "90d", "1y", "all"] }) {
  const labels = { "1d": "Today", "2d": "48 h", "7d": "7 days", "30d": "30 days", "90d": "90 days", "1y": "1 year", all: "All" };
  const today = mytDay(new Date());
  const state = { preset: initial, startDay: today, endDay: today };
  const el = h(`<div class="toolbar" role="group" aria-label="Date range">
      <div class="seg">${presets.map((p) => `<button type="button" data-preset="${p}" aria-pressed="${p === initial}">${labels[p]}</button>`).join("")}</div>
      <label class="inline">From <input type="date" name="from"></label>
      <label class="inline">To <input type="date" name="to"></label>
      <span class="grow"></span><span class="small muted">Calendar days in MYT</span>
    </div>`);
  container.appendChild(el);
  const from = el.querySelector('[name="from"]'), to = el.querySelector('[name="to"]');
  function applyPreset(p, firstDay) {
    const t = mytDay(new Date());
    const days = { "1d": 0, "2d": 1, "7d": 6, "30d": 29, "90d": 89, "1y": 364 }[p];
    state.endDay = t;
    state.startDay = p === "all" ? (firstDay || addDays(t, -364)) : addDays(t, -days);
  }
  function emit() {
    from.value = state.startDay; to.value = state.endDay; from.max = to.max = mytDay(new Date());
    el.querySelectorAll("[data-preset]").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.preset === state.preset)));
    onChange({ ...state });
  }
  el.querySelectorAll("[data-preset]").forEach((b) => b.addEventListener("click", () => { state.preset = b.dataset.preset; applyPreset(state.preset, picker.firstDay); emit(); }));
  [from, to].forEach((inp) => inp.addEventListener("change", () => {
    if (!from.value || !to.value) return;
    state.preset = "custom";
    state.startDay = from.value <= to.value ? from.value : to.value;
    state.endDay = from.value <= to.value ? to.value : from.value;
    emit();
  }));
  const picker = { el, firstDay: null, state, start() { applyPreset(state.preset, picker.firstDay); emit(); } };
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
