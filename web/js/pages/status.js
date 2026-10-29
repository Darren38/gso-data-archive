// Data Collection Status: collection health is shown separately from data freshness.
import { getStatus } from "../data.js";
import { card, errorState, esc, fmtAge, fmtDateTime, fmtNum, h, kpi, ageOf, verificationTag, renderTable } from "../ui.js";

export async function render(main, { isCurrent }) {
  let st;
  try { st = await getStatus(); } catch (err) { main.innerHTML = errorState(err); return; }
  if (!isCurrent()) return;
  const hb = st.collector_heartbeat;
  const enabled = st.adapters.filter((a) => a.enabled);
  const failing = enabled.filter((a) => a.consecutive_failures > 0);
  const stale = st.freshness.filter((f) => f.stale);
  const hbAge = hb ? ageOf(hb.cycle_started_at) : null;

  main.appendChild(h(`<div class="grid kpis">
    ${kpi({ label: "Live GSO collection", value: st.live_enabled ? "Enabled" : "Disabled", meta: st.live_enabled ? "GSO_LIVE_ENABLED=true" : "Opt-in: review GSO terms, then set GSO_LIVE_ENABLED=true" })}
    ${kpi({ label: "Last collector cycle", value: hb ? fmtAge(hbAge) : null, meta: hb ? `${fmtDateTime(hb.cycle_started_at)} MYT${hb.skipped_reason ? ` — ${esc(hb.skipped_reason)}` : ""}` : "Collector has not run" })}
    ${kpi({ label: "Adapters with failures", value: String(failing.length), meta: `${enabled.length} enabled` })}
    ${kpi({ label: "Stale series", value: String(stale.length), meta: `of ${st.freshness.length} archived series` })}
    ${kpi({ label: "Database", value: st.database.ok ? "Connected" : "Unreachable", meta: st.database.dialect })}
    ${kpi({ label: "Last backup", value: st.backup ? fmtAge(ageOf(st.backup.at)) : null, meta: st.backup ? `${esc(st.backup.kind)} · ${esc(st.backup.file)}` : "No backup recorded by this database" })}
  </div>`));

  // Cross-checks: two figures GSO publishes on two pages must agree, or numbers are being filed under the wrong name.
  const checks = st.cross_checks || [];
  if (checks.length) {
    const pill = (c) => (c.state === "passed" ? '<span class="pill ok">agree</span>'
      : c.state === "failed" ? '<span class="pill bad">disagree</span>' : '<span class="pill">waiting for daylight readings</span>');
    const x = h(card({ title: "Cross-checks between GSO's pages",
      desc: "GSO publishes these figures on two different pages. If they stop agreeing, GSO has probably changed its data and some numbers here may be filed under the wrong name; the owner is emailed. Last 48 hours, daylight only.",
      body: '<div class="tbl"></div>' }));
    main.appendChild(x);
    renderTable(x.querySelector(".tbl"), [
      { key: "state", label: "Result", fmt: (v, r) => pill(r) },
      { key: "name", label: "Check", fmt: (v) => `<span style="white-space:normal">${esc(v)}</span>` },
      { key: "agreeing", label: "Readings that agree", num: true, fmt: (v, r) => `${fmtNum(v)} of ${fmtNum(r.compared)}` },
      { key: "worst", label: "Largest difference", fmt: (v) => (v ? `${fmtNum(v.left)} vs ${fmtNum(v.right)} MW at ${fmtDateTime(v.time)}` : "—") },
    ], checks);
  }

  const a = h(card({ title: "Adapters", sub: "Collection runs (success = the request and storage worked, regardless of whether new data was published)", body: '<div class="tbl"></div>' }));
  main.appendChild(a);
  renderTable(a.querySelector(".tbl"), [
    { key: "adapter", label: "Adapter", fmt: (v) => `<span class="mono">${esc(v)}</span>` },
    { key: "enabled", label: "Enabled", fmt: (v) => (v ? "yes" : "no") },
    { key: "verification", label: "Source", fmt: (v) => verificationTag(v) },
    { key: "last_status", label: "Last run", fmt: (v, r) => (v ? `<span class="pill ${v === "success" ? "ok" : v === "failed" ? "bad" : "warn"}">${esc(v)}</span> ${fmtAge(ageOf(r.last_run_at))}` : "never") },
    { key: "last_success_at", label: "Last success (MYT)", fmt: (v) => (v ? fmtDateTime(v) : "—") },
    { key: "consecutive_failures", label: "Consecutive failures", num: true },
    { key: "runs_24h", label: "Runs 24 h", num: true },
    { key: "new_records_24h", label: "New 24 h", num: true, fmt: (v) => fmtNum(v) },
    { key: "revised_records_24h", label: "Revised 24 h", num: true, fmt: (v) => fmtNum(v) },
    { key: "median_duration_ms_24h", label: "Median duration", num: true, fmt: (v) => (v == null ? "—" : `${fmtNum(v)} ms`) },
    { key: "parse_errors_24h", label: "Parse errors 24 h", num: true },
    { key: "schema_changed_recently", label: "Schema change", fmt: (v) => (v ? '<span class="pill warn">detected</span>' : "—") },
    { key: "last_error", label: "Last error", fmt: (v) => (v ? `<span class="small" title="${esc(v)}">${esc(v.slice(0, 80))}</span>` : "—") },
  ], st.adapters, 20);

  const f = h(card({ title: "Data freshness", sub: "Source observation time of the newest archived reading", body: '<div class="tbl"></div>' }));
  main.appendChild(f);
  renderTable(f.querySelector(".tbl"), [
    { key: "series", label: "Series", fmt: (v) => `<a class="mono" href="#/explorer?series=${encodeURIComponent(v)}">${esc(v)}</a>` },
    { key: "latest_obs_time", label: "Latest observation (MYT)", fmt: (v) => (v ? fmtDateTime(v) : "—") },
    { key: "age_s", label: "Age", fmt: (v) => fmtAge(v) },
    { key: "interval_s", label: "Interval", num: true, fmt: (v) => (v ? `${Math.round(v / 60)} min` : "—") },
    { key: "observed_24h", label: "Readings 24 h", num: true },
    { key: "missing_24h", label: "Missing 24 h", num: true, fmt: (v) => (v == null ? "—" : v) },
    { key: "stale", label: "State", fmt: (v) => (v ? '<span class="pill bad">stale</span>' : '<span class="pill ok">fresh</span>') },
  ], st.freshness, 30);

  main.appendChild(h(card({ title: "Archive totals", body: `<div class="stat-row">${Object.entries(st.totals).map(([k, v]) => `<span>${esc(k.replace("_", " "))}: <b>${fmtNum(v)}</b></span>`).join("")}</div>
    <p class="small muted">Status generated ${fmtDateTime(st.generated_at)} MYT.</p>` })));
  main.appendChild(h(card({ title: "Categories without a verified source", body: `<ul>${Object.entries(st.not_implemented).map(([k, v]) => `<li><b>${esc(k)}</b>: ${esc(v)}</li>`).join("")}</ul>` })));
}
