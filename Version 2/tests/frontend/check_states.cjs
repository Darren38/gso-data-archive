// Browser checks for dashboard states. Invoked by tests/test_frontend.py:
//   node check_states.cjs <scenario> <baseUrl>
// Prints a JSON result; exits non-zero on failure.
const { chromium } = require("playwright");

const ROUTES = ["overview", "solar", "demand", "generation", "bess", "tieline", "constraints", "explorer", "status", "about"];

async function visit(page, base, route, wait = 1200) {
  await page.goto(`${base}/#/${route}`);
  await page.waitForTimeout(wait);
  return {
    title: await page.textContent("#page-title"),
    text: await page.textContent("main"),
    canvases: await page.$$eval("main canvas", (c) => c.length),
    errorStates: await page.$$eval("main .state.error", (e) => e.map((x) => x.textContent.trim())),
    demoBanner: (await page.$(".banner.demo")) !== null,
    skeletons: await page.$$eval("main .skeleton", (s) => s.length),
  };
}

(async () => {
  const [scenario, base] = process.argv.slice(2);
  const browser = await chromium.launch();
  // The site's service worker fetches files itself, which bypasses page.route(); block it where requests are faked.
  const fakes = scenario === "api-error" || scenario === "loading";
  const context = await browser.newContext({ viewport: { width: 1280, height: 900 }, serviceWorkers: fakes ? "block" : "allow" });
  const page = await context.newPage();
  const pageErrors = [];
  page.on("pageerror", (e) => pageErrors.push(e.message));
  const fail = [];
  const out = { scenario, pages: {} };

  if (scenario === "empty") {
    for (const r of ROUTES) out.pages[r] = await visit(page, base, r);
    if (!out.pages.overview.text.includes("Nothing archived yet")) fail.push("overview empty state missing");
    if (!out.pages.solar.text.includes("solar archive is empty")) fail.push("solar empty state missing");
    if (out.pages.overview.canvases) fail.push("charts rendered without data");
    if (out.pages.overview.demoBanner) fail.push("demo banner shown for real (empty) archive");
    if (!out.pages.bess.text.includes("Not yet available")) fail.push("BESS unavailable state missing");
  } else if (scenario === "demo") {
    for (const r of ROUTES) out.pages[r] = await visit(page, base, r, 1800);
    if (!out.pages.solar.demoBanner) fail.push("demo banner missing");
    if (out.pages.solar.canvases < 6) fail.push(`solar page rendered ${out.pages.solar.canvases} charts`);
    if (out.pages.overview.canvases < 2) fail.push("overview charts missing");
    for (const r of ROUTES) if (out.pages[r].errorStates.length) fail.push(`${r}: ${out.pages[r].errorStates[0]}`);
    // Owner's checklist (EPF Goal Planner): no sideways scrolling and no NaN/undefined/Infinity at any width.
    for (const width of [320, 360, 390, 768, 1024, 1440, 1920]) {
      await page.setViewportSize({ width, height: 900 });
      for (const r of ["overview", "solar", "status", "explorer"]) {
        await page.goto(`${base}/#/${r}`); await page.waitForTimeout(900);
        const sw = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
        if (sw > 0) fail.push(`${r} @${width}px scrolls sideways by ${sw}px`);
        const bad = (await page.textContent("main")).match(/\b(NaN|undefined|Infinity)\b/);
        if (bad) fail.push(`${r} @${width}px shows "${bad[0]}"`);
      }
    }
    await page.setViewportSize({ width: 1280, height: 900 });
    // Period switch & range change keep working.
    await page.goto(`${base}/#/solar`); await page.waitForTimeout(1500);
    await page.click('[data-preset="30d"]'); await page.waitForTimeout(1500);
    await page.click('[data-period="week"]'); await page.waitForTimeout(500);
    if (!(await page.textContent("main")).includes("W")) fail.push("weekly comparison did not render");
  } else if (scenario === "api-error") {
    await page.route("**/api/v1/meta", (route) => route.fulfill({ status: 503, body: '{"detail":"database unavailable"}', contentType: "application/json" }));
    out.pages.overview = await visit(page, base, "overview");
    if (!out.pages.overview.errorStates.length) fail.push("no error state on API failure");
    if (!out.pages.overview.text.includes("database unavailable")) fail.push("error detail not shown");
  } else if (scenario === "loading") {
    await page.route("**/api/v1/series/**", async (route) => { await new Promise((r) => setTimeout(r, 2500)); route.continue(); });
    await page.goto(`${base}/#/solar`); await page.waitForTimeout(700);
    out.pages.solar = { skeletons: await page.$$eval("main .skeleton", (s) => s.length) };
    if (!out.pages.solar.skeletons) fail.push("no loading skeleton while data is pending");
  } else if (scenario === "static") {
    out.pages.solar = await visit(page, base, "solar", 2000);
    out.pages.explorer = await visit(page, base, "explorer", 1500);
    if (out.pages.solar.canvases < 3) fail.push("static solar charts missing");
    if (!(await page.$(".banner.warn"))) fail.push("static snapshot banner missing");
  }
  if (pageErrors.length) fail.push(`page errors: ${pageErrors.join(" | ")}`);
  out.fail = fail;
  for (const p of Object.values(out.pages)) delete p.text;
  console.log(JSON.stringify(out));
  await browser.close();
  process.exit(fail.length ? 1 : 0);
})().catch((e) => { console.error(e); process.exit(2); });
