// App shell: hash router, theme, banners, freshness indicator, and live refresh.
import { clearCache, getMeta, MODE } from "./data.js";
import { disposeAll, disposeDetached } from "./charts.js";
import { errorState, freshnessPill, esc, fmtTime } from "./ui.js";

const ROUTES = {
  overview: { title: "Overview", load: () => import("./pages/overview.js") },
  solar: { title: "Solar", load: () => import("./pages/solar.js") },
  demand: { title: "Demand", load: () => import("./pages/demand.js") },
  generation: { title: "Generation Mix", load: () => import("./pages/generation.js") },
  bess: { title: "Battery Energy Storage (BESS)", load: () => import("./pages/bess.js") },
  tieline: { title: "Cross-Border Power Exchange (Tie-Line)", load: () => import("./pages/tieline.js") },
  constraints: { title: "System Constraints", load: () => import("./pages/unavailable.js"), arg: "constraints" },
  explorer: { title: "Historical Explorer", load: () => import("./pages/explorer.js") },
  status: { title: "Data Collection Status", load: () => import("./pages/status.js") },
  about: { title: "About & Data Sources", load: () => import("./pages/about.js") },
};

// How often an open page checks for new readings. Only a small file is read; the page redraws only when it changed.
const CHECK_EVERY_MS = 60000;

const main = document.getElementById("main");
let metaPromise = null;
let renderToken = 0;
let shownSignature = null;
let lastChecked = null;
let lastInteraction = 0;

function loadMeta() {
  if (!metaPromise) metaPromise = getMeta().catch((e) => { metaPromise = null; throw e; });
  return metaPromise;
}

/** Changes whenever any series gains a reading (generated_at alone changes on every publish). */
function signature(meta) {
  return meta ? meta.series.map((s) => `${s.key}:${s.last}:${s.count}`).join("|") + `|${meta.is_demo}` : "";
}

function setBanner(meta) {
  const slot = document.getElementById("banner-slot");
  const parts = [];
  if (meta && meta.is_demo) {
    parts.push(`<div class="banner demo" role="note"><strong>Demonstration data.</strong>
      <span>Every value on this site is synthetic, generated to exercise the dashboard. These are <b>not</b> GSO readings.</span></div>`);
  }
  slot.innerHTML = parts.join("");
}

function setFreshness(meta) {
  const el = document.getElementById("freshness-pill");
  const solar = meta?.series.find((s) => s.key === "generation_mix.solar") || meta?.series.find((s) => s.category === "solar" && s.kind === "actual");
  el.innerHTML = [
    meta?.is_demo ? '<span class="pill demo">Demo data</span>' : autoPill(meta?.collection),
    solar ? freshnessPill(solar.last, solar.interval_s) : '<span class="pill bad">No solar data yet</span>',
    lastChecked ? `<span class="pill checked" title="This page checks for new readings every minute and updates itself">Checked ${fmtTime(lastChecked.toISOString())}</span>` : "",
  ].join("");
}

/** "Auto" label: how often the archive updates itself (like Tech Comparison Hub's Auto labels). */
export function autoText(c) {
  if (!c) return null;
  if (!c.live_enabled) return null;
  const seconds = c.observed_interval_seconds || c.interval_seconds || 120;
  const mins = Math.max(1, Math.round(seconds / 60));
  return { mins, measured: !!c.observed_interval_seconds, github: c.mode === "github" };
}

function autoPill(c) {
  if (!c) return "";
  const a = autoText(c);
  if (!a) return '<span class="pill" title="Live collection is switched off (GSO_LIVE_ENABLED)">Auto updates off</span>';
  const how = `${a.measured ? "Measured from recent runs" : "Scheduled"}: new readings about every ${a.mins} min${a.github ? " (GitHub Actions; GitHub sometimes runs late)" : ""}`;
  return `<span class="pill auto" title="${esc(how)}">Auto · every ${a.mins === 1 ? "minute" : `${a.mins} min`}</span>`;
}

function toast(text) {
  let el = document.getElementById("toast");
  if (!el) {
    el = document.createElement("div");
    el.id = "toast"; el.className = "toast"; el.setAttribute("role", "status"); el.setAttribute("aria-live", "polite");
    document.body.appendChild(el);
  }
  el.textContent = text;
  el.classList.add("show");
  clearTimeout(el._t);
  el._t = setTimeout(() => el.classList.remove("show"), 3500);
}

