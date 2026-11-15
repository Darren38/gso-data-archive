// System constraints: GSO's two constraint tables from its home page, as the archive keeps them (store.keep_table:
// every row with when it was first and last seen, and every change). Shown exactly as GSO publishes them, under
// GSO's own column headings (gso_archive/adapters/constraints.py).
import { getTable } from "../data.js";
import { ageOf, card, downloadText, emptyState, errorState, esc, fmtAge, fmtDateTime, getParam, h, renderTable, setParams } from "../ui.js";

const LISTS = [
  { key: "constraints_existing", title: "Existing Constraints",
    gso: "Existing Constraint is described by its type of constraints such as inter-area power transfer limitation; circuits in the Grid being constrained; transmission assets’ voltage and thermal limits impact from which generation clusters; and some additional operational remarks if any." },
  { key: "constraints_outage", title: "Constraints Due to Outage (for the next 7 days)",
    gso: "Constraints Due to Outage is described in similar manner however additional information is included which is the outage duration period of the transmission assets giving rise to the system constraints." },
];
const META = new Set(["id", "name", "first_seen", "last_seen", "listed"]);
const MYT = 8 * 3600e3;
const mytIso = (iso) => (iso ? new Date(Date.parse(iso) + MYT).toISOString().slice(0, 16).replace("T", " ") : "");

/** The archive reads these lists every 30 minutes; over 90 minutes since the last read means collection is delayed,
 * so the list may be out of date (CLAUDE.md lesson 36: never let old figures pass for current ones). */
const late = (iso) => (iso && ageOf(iso) > 90 * 60
  ? `<p class="notice small">This list was last read from GSO's page ${esc(fmtAge(ageOf(iso)))} ago (${esc(fmtDateTime(iso))} MYT); GSO may have changed it since.</p>` : "");

/** GSO's columns, in the order GSO gives them (the first row that has each). */
function columnsOf(rows) {
  const cols = [];
  for (const r of rows) for (const k of Object.keys(r)) if (!META.has(k) && !cols.includes(k)) cols.push(k);
  return cols;
}

function csvText(list, cols, rows) {
  const cell = (v) => (v == null ? "" : /[",\n]/.test(String(v)) ? `"${String(v).replace(/"/g, '""')}"` : String(v));
  const head = [...cols, "listed_now", "first_seen_myt", "last_seen_myt"];
  const lines = rows.map((r) => [...cols.map((c) => r[c]), r.listed === false ? "no" : "yes", mytIso(r.first_seen), mytIso(r.last_seen)]);
  return `# Source: GSO home page (gso.org.my), "${list.title}", as kept by GSO Grid Archive. Times in MYT (UTC+8).\n`
    + [head, ...lines].map((r) => r.map(cell).join(",")).join("\n") + "\n";
}

export async function render(main) {
  main.appendChild(h(`<div class="notice">From the two constraint tables on <a href="https://www.gso.org.my/" target="_blank" rel="noopener">GSO's home page</a>,
    checked every 30 minutes. Each row is shown exactly as GSO publishes it, under GSO's own column headings. When GSO removes or edits a row,
    the archive keeps the old one (marked “no longer listed”) and records the change below.</div>`));
  const showOld = getParam("old") === "1";
  let data;
  try {
    data = await Promise.all(LISTS.map((l) => getTable(l.key).catch(() => null)));
  } catch (err) { main.appendChild(h(card({ title: "System constraints", body: errorState(err) }))); return; }
  if (data.every((d) => !d?.checked_at)) {
    main.appendChild(h(card({ title: "System constraints", body: emptyState("No constraint lists archived yet",
      "GSO's Existing Constraints and Constraints Due to Outage are collected from its home page every 30 minutes. They appear here after the next collection.", "◌") })));
    return;
  }
  const changes = [];
  LISTS.forEach((list, i) => {
    const d = data[i];
    const all = d?.rows || [];
    const listed = all.filter((r) => r.listed !== false);
    const rows = showOld ? all : listed;
    const cols = columnsOf(all);
    const c = h(card({ title: list.title, sub: '<span class="tag verified">GSO</span>',
      when: d?.checked_at ? `Checked ${esc(fmtDateTime(d.checked_at))} MYT · ${listed.length} listed now${all.length > listed.length ? `, ${all.length - listed.length} no longer listed` : ""}` : "",
      desc: `GSO: “${esc(list.gso)}”`,
      right: `<label class="inline small"><input type="checkbox" data-old${showOld ? " checked" : ""}> Show rows GSO no longer lists</label>
        <button type="button" class="btn" data-csv>CSV</button>`,
      body: `${late(d?.checked_at)}<div class="tbl"></div>` }));
    main.appendChild(c);
    if (!rows.length) {
      c.querySelector(".tbl").innerHTML = emptyState(d?.checked_at ? "GSO lists no constraints here at the moment" : "Not collected yet", "", "◌");
    } else {
      renderTable(c.querySelector(".tbl"), [
        ...cols.map((k) => ({ key: k, label: k, fmt: (v) => (v == null || v === "" ? "—" : esc(v)) })),
        { key: "first_seen", label: "Listed since", fmt: (v) => esc(mytIso(v)) },
        ...(showOld ? [{ key: "listed", label: "Status", fmt: (v, r) => (v === false ? `<span class="pill warn">No longer listed</span> <small class="muted">last seen ${esc(mytIso(r.last_seen))}</small>` : '<span class="pill ok">Listed</span>') }] : []),
      ], rows, 25);
    }
    c.querySelector("[data-old]").addEventListener("change", (e) => { setParams({ old: e.target.checked ? "1" : null }); location.reload(); });
    c.querySelector("[data-csv]").addEventListener("click", () => downloadText(`gso_${list.key}${showOld ? "_with_old" : ""}.csv`, csvText(list, cols, rows)));
    for (const ch of d?.changes || []) changes.push({ ...ch, list: list.title });
  });
  changes.sort((a, b) => (a.at < b.at ? 1 : -1));
  const cc = h(card({ title: "Changes GSO Made", desc: "Every row GSO added or stopped listing since the archive began collecting its constraint tables, newest first.",
    body: '<div class="tbl"></div>' }));
  main.appendChild(cc);
  if (!changes.length) cc.querySelector(".tbl").innerHTML = emptyState("No changes recorded yet", "The first list collected is the starting point; changes after it appear here.", "◌");
  else {
    renderTable(cc.querySelector(".tbl"), [
      { key: "at", label: "Seen (MYT)", fmt: (v) => esc(mytIso(v)) },
      { key: "list", label: "List" },
      { key: "name", label: "Row", fmt: (v) => esc(v ?? "—") },
      { key: "change", label: "Change", fmt: (v, r) => (r.old !== undefined ? `${esc(v)}: ${esc(r.old ?? "—")} → ${esc(r.new ?? "—")}` : esc(v)) },
    ], changes, 25);
  }
}
