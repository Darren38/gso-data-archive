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
    Every GSO data address this archive uses was checked first-hand on gso.org.my, and the meaning of each value comes from GSO's own page scripts.
    The only data that isn't GSO's is the sunshine and cloud forecast on the Weather page, from
    <a href="https://open-meteo.com/" target="_blank" rel="noopener">Open-Meteo.com</a> (<a href="https://creativecommons.org/licenses/by/4.0/" target="_blank" rel="noopener">CC BY 4.0</a>), labelled wherever it appears.
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
      <li>${verificationTag("third_party_documented")} from a documented outside service, not GSO (the weather forecast).</li>
      <li>${verificationTag("unverified")} the endpoint is inferred and needs confirmation before use.</li>
      <li>${verificationTag("demo")} synthetic demonstration data, not GSO readings.</li>
    </ul></div>` })));
  // What is known to be wrong or unusual in GSO's own figures, and what this site does about each: visitors may use this
  // site instead of GSO's (CLAUDE.md lesson 36), so they should know. Facts only, each found in the archive's checks.
  main.appendChild(h(card({ title: "Known problems in GSO's data, and what this site does",
    desc: "Found by comparing GSO's figures with each other at every collection. Nothing here is corrected or invented: GSO's figures are kept as published.",
    body: `<div class="prose"><ul>
      <li><b>GSO sometimes stops publishing.</b> On the night of 3-4 November 2026 its home page and System Demand page stopped from 9:10 pm to about 1 am;
        on 15 November its Solar page, solar forecast and solar map published nothing from 8:10 am. Those hours can't be recovered from anyone.
        Charts leave them blank, longer gaps are shaded “No readings from GSO”, and every page warns when the newest reading is over 45 minutes old.</li>
      <li><b>A stalled figure repeated as new.</b> At midnight on 4 November GSO's home page restarted with one value that only repeated its stalled figures
        (Grid Demand 20,858 MW). While a reading stands alone like that it is marked “frozen”: kept in the archive, left out of charts, totals and current figures.
        That morning GSO published the missing hour and corrected the figure to 18,929 MW, so the mark was lifted; the stalled value stays in the revision history.</li>
      <li><b>Two missing moments every night.</b> GSO's home page never publishes 23:40 and 23:50. The System Demand Profile joins that short gap in the drawing
        only; pointing at it says “no reading”.</li>
      <li><b>Two solar farms with impossible figures.</b> GSO's solar map shows PTRM and SKCL at nearly full output before sunrise and after sunset.
        They are listed as GSO publishes them, marked “GSO figures look wrong”, and left out of maps and totals.</li>
      <li><b>GSO revises its solar figures.</b> The Solar page sometimes re-sends earlier readings, up to 8.5% lower (29 October 2026). The newest value is shown;
        every earlier value is kept and can be seen in the Explorer.</li>
      <li><b>Two different “demand” figures.</b> GSO's home page Grid Demand and its System Demand page's figure are usually 0-60 MW apart. They are different
        figures, so this site names them separately instead of treating one as the other.</li>
      <li><b>Tie-line direction.</b> GSO's Tie-Line page counts power going out (export) as positive; its home page counts the same flow the other way round.
        Each chart says which way it counts.</li>
      <li><b>Rooftop solar is estimated.</b> NEM, FiT and SELCO figures are GSO's estimates from registered capacity, not meter readings.</li>
      <li><b>Checked every collection:</b> figures GSO publishes twice (Distribution Solar, Grid solar, Grid Demand, tie-line total) are compared each time;
        the results are on the <a href="#/status">Collection Status</a> page, and a disagreement alerts the site's owner.</li>
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
