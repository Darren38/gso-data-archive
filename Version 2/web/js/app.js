// App shell: hash router, theme, banners, freshness indicator.
import { clearCache, getMeta, MODE } from "./data.js";
import { disposeAll } from "./charts.js";
import { errorState, freshnessPill, esc } from "./ui.js";

const ROUTES = {
  overview: { title: "Overview", load: () => import("./pages/overview.js") },
  solar: { title: "Solar", load: () => import("./pages/solar.js") },
  demand: { title: "Demand", load: () => import("./pages/demand.js") },
  generation: { title: "Generation", load: () => import("./pages/generation.js") },
  bess: { title: "Battery Energy Storage (BESS)", load: () => import("./pages/unavailable.js"), arg: "bess" },
  tieline: { title: "Tie-line Flows", load: () => import("./pages/tieline.js") },
  constraints: { title: "System Constraints", load: () => import("./pages/unavailable.js"), arg: "constraints" },
  explorer: { title: "Historical Explorer", load: () => import("./pages/explorer.js") },
  status: { title: "Data Collection Status", load: () => import("./pages/status.js") },
  about: { title: "About & Data Sources", load: () => import("./pages/about.js") },
};

const main = document.getElementById("main");
let metaPromise = null;
let renderToken = 0;

function loadMeta() {
  if (!metaPromise) metaPromise = getMeta().catch((e) => { metaPromise = null; throw e; });
  return metaPromise;
}

function setBanner(meta) {
  const slot = document.getElementById("banner-slot");
  const parts = [];
  if (meta && meta.is_demo) {
    parts.push(`<div class="banner demo" role="note"><strong>Demonstration data.</strong>
      <span>Every value on this site is synthetic, generated to exercise the dashboard. These are <b>not</b> GSO readings.</span></div>`);
  }
  if (MODE === "static") {
    parts.push(`<div class="banner warn" role="note"><span>Published${meta && meta.generated_at ? ` ${esc(new Date(meta.generated_at).toLocaleString("en-GB", { timeZone: "Asia/Kuala_Lumpur" }))} MYT` : ""}. The site is published again whenever new readings are collected. CSV downloads work here; Excel needs the API deployment.</span></div>`);
  }
  slot.innerHTML = parts.join("");
}

function setFreshness(meta) {
  const el = document.getElementById("freshness-pill");
  const solar = meta?.series.find((s) => s.key === "generation_mix.solar") || meta?.series.find((s) => s.category === "solar" && s.kind === "actual");
  el.innerHTML = [
    meta?.is_demo ? '<span class="pill demo">Demo data</span>' : autoPill(meta?.collection),
    solar ? freshnessPill(solar.last, solar.interval_s) : '<span class="pill bad">No solar data yet</span>',
  ].join("");
}

/** "Auto" label: how often the archive updates itself (like Tech Comparison Hub's Auto labels). */
function autoPill(c) {
  if (!c) return "";
  if (!c.live_enabled) return '<span class="pill" title="Live collection is switched off (GSO_LIVE_ENABLED)">Auto updates off</span>';
  const mins = Math.round((c.interval_seconds || 300) / 60);
  const how = c.mode === "github" ? `GitHub Actions, about every ${mins} min (GitHub may run it later)` : `every ${mins} min`;
  return `<span class="pill auto" title="New readings are collected automatically: ${esc(how)}">Auto · every ${mins} min</span>`;
}

async function route() {
  const name = (location.hash.replace(/^#\/?/, "").split("?")[0] || "overview");
  const r = ROUTES[name] || ROUTES.overview;
  const token = ++renderToken;
  document.querySelectorAll("#nav a").forEach((a) => a.classList.toggle("active", a.dataset.route === name));
  document.querySelectorAll("#nav a").forEach((a) => (a.dataset.route === name ? a.setAttribute("aria-current", "page") : a.removeAttribute("aria-current")));
  document.getElementById("page-title").textContent = r.title;
  document.title = `${r.title} · GSO Grid Archive`;
  document.getElementById("sidebar").classList.remove("open");
  disposeAll();
  main.innerHTML = '<div class="skeleton" style="height:120px"></div><div class="skeleton" style="height:340px"></div>';
  try {
    const [meta, mod] = await Promise.all([loadMeta(), r.load()]);
    if (token !== renderToken) return;
    setBanner(meta);
    setFreshness(meta);
    main.innerHTML = "";
    await mod.render(main, { meta, arg: r.arg, isCurrent: () => token === renderToken });
  } catch (err) {
    if (token !== renderToken) return;
    console.error(err);
    main.innerHTML = errorState(err);
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
    route();
  });
}

function initMenu() {
  const btn = document.getElementById("menu-btn"), sb = document.getElementById("sidebar");
  btn.addEventListener("click", () => { const open = sb.classList.toggle("open"); btn.setAttribute("aria-expanded", String(open)); });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") sb.classList.remove("open"); });
  document.addEventListener("click", (e) => { if (sb.classList.contains("open") && !sb.contains(e.target) && e.target !== btn) sb.classList.remove("open"); });
}

function boot() {
  initTheme();
  initMenu();
  window.addEventListener("hashchange", route);
  // Refresh metadata every 5 minutes so freshness indicators stay honest.
  setInterval(() => { clearCache(); metaPromise = null; loadMeta().then((m) => { setFreshness(m); }).catch(() => {}); }, 300000);
  route();
}

if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot); else boot();
