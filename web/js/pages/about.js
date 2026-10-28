// About & Data Sources.
import { MODE } from "../data.js";
import { SHORT_FORMS, card, esc, fmtDateTime, h, verificationTag } from "../ui.js";

export async function render(main, { meta }) {
  main.appendChild(h(card({ title: "About this archive", body: `<div class="prose">
    <p>An independent, long-term archive of electricity-grid data published by Malaysia's
    <a href="https://www.gso.org.my/" target="_blank" rel="noopener">Grid System Operator (GSO)</a> for Peninsular Malaysia.
    Some GSO data is only on the GSO website for a limited time. This project collects it on a schedule and keeps it permanently,
    so it can be searched, analysed and downloaded. Solar generation is the main focus.</p>
    <p><b>Not affiliated with GSO or Tenaga Nasional Berhad.</b> GSO's terms of use apply to the underlying data.
    Every data address this archive uses was checked first-hand on gso.org.my, and the meaning of each value comes from GSO's own page scripts.
    GSO's NEM, FiT and SELCO rooftop solar values are GSO's estimates from registered capacity and are labelled that way.</p>
    <h2>Data conventions</h2>
    <ul>
      <li><b>Time:</b> times are stored in UTC and shown in Malaysia time (MYT, UTC+8). GSO timestamps without a timezone are read as MYT.</li>
      <li><b>Observation time vs collection time:</b> charts use the time the source says the reading applies to. The time the archive collected it is recorded separately.</li>
      <li><b>Missing data:</b> a missing reading is shown as a gap and exported as an absent row. It is never treated as zero.</li>
      <li><b>Revisions:</b> if GSO changes a reading after it was collected, the new value is shown and the old value is kept in the revision history (see the Explorer).</li>
      <li><b>Derived values:</b> energy (MWh), shares, ramp rates and totals are calculated from archived readings and are labelled “derived”.</li>
      <li><b>Forecasts:</b> forecasts are stored separately from actuals, with the forecast issue time and the target time it applies to.</li>
      <li><b>Quality flags:</b> <code>suspect_negative</code>, <code>out_of_range</code> and <code>suspect_night</code> mark readings that need checking. Flagged readings are kept as published, not corrected.</li>
    </ul>
    <h2>Source verification levels</h2>
    <ul>
      <li>${verificationTag("verified")} the request and response were observed first-hand by this project.</li>
      <li>${verificationTag("unverified")} the endpoint is inferred and needs confirmation before use.</li>
      <li>${verificationTag("demo")} synthetic demonstration data, not GSO readings.</li>
    </ul></div>` })));
  const c = meta.collection;
  main.appendChild(h(card({ title: "How current is it?", body: `<div class="table-wrap"><table><tbody>
    <tr><th scope="row">New readings</th><td style="white-space:normal">${!c ? "—" : !c.live_enabled ? "Automatic collection is switched off" : c.mode === "github"
      ? `Collected automatically by GitHub Actions about every ${Math.round(c.interval_seconds / 60)} minutes. GitHub sometimes runs it later; nothing is lost, because each request returns the whole day.`
      : `Collected automatically every ${Math.round(c.interval_seconds / 60)} minutes.`}</td></tr>
    <tr><th scope="row">Missed days</th><td style="white-space:normal">Yesterday is checked again every hour for late or corrected readings, and days the collector missed are fetched again automatically.</td></tr>
    <tr><th scope="row">This page</th><td style="white-space:normal">${MODE === "static" ? `Published ${esc(meta.generated_at ? fmtDateTime(meta.generated_at) : "")} MYT. Every visit checks for newer files.` : "Live from the archive."}</td></tr>
    </tbody></table></div>
    ${MODE === "static" && !meta.is_demo ? '<p><a class="btn primary" href="data/archive.sqlite3.gz" download>Download the whole archive (SQLite, gzip)</a> <span class="small muted">Every reading and every revision. Open with any SQLite tool.</span></p>' : ""}` })));
  main.appendChild(h(card({ title: "Short forms", desc: "The terms GSO uses on its pages, which this site uses too.", body: `<div class="table-wrap"><table><tbody>
    ${Object.entries(SHORT_FORMS).map(([k, v]) => `<tr><th scope="row">${esc(k)}</th><td style="white-space:normal">${esc(v)}</td></tr>`).join("")}
    </tbody></table></div>` })));
  main.appendChild(h(card({ title: "Datasets", body: `<div class="table-wrap"><table><thead><tr><th>Dataset</th><th>Category</th><th>Source page</th><th>Verification</th><th>Notes</th></tr></thead><tbody>
    ${meta.datasets.map((d) => `<tr><td class="mono">${esc(d.key)}</td><td>${esc(d.category)}</td><td class="mono">${esc(d.source_url)}</td><td>${verificationTag(d.verification)}</td><td style="white-space:normal;min-width:320px">${esc(d.description)}${d.no_data_yet ? ' <span class="muted">(no data archived yet)</span>' : ""}</td></tr>`).join("")}
    </tbody></table></div>` })));
}
