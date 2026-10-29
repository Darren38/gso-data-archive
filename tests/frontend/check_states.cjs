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
  const fakes = ["api-error", "loading", "refresh"].includes(scenario);
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
    if (!out.pages.bess.text.includes("No BESS readings archived yet")) fail.push("BESS empty state missing");
    if (!out.pages.constraints.text.includes("Not yet available")) fail.push("constraints unavailable state missing");
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
    // Solar map: every farm placed, and pointing at one shows its numbers (a geo tooltip setting once hid them all).
    const map = await page.evaluate(async () => {
      const el = document.querySelector(".chart.map"); const c = el && window.echarts.getInstanceByDom(el);
      if (!c) return { farms: 0, tip: "" };
      c.dispatchAction({ type: "showTip", seriesIndex: 0, dataIndex: 0 }); await new Promise((r) => setTimeout(r, 400));
      return { farms: c.getOption().series[0].data.length, tip: [...el.querySelectorAll("div")].map((d) => d.innerText).join(" ") };
    });
    if (!map.farms) fail.push("solar map has no farms");
    if (!/MW of [\d,]+ MW/.test(map.tip)) fail.push("solar map shows no farm details");
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
    out.pages.about = await visit(page, base, "about", 1200);
    if (!(await page.textContent("main")).includes("How current is it?")) fail.push("about page lacks the freshness table");
  } else if (scenario === "interactions") {
    const errorsOnPage = async (label) => {
      const e = await page.$$eval("main .state.error", (x) => x.map((y) => y.textContent.trim().slice(0, 100)));
      if (e.length) fail.push(`${label}: ${e[0]}`);
      const bad = (await page.textContent("main")).match(/\b(NaN|undefined|Infinity)\b/);
      if (bad) fail.push(`${label}: shows "${bad[0]}"`);
    };
    const hash = () => page.evaluate(() => location.hash);
    // Every date preset on every page that has them.
    for (const r of ["solar", "demand", "generation", "tieline", "explorer"]) {
      await page.goto(`${base}/#/${r}`); await page.waitForTimeout(1200);
      for (const b of await page.$$eval("[data-preset]", (x) => x.map((y) => y.dataset.preset))) {
        await page.click(`[data-preset="${b}"]`); await page.waitForTimeout(900);
        if (!(await hash()).includes(`range=${b}`)) fail.push(`${r}: range ${b} not kept in the address`);
        await errorsOnPage(`${r} ${b}`);
      }
    }
    // Custom dates, series choice, overlay and comparison period on Solar; all survive a reload.
    await page.goto(`${base}/#/solar`); await page.waitForTimeout(1500);
    const day = (n) => new Date(Date.now() + 8 * 3600e3 - n * 864e5).toISOString().slice(0, 10);
    await page.fill('[name="from"]', day(12)); await page.fill('[name="to"]', day(3));
    await page.dispatchEvent('[name="to"]', "change"); await page.waitForTimeout(1200);
    if (!(await hash()).includes(`from=${day(12)}`)) fail.push("custom range not kept in the address");
    await errorsOnPage("solar custom range");
    // A future date is pulled back to today.
    await page.fill('[name="to"]', day(-30)); await page.dispatchEvent('[name="to"]', "change"); await page.waitForTimeout(1000);
    if ((await page.inputValue('[name="to"]')) !== day(0)) fail.push("a future end date was accepted");
    const options = await page.$$eval('[name="primary"] option', (o) => o.map((x) => x.value));
    if (options.length > 1) {
      await page.selectOption('[name="primary"]', options[1]); await page.waitForTimeout(1200);
      if (!(await hash()).includes("primary=")) fail.push("primary series not kept in the address");
      await errorsOnPage("solar other primary series");
    }
    await page.click('[name="demand"]'); await page.waitForTimeout(1000);
    await page.click('[data-period="month"]'); await page.waitForTimeout(500);
    const before = await hash();
    await page.reload(); await page.waitForTimeout(2000);
    if ((await page.$eval('[data-period="month"]', (b) => b.getAttribute("aria-pressed"))) !== "true") fail.push("comparison period lost on reload");
    if (await page.$eval('[name="demand"]', (c) => c.checked)) fail.push("demand overlay setting lost on reload");
    if ((await hash()) !== before) fail.push(`address changed on reload: ${before} -> ${await hash()}`);
    // Theme switch keeps the view and draws without errors.
    await page.click("#theme-toggle"); await page.waitForTimeout(2000);
    if ((await hash()) !== before) fail.push("theme switch lost the page settings");
    await errorsOnPage("solar after theme switch");
    // 12-hour / 24-hour switch: times change, the view stays, and the choice survives a reload.
    await page.click("#clock-toggle"); await page.waitForTimeout(2000);
    if (!/\b\d{1,2}:\d{2} (am|pm)\b/.test(await page.textContent("main"))) fail.push("12-hour switch did not change the times");
    if ((await hash()) !== before) fail.push("clock switch lost the page settings");
    await errorsOnPage("solar after clock switch");
    await page.reload(); await page.waitForTimeout(2000);
    if (!(await page.textContent("#clock-toggle")).includes("12-hour")) fail.push("12-hour choice lost on reload");
    await page.click("#clock-toggle"); await page.waitForTimeout(1500);
    if (/\b\d{1,2}:\d{2} (am|pm)\b/.test(await page.textContent("main"))) fail.push("24-hour switch left am/pm times");
    // Table pages.
    await page.goto(`${base}/#/solar?range=90d`); await page.waitForTimeout(2000);
    const next = await page.$('.pager button[data-p="1"]:not([disabled])');
    if (next) { await next.click(); await page.waitForTimeout(300); if (!(await page.textContent("main")).includes("Page 2")) fail.push("table did not go to page 2"); }
    // CSV download from the main chart.
    const [dl] = await Promise.all([page.waitForEvent("download", { timeout: 10000 }), page.click('[data-act="csv"]')]);
    const csv = require("fs").readFileSync(await dl.path(), "utf8");
    if (!csv.startsWith("series,obs_time_utc") || /NaN|undefined/.test(csv) || csv.split("\n").length < 50) fail.push("CSV download is wrong");
    // Excel link answers with a real spreadsheet.
    const xl = await page.$eval('main a.btn[href*="format=xlsx"]', (a) => a.href).catch(() => null);
    if (!xl) fail.push("no Excel link in API mode");
    else { const res = await page.request.get(xl); if (res.status() !== 200 || (await res.body()).subarray(0, 2).toString() !== "PK") fail.push("Excel download failed"); }
    // Explorer: at most 12 series, choice kept in the address, unknown keys in a link ignored.
    await page.goto(`${base}/#/explorer`); await page.waitForTimeout(1500);
    const boxes = await page.$$(".series-pick input[type=checkbox]");
    for (const b of boxes) { if (!(await b.isChecked())) { await b.click(); await page.waitForTimeout(150); } }
    const checked = await page.$$eval(".series-pick input:checked", (x) => x.length);
    if (checked > 12) fail.push(`explorer allowed ${checked} series`);
    if (!(await hash()).includes("series=")) fail.push("explorer series not kept in the address");
    await page.waitForTimeout(1500); await errorsOnPage("explorer many series");
    await page.goto(`${base}/#/explorer?series=bogus.key,generation_mix.solar`); await page.waitForTimeout(1500);
    await errorsOnPage("explorer unknown series link");
    // Fast clicking between pages ends on the last one, with no errors.
    for (const r of ["solar", "demand", "status", "generation", "tieline", "overview", "solar"]) await page.click(`#nav a[data-route="${r}"]`);
    await page.waitForTimeout(2500);
    if ((await page.textContent("#page-title")) !== "Solar") fail.push("fast navigation ended on the wrong page");
    await errorsOnPage("after fast navigation");
    // Phone menu.
    await page.setViewportSize({ width: 390, height: 800 });
    await page.goto(`${base}/#/overview`); await page.waitForTimeout(1200);
    await page.click("#menu-btn"); await page.waitForTimeout(300);
    if (!(await page.$eval("#sidebar", (e) => e.classList.contains("open")))) fail.push("menu did not open");
    await page.click('#nav a[data-route="demand"]'); await page.waitForTimeout(1200);
    if (await page.$eval("#sidebar", (e) => e.classList.contains("open"))) fail.push("menu stayed open after choosing a page");
    if ((await page.textContent("#page-title")) !== "Demand") fail.push("menu link did not navigate");
    await page.click("#menu-btn"); await page.keyboard.press("Escape"); await page.waitForTimeout(300);
    if (await page.$eval("#sidebar", (e) => e.classList.contains("open"))) fail.push("Escape did not close the menu");
  } else if (scenario === "refresh") {
    // New readings arrive while the page is open: it redraws in place, keeps the view and the scroll position.
    let bump = 0, newest = null;
    await page.route("**/api/v1/meta", async (route) => {
      const res = await route.fetch(); const meta = await res.json();
      if (bump) meta.series[0].count += bump;
      if (newest) { // real (not demo) readings whose newest GSO 10-minute reading is from `newest`
        meta.is_demo = false;
        for (const x of meta.series) { x.dataset = "system_demand"; x.kind = "actual"; x.last = newest; }
      }
      route.fulfill({ response: res, json: meta });
    });
    await page.goto(`${base}/#/solar?range=30d`); await page.waitForTimeout(2500);
    const canvases = await page.$$eval("main canvas", (c) => c.length);
    await page.evaluate(() => window.scrollTo(0, 900)); await page.waitForTimeout(200);
    await page.evaluate(() => window.gsoCheckNow()); await page.waitForTimeout(2500);
    if ((await page.$eval("#toast", (t) => t.classList.contains("show")).catch(() => false))) fail.push("redrew although nothing changed");
    bump = 5;
    await page.evaluate(() => window.gsoCheckNow());
    await page.waitForTimeout(400);
    if (await page.$$eval("main .skeleton", (s) => s.length)) fail.push("loading boxes flashed during a live refresh");
    await page.waitForTimeout(3000);
    if (!(await page.$eval("#toast", (t) => t.textContent).catch(() => "")).includes("New readings")) fail.push("no 'New readings loaded' notice");
    if (!(await page.evaluate(() => location.hash)).includes("range=30d")) fail.push("refresh lost the date range");
    if (Math.abs((await page.evaluate(() => window.scrollY)) - 900) > 5) fail.push("refresh moved the scroll position");
    const after = await page.$$eval("main canvas", (c) => c.length);
    if (after !== canvases) fail.push(`charts after refresh: ${after}, before: ${canvases}`);
    if (await page.$(".render-buffer")) fail.push("hidden render buffer left behind");
    if (!(await page.textContent("#freshness-pill")).includes("Checked")) fail.push("no 'Checked' time shown");
    // Collection or GSO stops: an open page must warn that its "current" figures are old, and stop warning once
    // readings are fresh again.
    if (await page.$(".banner.warn")) fail.push("delay warning shown for demo data");
    newest = new Date(Date.now() - 3 * 3600e3).toISOString();
    await page.evaluate(() => window.gsoCheckNow()); await page.waitForTimeout(3000);
    const warn = await page.$eval(".banner.warn", (b) => b.textContent).catch(() => "");
    if (!/Readings are delayed[\s\S]*3 h ago/.test(warn)) fail.push(`no delay warning for 3-hour-old readings: "${warn}"`);
    newest = new Date(Date.now() - 20 * 60e3).toISOString();
    await page.evaluate(() => window.gsoCheckNow()); await page.waitForTimeout(3000);
    if (await page.$(".banner.warn")) fail.push("delay warning stayed after fresh readings arrived");
  }
  if (pageErrors.length) fail.push(`page errors: ${pageErrors.join(" | ")}`);
  out.fail = fail;
  for (const p of Object.values(out.pages)) delete p.text;
  console.log(JSON.stringify(out));
  await browser.close();
  process.exit(fail.length ? 1 : 0);
})().catch((e) => { console.error(e); process.exit(2); });
