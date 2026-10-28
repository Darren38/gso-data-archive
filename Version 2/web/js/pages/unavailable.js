// BESS and System Constraints: categories with no verified data source yet.
import { card, emptyState, esc, h } from "../ui.js";

const COPY = {
  bess: {
    title: "Battery energy storage (BESS)",
    want: "Published BESS status, available power/energy, charge/discharge readings and historical status changes.",
  },
  constraints: {
    title: "System constraints",
    want: "Published constraint records with descriptions, limits, dates and durations, and changes to those records over time.",
  },
};

export async function render(main, { meta, arg }) {
  const c = COPY[arg];
  const reason = meta.not_implemented?.[arg] || "No data source identified yet.";
  const archived = meta.series.filter((s) => s.category === arg);
  main.appendChild(h(card({
    title: c.title,
    body: archived.length
      ? `<p>${archived.length} series archived. Use the <a href="#/explorer">Historical Explorer</a> to chart them.</p>`
      : emptyState("Not yet available", `${esc(reason)}<br><br><b>Target data:</b> ${esc(c.want)}`, "◌"),
  })));
  main.appendChild(h(card({
    title: "What is needed to enable this category",
    body: `<ol class="prose">
      <li>From a network that can reach gso.org.my, run <code>gso-archive probe</code>. It saves each SystemData page and lists the PageMethods / AJAX URLs it references.</li>
      <li>If a ${esc(arg.toUpperCase())} endpoint exists, add an <code>AdapterSpec</code> in <code>gso_archive/adapters/registry.py</code> and save a real response as a test fixture.</li>
      <li>Enable it via <code>GSO_ADAPTERS</code>. Unknown fields are auto-discovered, and every change is kept in the revision history.</li>
    </ol>
    <p class="small muted">Nothing on this page is estimated or simulated. It stays empty until real published data is archived.</p>`,
  })));
}