/**
 * Render the page named in the hash. With silent=true (live refresh) the new page is built in a hidden buffer and
 * swapped in when complete, so there is no flash of loading boxes and the scroll position stays where it was.
 */
async function route({ silent = false } = {}) {
  const name = (location.hash.replace(/^#\/?/, "").split("?")[0] || "overview");
  const r = ROUTES[name] || ROUTES.overview;
  const token = ++renderToken;
  if (!silent) {
    document.querySelectorAll("#nav a").forEach((a) => {
      a.classList.toggle("active", a.dataset.route === name);
      if (a.dataset.route === name) a.setAttribute("aria-current", "page"); else a.removeAttribute("aria-current");
    });
    document.getElementById("page-title").textContent = r.title;
    document.title = `${r.title} · GSO Grid Archive`;
    document.getElementById("sidebar").classList.remove("open");
    disposeAll();
    main.innerHTML = '<div class="skeleton" style="height:120px"></div><div class="skeleton" style="height:340px"></div>';
  }
  let target = main;
  if (silent) {
    target = document.createElement("div");
    target.className = "page render-buffer";
    target.style.width = `${main.clientWidth}px`;
    target.style.top = `${main.offsetTop}px`;
    main.parentElement.appendChild(target);
  }
  const scrollY = window.scrollY;
  try {
    const [meta, mod] = await Promise.all([loadMeta(), r.load()]);
    if (token !== renderToken) { if (silent) target.remove(); return; }
    setBanner(meta);
    if (!silent) main.innerHTML = "";
    shownSignature = signature(meta);
    await mod.render(target, { meta, arg: r.arg, isCurrent: () => token === renderToken });
    if (token !== renderToken) { if (silent) target.remove(); return; }
    if (silent) {
      main.replaceChildren(...target.childNodes);
      target.remove();
      disposeDetached();
      window.scrollTo(0, scrollY);
    }
    setFreshness(meta);
  } catch (err) {
    if (silent) { target.remove(); return; } // keep showing the current page; the next check tries again
    if (token !== renderToken) return;
    console.error(err);
    main.innerHTML = errorState(err);
  }
}

/** Every minute: read the small metadata file; if any series has new readings, redraw the page in place. */
async function checkForNewData({ force = false } = {}) {
  if (document.hidden) return;
  // Don't redraw under someone who is using a control right now; try again next minute.
  const busy = Date.now() - lastInteraction < 15000 || document.activeElement?.matches?.("select, input");
  clearCache();
  metaPromise = null;
  let meta;
  try { meta = await loadMeta(); } catch { return; }
  lastChecked = new Date();
  setFreshness(meta);
  if (signature(meta) !== shownSignature && (force || !busy)) {
    await route({ silent: true });
    toast("New readings loaded");
  }
}

function initTheme() {
  const root = document.documentElement;
  let saved = null;
  try { saved = localStorage.getItem("gso-theme"); } catch { /* storage unavailable */ }
  if (saved) root.dataset.theme = saved;
  document.getElementById("theme-toggle").addEventListener("click", () => {
    const dark = root.dataset.theme ? root.dataset.theme === "dark" : matchMedia("(prefers-color-scheme: dark)").matches;
    root.dataset.theme = dark ? "light" : "dark";
    try { localStorage.setItem("gso-theme", root.dataset.theme); } catch { /* ignore */ }
    route({ silent: true }); // charts read their colours when drawn; the page's settings live in the address
  });
}

function initMenu() {
  const btn = document.getElementById("menu-btn"), sb = document.getElementById("sidebar");
  const setOpen = (open) => { sb.classList.toggle("open", open); btn.setAttribute("aria-expanded", String(open)); };
  btn.addEventListener("click", (e) => { e.stopPropagation(); setOpen(!sb.classList.contains("open")); });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") setOpen(false); });
  document.addEventListener("click", (e) => { if (sb.classList.contains("open") && !sb.contains(e.target)) setOpen(false); });
  sb.addEventListener("click", (e) => { if (e.target.closest("nav a")) setOpen(false); });
}

function boot() {
  initTheme();
  initMenu();
  window.addEventListener("hashchange", () => route());
  for (const ev of ["pointerdown", "keydown"]) document.addEventListener(ev, () => { lastInteraction = Date.now(); }, { passive: true });
  setInterval(() => checkForNewData(), CHECK_EVERY_MS);
  document.addEventListener("visibilitychange", () => { if (!document.hidden) checkForNewData(); });
  window.gsoCheckNow = () => checkForNewData({ force: true }); // used by the browser tests
  route();
}

if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot); else boot();
